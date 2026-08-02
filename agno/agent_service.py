"""
Agno Agent Service - Flask HTTP server that runs an Agno agent with bash tool execution.
This service is called by the Next.js API route.

Usage:
    python agent_service.py

Runs on http://localhost:8081
"""

import json
import subprocess
import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# Try importing agno, fall back gracefully
try:
    from agno.agent import Agent
    from agno.models.openai.like import OpenAILike
    AGNO_AVAILABLE = True
except ImportError as e:
    AGNO_AVAILABLE = False
    print(f"WARNING: agno not installed or import failed: {e}")
    print("Install with: pip install -r requirements.txt")

app = Flask(__name__)
CORS(app)

# --- Configuration ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    """Load LLM and tool configuration from config.json."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "provider": "YOUR_PROVIDER",
            "baseURL": "http://localhost:8080/v1",
            "apiKey": "example",
            "model": "openai-compatible:modelName",
            "allowList": ["ls", "pwd"],
            "allowAll": False,
        }


# --- Bash Tool ---
ALLOW_LIST = ["ls", "pwd"]
ALLOW_ALL = False


def bash_tool(command: str, run_context=None) -> str:
    """Execute a bash command. ONLY use when the user explicitly asks to run a shell command, check system info, or list files."""
    # Allow list check
    global ALLOW_LIST, ALLOW_ALL
    cfg = load_config()
    ALLOW_LIST = cfg.get("allowList", ["ls", "pwd"])
    ALLOW_ALL = cfg.get("allowAll", False)

    base_cmd = command.strip().split()[0] if command.strip() else ""
    if base_cmd not in ALLOW_LIST and not ALLOW_ALL:
        return json.dumps(
            {"error": f"Command '{base_cmd}' not allowed", "stdout": "", "stderr": ""}
        )

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        if result.returncode != 0:
            output["error"] = f"Command exited with code {result.returncode}"
        return json.dumps(output)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Command timed out (30s)", "stdout": "", "stderr": ""})
    except Exception as e:
        return json.dumps({"error": str(e), "stdout": "", "stderr": ""})


# --- Agent Factory ---
def create_agent():
    """Create and return an Agno Agent configured with the bash tool."""
    cfg = load_config()

    if not AGNO_AVAILABLE:
        raise RuntimeError("agno package is not installed. Run: pip install -r requirements.txt")

    model = OpenAILike(
        id=cfg.get("model", "your-model-id"),
        api_key=cfg.get("apiKey", "example"),
        base_url=cfg.get("baseURL", "http://localhost:8080/v1"),
    )

    # Build dynamic bash instructions from shared config
    config = load_chatlets_config()
    bash_prompt = get_bash_commands_prompt(config)
    
    agent = Agent(
        name="chat-agent",
        model=model,
        tools=[bash_tool],
        instructions=f"""You are a helpful assistant. {bash_prompt}

    IMPORTANT RULES:
    - Answer questions directly from your knowledge whenever possible
    - ONLY use bash tool when: the user explicitly asks to run a command, check system status, list files, read files, or perform a computation
    - NEVER use bash for: general knowledge questions (area, population, history, facts), math, definitions, explanations
    - If you don't know the answer, say so. Do not guess.
    - If the user asks something that can be answered without a command, answer it directly.""",
        tool_call_limit=5,
        add_session_state_to_context=True,
        add_history_to_context=True,
        stream=False,
        debug_mode=False,
    )
    return agent


# --- API Routes ---
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "agno": AGNO_AVAILABLE})


@app.route("/chat", methods=["POST"])
def chat():
    """Process a chat message through the Agno agent.

    Expected JSON body: {"messages": [{"role": "user"|"assistant", "content": "..."}]}
    Returns: {"text": "...", "toolOutputs": [...]}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        # Support both new messages format and legacy prompt field
        messages = data.get("messages", [])
        if not messages:
            # Legacy: fall back to single prompt field
            prompt = data.get("prompt", "")
            if not prompt.strip():
                return jsonify({"error": "Prompt cannot be empty"}), 400
            messages = [{"role": "user", "content": prompt}]
        else:
            # Validate at least one message exists
            last = messages[-1]["content"] if messages else ""
            if not last.strip():
                return jsonify({"error": "Prompt cannot be empty"}), 400

        # Build full conversation from all messages
        conversation_parts = []
        for m in messages:
            role_label = "User" if m["role"] == "user" else "Assistant"
            conversation_parts.append(f"{role_label}: {m['content']}")
        full_conversation = "\n".join(conversation_parts)

        agent = create_agent()

        # Pass full conversation as input so the model sees prior context
        result = agent.run(input=full_conversation)

        # Debug: show the full message history sent to LLM
        print("=== FULL LLM CONTEXT ===", flush=True)
        if hasattr(result, "messages") and result.messages:
            for i, msg in enumerate(result.messages):
                role = getattr(msg, "role", "unknown")
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    content = [{"type": type(c).__name__, "text": str(getattr(c, "text", ""))[:200]} for c in content]
                print(f"[{i}] role={role} content={repr(content)}", flush=True)
        print("=== END CONTEXT ===", flush=True)

        # Extract final text response from assistant messages
        text = ""
        if hasattr(result, "content") and result.content:
            text = str(result.content)
        elif hasattr(result, "messages") and result.messages:
            for msg in reversed(result.messages):
                if getattr(msg, "role", None) == "assistant":
                    content = msg.content
                    if isinstance(content, list):
                        text = " ".join(
                            c.text for c in content if hasattr(c, "text")
                        )
                    elif isinstance(content, str):
                        text = content
                    break

        # Extract tool call results from messages with role='tool'
        tool_outputs = []
        if hasattr(result, "messages") and result.messages:
            for msg in result.messages:
                if getattr(msg, "role", None) == "tool":
                    content = msg.content
                    if isinstance(content, str):
                        try:
                            tool_outputs.append(json.loads(content))
                        except (json.JSONDecodeError, TypeError):
                            tool_outputs.append({"stdout": content, "stderr": ""})
                    elif isinstance(content, dict):
                        tool_outputs.append(content)
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, str):
                                try:
                                    tool_outputs.append(json.loads(item))
                                except (json.JSONDecodeError, TypeError):
                                    pass
                            elif isinstance(item, dict):
                                tool_outputs.append(item)

        # Suppress LLM text response when we have tool outputs —
        # the tool cards already show the full output (matches vercel-ai)
        if tool_outputs:
            text = ""

        return jsonify({"text": text, "toolOutputs": tool_outputs})

    except RuntimeError as e:
        return jsonify({"error": str(e), "text": "", "toolOutputs": []}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "text": "", "toolOutputs": []}), 500


if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", 8081))
    print(f"Starting Agno Agent Service on http://localhost:{port}")
    print(f"Config: {CONFIG_PATH}")
    print(f"Agno available: {AGNO_AVAILABLE}")
    app.run(host="0.0.0.0", port=port, debug=False)

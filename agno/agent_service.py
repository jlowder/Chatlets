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
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# Try importing agno, fall back gracefully
try:
    from agno.agent import Agent
    from agno.models.openai.like import OpenAILike
    from agno.models.message import Message as AgnoMessage
    AGNO_AVAILABLE = True
except ImportError as e:
    AGNO_AVAILABLE = False
    AgnoMessage = None
    print(f"WARNING: agno not installed or import failed: {e}")
    print("Install with: pip install -r requirements.txt")

app = Flask(__name__)
CORS(app)

# --- Configuration ---


def load_config():
    """Load LLM and tool configuration using shared config loader."""
    return load_chatlets_config()


# --- Bash Tool ---
ALLOW_LIST = ["ls", "pwd"]
ALLOW_ALL = False


def bash_tool(command: str, run_context=None) -> str:
    """Execute a bash/shell command.

    NEVER use this tool for general knowledge, factual questions, geography, population, weather, math, definitions, explanations, or questions that can be answered from memory.
    ONLY call this tool when the user explicitly asks to run a shell/terminal command, check local system status, list local files, or execute a local file.
    Do NOT attempt to run curl or network commands to lookup factual answers.
    """
    import shlex
    # Allow list check
    global ALLOW_LIST, ALLOW_ALL
    cfg = load_config()
    ALLOW_LIST = cfg.get("allowList", ["ls", "pwd"])
    ALLOW_ALL = cfg.get("allowAll", False)

    cmd = command.strip().strip('"').strip("'").strip()
    if not cmd:
        return json.dumps(
            {"error": "Empty command", "stdout": "", "stderr": ""}
        )

    try:
        args = shlex.split(cmd)
    except Exception as e:
        return json.dumps(
            {"error": f"Failed to parse command: {str(e)}", "stdout": "", "stderr": ""}
        )

    if not args:
        return json.dumps(
            {"error": "Empty command", "stdout": "", "stderr": ""}
        )

    base_cmd = args[0]
    if base_cmd not in ALLOW_LIST and not ALLOW_ALL:
        return json.dumps(
            {"error": f"Command '{base_cmd}' not allowed", "stdout": "", "stderr": ""}
        )

    try:
        result = subprocess.run(
            args, shell=False, capture_output=True, text=True, timeout=30
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
    - DO NOT use the bash tool under any circumstances unless the user explicitly requested a terminal/shell command to be run (e.g., 'run ls', 'execute pwd').
    - Answer questions directly from your internal knowledge whenever possible.
    - NEVER use the bash tool for: general knowledge, geography, population, weather, history, facts, math, definitions, or explanations.
    - Questions like "What's the capital of India?" or "What's its population?" or "How is the weather?" are general knowledge/factual questions. You MUST answer them directly from your knowledge. DO NOT run curl or any web/shell command to look them up.
    - If the user asks a question that can be answered without executing a shell command, you MUST answer it directly and MUST NOT call the bash tool.
    - If you don't know the answer, say so. Do not guess and do not use tools to find out.""",
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

        if not AGNO_AVAILABLE:
            raise RuntimeError("agno package is not installed. Run: pip install -r requirements.txt")

        # Convert messages format to list of Agno Message objects
        agno_messages = []
        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content")
            tool_outputs_list = m.get("toolOutputs")

            if role == "assistant" and tool_outputs_list:
                # Map nested toolOutputs to structured tool_calls and tool messages
                tool_calls = []
                tool_messages = []
                for t_idx, tout in enumerate(tool_outputs_list):
                    tool_call_id = f"call_{idx}_{t_idx}"
                    tool_calls.append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "bash_tool",
                            "arguments": json.dumps({"command": tout.get("command", "")})
                        }
                    })
                    tool_messages.append(AgnoMessage(
                        role="tool",
                        tool_call_id=tool_call_id,
                        content=json.dumps(tout)
                    ))
                agno_messages.append(AgnoMessage(
                    role="assistant",
                    content=content or None,
                    tool_calls=tool_calls
                ))
                agno_messages.extend(tool_messages)
            else:
                agno_messages.append(AgnoMessage(role=role, content=content))

        agent = create_agent()

        # Pass structured message list as input so the model sees proper conversation history
        result = agent.run(input=agno_messages)

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

        # Find the last input message in the result messages to identify newly generated messages
        last_input_msg = agno_messages[-1] if agno_messages else None
        last_input_idx = -1
        if last_input_msg and hasattr(result, "messages") and result.messages:
            for i, msg in enumerate(result.messages):
                if msg is last_input_msg or (
                    getattr(msg, "role", None) == last_input_msg.role and
                    getattr(msg, "content", None) == last_input_msg.content
                ):
                    last_input_idx = i

        new_messages = result.messages[last_input_idx + 1:] if last_input_idx != -1 and hasattr(result, "messages") else (result.messages if hasattr(result, "messages") else [])

        # Extract final text response from assistant messages
        text = ""
        if hasattr(result, "content") and result.content:
            text = str(result.content)
        elif new_messages:
            for msg in reversed(new_messages):
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
        if new_messages:
            for msg in new_messages:
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
    print("Config: Shared Config Loader")
    print(f"Agno available: {AGNO_AVAILABLE}")
    app.run(host="0.0.0.0", port=port, debug=False)

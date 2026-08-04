"""
CrewAI Agent Service - Flask HTTP server that runs a CrewAI agent with bash tool execution.
This service is called by the Next.js API route.

Usage:
    python agent_service.py

Runs on http://localhost:5000
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

# Try importing crewai, fall back gracefully
try:
    from crewai import Agent, Task, Crew, LLM
    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field
    from typing import Type
    
    CREWAI_AVAILABLE = True
except ImportError as e:
    CREWAI_AVAILABLE = False
    print(f"WARNING: crewai not installed or import failed: {e}")
    print("Install with: pip install -r requirements.txt")

app = Flask(__name__)
CORS(app)

# Module-level capture for tool outputs
_captured_tool_outputs = []

# --- Configuration ---


def load_config():
    """Load LLM and tool configuration using shared config loader."""
    return load_chatlets_config()


# --- Bash Tool ---
class BashToolInput(BaseModel):
    """Input schema for BashTool."""
    command: str = Field(description="The bash/shell command to execute")


class BashTool(BaseTool):
    """A CrewAI tool that executes bash commands with allow-list enforcement."""
    
    name: str = "bash"
    description: str = "Execute a bash command. ONLY use when the user explicitly asks to run a shell command, check system info, or list files."
    args_schema: Type[BaseModel] = BashToolInput
    
    def _run(self, command: str) -> str:
        """Execute a bash command on the server."""
        import shlex
        # Allow list check
        cfg = load_config()
        allow_list = cfg.get("allowList", ["ls", "pwd"])
        allow_all = cfg.get("allowAll", False)
        
        cmd = command.strip().strip('"').strip("'").strip()
        if not cmd:
            output = {"error": "Empty command", "stdout": "", "stderr": ""}
            _captured_tool_outputs.append(output)
            return json.dumps(output)

        try:
            args = shlex.split(cmd)
        except Exception as e:
            output = {"error": f"Failed to parse command: {str(e)}", "stdout": "", "stderr": ""}
            _captured_tool_outputs.append(output)
            return json.dumps(output)

        if not args:
            output = {"error": "Empty command", "stdout": "", "stderr": ""}
            _captured_tool_outputs.append(output)
            return json.dumps(output)

        base_cmd = args[0]
        if base_cmd not in allow_list and not allow_all:
            output = {
                "error": f"Command '{base_cmd}' not allowed",
                "stdout": "",
                "stderr": ""
            }
            _captured_tool_outputs.append(output)
            return json.dumps(output)
        
        try:
            result = subprocess.run(
                args, shell=False, capture_output=True, text=True, timeout=30
            )
            output = {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
            if result.returncode != 0:
                output["error"] = f"Command exited with code {result.returncode}"
            _captured_tool_outputs.append(output)
            return json.dumps(output)
        except subprocess.TimeoutExpired:
            output = {"error": "Command timed out (30s)", "stdout": "", "stderr": ""}
            _captured_tool_outputs.append(output)
            return json.dumps(output)
        except Exception as e:
            output = {"error": str(e), "stdout": "", "stderr": ""}
            _captured_tool_outputs.append(output)
            return json.dumps(output)


# --- Agent Factory ---
def create_agent():
    """Create and return a CrewAI Agent configured with the bash tool."""
    cfg = load_config()
    
    if not CREWAI_AVAILABLE:
        raise RuntimeError("crewai package is not installed. Run: pip install -r requirements.txt")
    
    # Create LLM instance - CrewAI 2.x requires LLM class
    llm = LLM(
        model=f"openai/{cfg.get('model', 'Qwen3.6-35B-A3B-MLX-8bit')}",
        base_url=cfg.get("baseURL", "http://localhost:8080/v1"),
        api_key=cfg.get("apiKey", "example"),
    )
    
    # Create the bash tool
    bash_tool = BashTool()
    
    # Build dynamic bash instructions from shared config
    config = load_chatlets_config()
    bash_prompt = get_bash_commands_prompt(config)
    allow_all = config.get("allowAll", False)
    allow_list = config.get("allowList", [])
    if allow_all:
        goal = "Answer user questions directly using your knowledge. Use the bash tool to run any shell command when needed."
    else:
        command_list = ", ".join(allow_list) if allow_list else "none"
        goal = f"Answer user questions directly using your knowledge. Only use the bash tool to run these commands: {command_list}."
    
    # Create the agent with the LLM instance
    agent = Agent(
        role="Assistant",
        goal=goal,
        backstory=f"""You are a helpful assistant. {bash_prompt}

    IMPORTANT RULES:
    - Answer questions directly from your knowledge whenever possible
    - ONLY use bash tool when: the user explicitly asks to run a command, check system status, list files, read files, or perform a computation
    - NEVER use bash for: general knowledge questions (area, population, history, facts), math, definitions, explanations
    - If you don't know the answer, say so. Do not guess.
    - If the user asks something that can be answered without a command, answer it directly.""",
        llm=llm,
        tools=[bash_tool],
        max_iter=5,
        verbose=False,
    )
    
    return agent


# --- API Routes ---
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "crewai": CREWAI_AVAILABLE})


@app.route("/chat", methods=["POST"])
def chat():
    """Process a chat message through the CrewAI agent.

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

        # Build conversation context from prior messages
        context_parts = []
        for m in messages[:-1]:  # All messages except the last (current) one
            role_label = "user" if m["role"] == "user" else "assistant"
            context_parts.append(f"{role_label}: {m['content']}")
        context = "\n".join(context_parts) if context_parts else None

        # The last message is the current prompt
        last_prompt = messages[-1]["content"]

        # Build task description with conversation context
        if context:
            task_description = f"Previous conversation:\n{context}\n\nCurrent question: {last_prompt}"
        else:
            task_description = last_prompt

        agent = create_agent()

        # Reset captured outputs before this run
        _captured_tool_outputs.clear()

        # Create a task from the prompt (with context if available)
        task = Task(
            description=task_description,
            expected_output="A response to the user's request, with tool results if needed.",
            agent=agent,
        )
        
        # Assemble the crew and execute
        crew = Crew(
            agents=[agent],
            tasks=[task],
            verbose=False,
        )
        
        result = crew.kickoff()
        
        # Extract text response
        text = ""
        if hasattr(result, 'output') and result.output:
            text = str(result.output)
        elif hasattr(result, 'raw') and result.raw:
            text = str(result.raw)
        
        # Extract tool outputs from captured list
        tool_outputs = list(_captured_tool_outputs)
        _captured_tool_outputs.clear()
        
        # Suppress LLM text response when we have tool outputs
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
    port = int(os.environ.get("CREWAI_PORT", 5000))
    print(f"Starting CrewAI Agent Service on http://localhost:{port}")
    print("Config: Shared Config Loader")
    print(f"CrewAI available: {CREWAI_AVAILABLE}")
    app.run(host="0.0.0.0", port=port, debug=False)

import os
import json
import subprocess
import asyncio
import sys
import hashlib
from pathlib import Path
from typing import Annotated, Sequence
from flask import Flask, request, jsonify
from flask_cors import CORS
from pydantic import Field
from agent_framework import Agent, FunctionInvocationContext, tool, Message
from agent_framework.openai import OpenAIChatClient
from agent_framework._sessions import AgentSession

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

app = Flask(__name__)
CORS(app)

AGENT_PORT = int(os.environ.get("AGENT_PORT", 5006))


def load_config() -> dict:
    """Load LLM and tool configuration using shared config loader."""
    return load_chatlets_config()


class BashTool:
    """Bash execution tool with allow list and timeout."""

    def __init__(self, allow_list: list, allow_all: bool):
        self.allow_list = allow_list
        self.allow_all = allow_all

    def execute(self, command: str) -> str:
        """Execute a bash command with allow-list enforcement and timeout."""
        import shlex
        cmd = command.strip().strip('"').strip("'").strip()
        if not cmd:
            return json.dumps({"error": "Empty command"})

        try:
            args = shlex.split(cmd)
        except Exception as e:
            return json.dumps({"error": f"Failed to parse command: {str(e)}"})

        if not args:
            return json.dumps({"error": "Empty command"})

        cmd_name = args[0]

        if not self.allow_all and cmd_name not in self.allow_list:
            return json.dumps({"error": f"Command '{cmd_name}' not allowed"})

        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = {"stdout": result.stdout}
            if result.stderr:
                output["stderr"] = result.stderr
            if result.returncode != 0:
                output["error"] = result.stderr or f"Exit code {result.returncode}"
            return json.dumps(output)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Command timed out"})
        except Exception as e:
            return json.dumps({"error": str(e)})


def bash_execute_fn(command: str) -> str:
    """Wrapper function for the bash tool."""
    cfg = load_config()
    tool_instance = BashTool(
        allow_list=cfg.get("allowList", ["ls", "pwd"]),
        allow_all=cfg.get("allowAll", False)
    )
    return tool_instance.execute(command)


@tool(approval_mode="never_require")
def bash(command: Annotated[str, Field(description="The shell command to execute")]) -> str:
    """Execute a shell command. Only use for explicit command requests."""
    return bash_execute_fn(command)


# Module-level caches for agent and sessions
_agent_cache = None
_last_config = None
_session_cache = {}


def get_agent() -> Agent:
    """Retrieve or create the cached Agent instance based on current config."""
    global _agent_cache, _last_config
    cfg = load_config()

    # Check if the active configuration has changed
    config_key = (cfg.get("baseURL"), cfg.get("apiKey"), cfg.get("model"))
    if _agent_cache is None or _last_config != config_key:
        client = OpenAIChatClient(
            base_url=cfg["baseURL"],
            api_key=cfg["apiKey"],
            model=cfg["model"],
        )

        config = load_chatlets_config()
        bash_prompt = get_bash_commands_prompt(config)

        agent = client.as_agent(
            name="ChatletAgent",
            instructions=(
                f"You are a helpful assistant. {bash_prompt} "
                "Answer questions directly from your knowledge whenever possible. "
                "Do NOT use bash for general knowledge questions, math, definitions, "
                "explanations, or factual queries."
            ),
            tools=[bash],
        )
        _agent_cache = agent
        _last_config = config_key
        # Clear session cache when agent is recreated to avoid mismatch
        _session_cache.clear()

    return _agent_cache


def get_session_id(messages: list) -> str:
    """Generate a deterministic session ID from the first user message."""
    if not messages:
        return "default_session"
    first_msg = messages[0]
    content = first_msg.get("content", "")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_session(agent: Agent, session_id: str) -> AgentSession:
    """Retrieve or create a cached AgentSession on the server."""
    if session_id not in _session_cache:
        _session_cache[session_id] = agent.create_session(session_id=session_id)
    return _session_cache[session_id]


async def run_agent(messages: list) -> dict:
    """Run the agent with the given messages and return the result."""
    agent = get_agent()
    session_id = get_session_id(messages)
    session = get_session(agent, session_id)

    # Convert all but the last message to MAF Message objects for session history
    formatted_history = []
    for m in messages[:-1]:
        formatted_history.append(Message(role=m["role"], contents=[m["content"]]))

    # Synchronize the session's in-memory history with the client's message history
    session.state.setdefault("in_memory", {})["messages"] = formatted_history

    # The last message is the current prompt
    last_msg = messages[-1]
    current_prompt = Message(role=last_msg["role"], contents=[last_msg["content"]])

    # Run the agent natively with current prompt and the session
    result = await agent.run(current_prompt, session=session)

    # Use public .to_dict() and .text property to avoid private introspection coupling
    res_dict = result.to_dict()
    text = result.text or ""

    # Extract tool outputs using public to_dict serialization format
    tool_outputs = []
    messages_data = res_dict.get("messages", [])
    for msg in messages_data:
        contents = msg.get("contents", [])
        for content in contents:
            if content.get("type") == "function_result":
                raw_result = content.get("result")
                if raw_result:
                    try:
                        parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
                        tool_outputs.append({
                            "stdout": parsed.get("stdout"),
                            "stderr": parsed.get("stderr"),
                            "error": parsed.get("error"),
                        })
                    except (json.JSONDecodeError, AttributeError):
                        pass

    # Suppress text when tools were used (the prose is redundant with toolOutputs)
    return {
        "text": "" if tool_outputs else text,
        "toolOutputs": tool_outputs,
    }


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    """Process a chat message through the Microsoft Agent Framework agent.

    Expected JSON body: {"messages": [{"role": "user"|"assistant", "content": "..."}]}
    Returns: {"text": "...", "toolOutputs": [...]}
    """
    try:
        data = request.get_json()

        # Support both new messages format and legacy prompt format
        messages = data.get("messages", [])
        if not messages and "prompt" in data:
            messages = [{"role": "user", "content": data["prompt"]}]

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        # Run the agent asynchronously
        result = asyncio.run(run_agent(messages))

        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"Starting Microsoft Agent Framework Agent Service on http://localhost:{AGENT_PORT}")
    print("Config: Shared Config Loader")
    app.run(host="0.0.0.0", port=AGENT_PORT)

import os
import json
import subprocess
import asyncio
import sys
from pathlib import Path
from typing import Annotated
from flask import Flask, request, jsonify
from flask_cors import CORS
from pydantic import Field
from agent_framework import Agent, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIChatClient

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

app = Flask(__name__)
CORS(app)

CONFIG_PATH = Path(__file__).parent / "config.json"
AGENT_PORT = int(os.environ.get("AGENT_PORT", 5006))


def load_config() -> dict:
    """Load LLM and tool configuration from config.json."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


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


async def run_agent(messages: list) -> dict:
    """Run the agent with the given messages and return the result."""
    cfg = load_config()

    # Create client with OpenAI-compatible settings
    client = OpenAIChatClient(
        base_url=cfg["baseURL"],
        api_key=cfg["apiKey"],
        model=cfg["model"],
    )

    # Build dynamic bash instructions from shared config
    config = load_chatlets_config()
    bash_prompt = get_bash_commands_prompt(config)

    # Create agent with tools
    agent = client.as_agent(
        name="ChatletAgent",
        instructions=f"You are a helpful assistant. {bash_prompt} Answer questions directly from your knowledge whenever possible. Do NOT use bash for general knowledge questions, math, definitions, explanations, or factual queries.",
        tools=[bash],
    )

    # Build conversation history
    user_messages = []
    for m in messages:
        if m["role"] == "user":
            user_messages.append(f"User: {m['content']}")
        elif m["role"] == "assistant":
            user_messages.append(f"Assistant: {m['content']}")

    # The last message is the current prompt
    history = "\n".join(user_messages[:-1]) if len(user_messages) > 1 else ""
    current_prompt = user_messages[-1].replace("User: ", "") if user_messages else ""

    if history:
        full_prompt = f"Previous conversation:\n{history}\n\n{current_prompt}"
    else:
        full_prompt = current_prompt

    # Run the agent
    result = await agent.run(full_prompt)

    # Extract tool outputs and text from result.messages
    tool_outputs = []
    text = ""
    for msg in result.messages:
        contents = getattr(msg, 'contents', None) if hasattr(msg, 'contents') else None
        if not contents:
            continue
        for ci in contents:
            ci_type = getattr(ci, 'type', None)
            if ci_type == 'function_result':
                # Tool output: parse the result attribute as JSON
                raw_result = getattr(ci, 'result', None)
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
            elif ci_type == 'text':
                # Response text — keep last non-empty one
                ci_text = getattr(ci, 'text', None)
                if ci_text:
                    text = ci_text

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
    print(f"Config: {CONFIG_PATH}")
    app.run(host="0.0.0.0", port=AGENT_PORT)

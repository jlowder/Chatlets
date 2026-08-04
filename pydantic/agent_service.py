"""
Pydantic AI Agent Service - Flask HTTP server that runs a Pydantic AI agent with bash tool execution.
This service is called by the Next.js API route.

Usage:
    python agent_service.py

Runs on http://localhost:5008
"""

import json
import subprocess
import asyncio
import sys
import os
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# Pydantic AI imports
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

app = Flask(__name__)
CORS(app)

CONFIG_PATH = Path(__file__).parent / "config.json"
AGENT_PORT = int(__import__("os").environ.get("AGENT_PORT", 5008))


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


class ChatDeps:
    def __init__(self, allow_list: set = None, allow_all: bool = False):
        self.allow_list = allow_list or set()
        self.allow_all = allow_all


async def bash_tool(ctx: RunContext[ChatDeps], command: str) -> str:
    """Execute a bash command respecting the allow list."""
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

    if not ctx.deps.allow_all and cmd_name not in ctx.deps.allow_list:
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


def create_agent():
    cfg = load_config()
    model = OpenAIChatModel(
        cfg["model"],  # First positional arg, not model_id=
        provider=OpenAIProvider(
            base_url=cfg["baseURL"],
            api_key=cfg["apiKey"],
        ),
    )

    # Build dynamic bash instructions from shared config
    config = load_chatlets_config()
    bash_prompt = get_bash_commands_prompt(config)

    agent = Agent[ChatDeps, str](
        model,
        deps_type=ChatDeps,
        system_prompt=(
            f"You are a helpful assistant. {bash_prompt} "
            "The ONLY tool available is 'bash' for executing shell commands. "
            "Do NOT call 'bash' for general knowledge questions, math, definitions, explanations, or factual queries. "
            "Do NOT invent or call tools that are not available (e.g., google_search, web_search, etc.). "
            "If you don't have a tool for something, just answer directly from your knowledge."
        ),
    )

    # Register the bash tool
    agent.tool(bash_tool)

    return agent


async def run_agent(messages: list) -> dict:
    """Run the agent and extract tool outputs."""
    cfg = load_config()
    agent = create_agent()

    # Build conversation context from messages
    user_messages = []
    for m in messages:
        if m["role"] == "user":
            user_messages.append(f"User: {m['content']}")
        elif m["role"] == "assistant":
            user_messages.append(f"Assistant: {m['content']}")

    # The last message is the current prompt
    history = "\n".join(user_messages[:-1]) if len(user_messages) > 1 else ""
    current_prompt = user_messages[-1].replace("User: ", "") if user_messages else ""

    full_prompt = f"Previous conversation:\n{history}\n\n{current_prompt}" if history else current_prompt

    deps = ChatDeps(
        allow_list=set(cfg.get("allowList", ["ls", "pwd"])),
        allow_all=cfg.get("allowAll", False)
    )

    # Run the agent
    result = await agent.run(full_prompt, deps=deps)

    # Extract tool outputs from all_messages()
    tool_outputs = []
    for msg in result.all_messages():
        for part in msg.parts:
            if hasattr(part, 'part_kind') and part.part_kind == 'tool-return':
                try:
                    content = json.loads(part.content) if isinstance(part.content, str) else part.content
                    tool_outputs.append({
                        "stdout": content.get("stdout"),
                        "stderr": content.get("stderr"),
                        "error": content.get("error"),
                    })
                except (json.JSONDecodeError, AttributeError):
                    pass

    return {
        "text": "" if tool_outputs else result.output,
        "toolOutputs": tool_outputs,
    }


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()

        messages = data.get("messages", [])
        if not messages and "prompt" in data:
            messages = [{"role": "user", "content": data["prompt"]}]

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        result = asyncio.run(run_agent(messages))

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"Starting Pydantic AI Agent Service on http://localhost:{AGENT_PORT}")
    print(f"Config: {CONFIG_PATH}")
    app.run(host="0.0.0.0", port=AGENT_PORT)

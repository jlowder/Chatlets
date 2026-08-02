import os
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# LlamaIndex imports
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, step
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.tools import FunctionTool

app = Flask(__name__)
CORS(app)

CONFIG_PATH = Path(__file__).parent / "config.json"
AGENT_PORT = int(os.environ.get("AGENT_PORT", 5004))


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
        cmd = command.strip()
        cmd_name = cmd.split()[0] if cmd else ""

        if not self.allow_all and cmd_name not in self.allow_list:
            return json.dumps({"error": f"Command '{cmd_name}' not allowed"})

        try:
            result = subprocess.run(
                cmd,
                shell=True,
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
    """Function wrapper for LlamaIndex FunctionTool."""
    cfg = load_config()
    tool = BashTool(
        allow_list=cfg.get("allowList", ["ls", "pwd"]),
        allow_all=cfg.get("allowAll", False)
    )
    return tool.execute(command)


# LlamaIndex tool instance
bash_tool = FunctionTool.from_defaults(
    fn=bash_execute_fn,
    name="bash",
    description="Execute a shell command. Only use for explicit command requests, NOT for general knowledge, math, definitions, or factual queries."
)


class InputEvent(StartEvent):
    """Custom event for user input."""
    messages: List[Dict[str, str]]


class ToolCallEvent(StartEvent):
    """Custom event for tool call results."""
    tool_result: str
    command: str


class LlamaIndexWorkflow(Workflow):
    """LlamaIndex Workflow-based agent with event-driven flow."""

    @step
    async def handle_llm_input(self, ev: StartEvent) -> StopEvent:
        """Main step: prepare message history and get LLM response."""
        messages = ev.messages if hasattr(ev, 'messages') else []
        prompt = messages[-1]["content"] if messages else ""
        history = messages[:-1]

        # Build system message with dynamic bash instructions from shared config
        config = load_chatlets_config()
        bash_prompt = get_bash_commands_prompt(config)
        system_msg = ChatMessage(
            role="system",
            content=f"You are a helpful assistant. {bash_prompt} Answer questions directly from your knowledge whenever possible."
        )

        # Build history messages
        user_messages = []
        for m in history:
            if m["role"] == "user":
                user_messages.append(ChatMessage(role="user", content=m["content"]))
            elif m["role"] == "assistant":
                user_messages.append(ChatMessage(role="assistant", content=m["content"]))

        user_messages.append(ChatMessage(role="user", content=prompt))

        # Get LLM response
        llm = self.ctx.get("llm")
        response = await llm.astream_chat(system_msg, user_messages)

        full_response = ""
        async for delta in response:
            if hasattr(delta, 'message') and delta.message.content:
                full_response += delta.message.content

        return StopEvent(result={"text": full_response})


def get_agent_response(messages: list) -> dict:
    """Get response from the workflow."""
    cfg = load_config()

    # Initialize LLM
    llm = OpenAILike(
        id=cfg["model"],
        api_key=cfg["apiKey"],
        base_url=cfg["baseURL"],
    )

    # Create and run workflow
    workflow = LlamaIndexWorkflow(timeout=120)
    result = workflow.run(messages=messages, llm=llm)

    return {
        "text": result.get("text", ""),
        "toolOutputs": []
    }


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    """Process a chat message through the LlamaIndex workflow.

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

        result = get_agent_response(messages)

        # Suppress text when tool outputs exist
        if result.get("toolOutputs"):
            result["text"] = ""

        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"Starting LlamaIndex Workflow Agent Service on http://localhost:{AGENT_PORT}")
    print(f"Config: {CONFIG_PATH}")
    app.run(host="0.0.0.0", port=AGENT_PORT)

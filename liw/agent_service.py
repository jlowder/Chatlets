import os
import json
import subprocess
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Union

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# LlamaIndex imports
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, step, Context, Event
from llama_index.core.llms import ChatMessage
from llama_index.core.llms.llm import ToolSelection
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.tools import FunctionTool
from flask import Flask, request, jsonify
from flask_cors import CORS

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


class InputEvent(Event):
    """Event carrying chat history for LLM processing."""
    input: List[ChatMessage]


class ToolCallEvent(Event):
    """Event carrying tool calls to be executed."""
    tool_calls: List[ToolSelection]


class StreamEvent(Event):
    """Event for streaming response deltas."""
    delta: str


class LlamaIndexWorkflow(Workflow):
    """LlamaIndex Workflow-based agent with event-driven flow."""

    def __init__(self, *args, llm=None, tools=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = llm
        self.tools = tools or []

    @step
    async def prepare_chat_history(self, ctx: Context, ev: StartEvent) -> InputEvent:
        """Entry point: initialize memory and build chat history."""
        messages = getattr(ev, "messages", [])

        memory = await ctx.store.get("memory", default=None)
        if not memory:
            memory = ChatMemoryBuffer.from_defaults(llm=self.llm)
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                memory.put(ChatMessage(role=role, content=content))
            await ctx.store.set("memory", memory)

        chat_history = memory.get()
        return InputEvent(input=chat_history)

    @step
    async def handle_llm_input(self, ctx: Context, ev: InputEvent) -> Union[ToolCallEvent, StopEvent]:
        """Call LLM with chat history + tools. Returns ToolCallEvent or StopEvent."""
        config = load_chatlets_config()
        bash_prompt = get_bash_commands_prompt(config)
        system_msg = ChatMessage(
            role="system",
            content=f"You are a helpful assistant. {bash_prompt} Answer questions directly from your knowledge whenever possible."
        )

        chat_history = [system_msg] + ev.input

        # Call achat_with_tools asynchronously
        response = await self.llm.achat_with_tools(
            self.tools, chat_history=chat_history
        )

        if response and response.message:
            memory = await ctx.store.get("memory")
            memory.put(response.message)
            await ctx.store.set("memory", memory)

        # Robustly extract tool calls from the response
        tool_calls = []
        if response:
            if hasattr(self.llm, "get_tool_calls_from_response"):
                try:
                    tool_calls = self.llm.get_tool_calls_from_response(response, error_on_no_tool_call=False)
                except Exception:
                    pass
            if not tool_calls and response.message and "tool_calls" in response.message.additional_kwargs:
                raw_calls = response.message.additional_kwargs["tool_calls"]
                for rc in raw_calls:
                    function = rc.get("function", {})
                    arguments = function.get("arguments", "{}")
                    if isinstance(arguments, str):
                        try:
                            kwargs_dict = json.loads(arguments)
                        except Exception:
                            kwargs_dict = {}
                    else:
                        kwargs_dict = arguments
                    tool_calls.append(ToolSelection(
                        tool_id=rc.get("id"),
                        tool_name=function.get("name"),
                        tool_kwargs=kwargs_dict
                    ))

        if not tool_calls:
            text_response = response.message.content if response and response.message else ""
            tool_outputs = await ctx.store.get("tool_outputs", default=[])
            return StopEvent(result={"text": text_response, "tool_outputs": tool_outputs})

        return ToolCallEvent(tool_calls=tool_calls)

    @step
    async def handle_tool_calls(self, ctx: Context, ev: ToolCallEvent) -> InputEvent:
        """Execute tool calls and return updated chat history."""
        tools_by_name = {tool.metadata.get_name(): tool for tool in self.tools}
        tool_msgs = []

        # Retrieve or initialize tool outputs in ctx.store for API response
        tool_outputs = await ctx.store.get("tool_outputs", default=[])

        for tool_call in ev.tool_calls:
            tool = tools_by_name.get(tool_call.tool_name)
            if tool:
                tool_output = tool(**tool_call.tool_kwargs)
                content = tool_output.content
            else:
                content = f"Tool {tool_call.tool_name} does not exist"
                tool_output = None

            if tool_output:
                try:
                    tool_output_dict = json.loads(content)
                except Exception:
                    tool_output_dict = {"error": f"Invalid JSON output: {content}", "stdout": content}
            else:
                tool_output_dict = {"error": content}

            tool_outputs.append(tool_output_dict)

            tool_msgs.append(ChatMessage(
                role="tool",
                content=content,
                additional_kwargs={
                    "tool_id": tool_call.tool_id,
                    "name": tool_call.tool_name,
                }
            ))

        await ctx.store.set("tool_outputs", tool_outputs)

        memory = await ctx.store.get("memory")
        for msg in tool_msgs:
            memory.put(msg)
        await ctx.store.set("memory", memory)

        return InputEvent(input=memory.get())


async def run_workflow_async(messages: list, llm: OpenAILike) -> dict:
    """Run workflow asynchronously and return result."""
    workflow = LlamaIndexWorkflow(llm=llm, tools=[bash_tool], timeout=120)
    result = await workflow.run(messages=messages)

    text = result.get("text", "")
    tool_outputs = result.get("tool_outputs", [])

    return {
        "text": text,
        "toolOutputs": tool_outputs
    }


def get_agent_response(messages: list) -> dict:
    """Get response from the workflow."""
    cfg = load_config()

    # Initialize LLM with correct parameter mappings and force Chat/Tool capabilities
    llm = OpenAILike(
        model=cfg["model"],
        api_key=cfg["apiKey"],
        api_base=cfg["baseURL"],
        is_chat_model=True,
        is_function_calling_model=True
    )

    return asyncio.run(run_workflow_async(messages, llm))


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

"""
Smolagents Agent Service - Flask HTTP server that runs a smolagents ToolCallingAgent with bash tool execution.
This service is called by the Next.js API route.

Usage:
    python agent_service.py

Runs on http://localhost:5010
"""

import json
import subprocess
import asyncio
import sys
import os
import io
import time
import contextvars
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

_current_tool_outputs = contextvars.ContextVar("current_tool_outputs", default=None)

# Add parent directory to path for shared config loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.config_loader import load_chatlets_config, get_bash_commands_prompt

# Smolagents imports
from smolagents import ToolCallingAgent, LiteLLMModel, tool

app = Flask(__name__)
CORS(app)

# Increase werkzeug server timeout (avoid HTTP 503 on slow LLM responses)
import werkzeug.serving
werkzeug.serving.WSGIRequestHandler.log_request = lambda self, format, *args: None

AGENT_PORT = int(__import__("os").environ.get("AGENT_PORT", 5010))


def load_config():
    return load_chatlets_config()


@tool
def bash_tool(command: str) -> str:
    """Execute a bash command on the server. ONLY 'ls' and 'pwd' commands are allowed.

    CRITICAL: This tool should ONLY be used when the user explicitly asks to run a shell command.
    Do NOT use for greetings, facts, definitions, math, explanations, or general knowledge.
    Do NOT use for 'echo', 'cat', or any command other than 'ls' or 'pwd'.

    Args:
        command: The shell command to execute. Only 'ls' and 'pwd' are permitted.
    """
    cfg = load_config()

    cmd = command.strip().strip('"').strip("'").strip()
    cmd_name = cmd.split()[0] if cmd else ""

    if not cfg.get("allowAll", False) and cmd_name not in cfg.get("allowList", ["ls", "pwd"]):
        err_msg = f"Command '{cmd_name}' not allowed"
        try:
            outputs_list = _current_tool_outputs.get()
            if outputs_list is not None:
                outputs_list.append({"error": err_msg})
        except LookupError:
            pass
        return json.dumps({"error": err_msg})

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

        try:
            outputs_list = _current_tool_outputs.get()
            if outputs_list is not None:
                outputs_list.append({
                    "stdout": output.get("stdout"),
                    "stderr": output.get("stderr"),
                    "error": output.get("error"),
                })
        except LookupError:
            pass

        return json.dumps(output)
    except subprocess.TimeoutExpired:
        err_msg = "Command timed out"
        try:
            outputs_list = _current_tool_outputs.get()
            if outputs_list is not None:
                outputs_list.append({"error": err_msg})
        except LookupError:
            pass
        return json.dumps({"error": err_msg})
    except Exception as e:
        err_msg = str(e)
        try:
            outputs_list = _current_tool_outputs.get()
            if outputs_list is not None:
                outputs_list.append({"error": err_msg})
        except LookupError:
            pass
        return json.dumps({"error": err_msg})


def create_agent():
    cfg = load_config()
    model = LiteLLMModel(
        model_id=f"openai/{cfg['model']}",
        api_base=cfg["baseURL"],
        api_key=cfg["apiKey"],
        timeout=300.0,
        extra_body={"max_tokens": 4096},
    )
    
    agent = ToolCallingAgent(
        tools=[bash_tool],
        model=model,
        max_steps=2,
    )
    # Build dynamic bash instructions from shared config
    config = load_chatlets_config()
    bash_prompt = get_bash_commands_prompt(config)
    agent.prompt_templates["system_prompt"] = (
        f"You are a helpful assistant. {bash_prompt} "
        "Use the bash tool only when the user explicitly asks to run a command. "
        "Use bash for: 'run ls', 'execute pwd', 'run the command ls' etc. "
        "Answer knowledge questions directly without using tools. "
        "Only ls and pwd commands are allowed. All other commands will be rejected."
    )
    return agent


async def run_agent(messages: list) -> dict:
    """Run the agent and return the result."""
    import re
    
    agent = create_agent()
    
    # Reset state (defensive, public API)
    if hasattr(agent, 'reset'):
        agent.reset()
    
    # Build conversation context
    user_messages = []
    for m in messages:
        if m["role"] == "user":
            user_messages.append(f"User: {m['content']}")
        elif m["role"] == "assistant":
            # Skip error messages from retries
            if m["content"].startswith(("Error:", "Failed to", "try again", "Command 'echo'")):
                continue
            user_messages.append(f"Assistant: {m['content']}")
    
    history = "\n".join(user_messages[:-1]) if len(user_messages) > 1 else ""
    current_prompt = user_messages[-1].replace("User: ", "") if user_messages else ""
    full_prompt = f"Previous conversation:\n{history}\n\n{current_prompt}" if history else current_prompt
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    
    tool_outputs = []
    token = _current_tool_outputs.set(tool_outputs)

    try:
        result = agent.run(full_prompt)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        _current_tool_outputs.reset(token)
    
    # If any tool outputs were captured, return them (natural reasoning-loop autonomy)
    if tool_outputs:
        return {"text": "", "toolOutputs": tool_outputs}
    
    # Fallback: clean raw result
    answer = str(result) if result is not None else ""
    answer = re.sub(r'Thought:.*?(?=(Observation|Action:|$))', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'```python\s*.*?\s*```', '', answer, flags=re.DOTALL).strip()
    answer = re.sub(r'```.*?```', '', answer, flags=re.DOTALL).strip()
    
    return {"text": answer if answer else "I couldn't process that request.", "toolOutputs": []}




@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    start = time.time()
    print(f"\n[agent] /chat started at {time.strftime('%H:%M:%S')}", flush=True)
    try:
        data = request.get_json()

        messages = data.get("messages", [])
        if not messages and "prompt" in data:
            messages = [{"role": "user", "content": data["prompt"]}]

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        result = asyncio.run(run_agent(messages))

        elapsed = time.time() - start
        print(f"[agent] /chat completed in {elapsed:.1f}s", flush=True)

        return jsonify(result)
    except Exception as e:
        elapsed = time.time() - start
        print(f"[agent] /chat failed after {elapsed:.1f}s: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"Starting Smolagents Agent Service on http://localhost:{AGENT_PORT}")
    print("Config: Shared Config Loader")
    app.run(host="0.0.0.0", port=AGENT_PORT)

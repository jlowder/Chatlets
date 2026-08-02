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
import io
import time
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Smolagents imports
from smolagents import ToolCallingAgent, LiteLLMModel, tool

app = Flask(__name__)
CORS(app)

# Increase werkzeug server timeout (avoid HTTP 503 on slow LLM responses)
import werkzeug.serving
werkzeug.serving.WSGIRequestHandler.log_request = lambda self, format, *args: None

CONFIG_PATH = Path(__file__).parent / "config.json"
AGENT_PORT = int(__import__("os").environ.get("AGENT_PORT", 5010))


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


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
    agent.prompt_templates["system_prompt"] = (
        "You are a helpful assistant with access to a bash tool. "
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
    
    # Reset state
    if hasattr(agent, 'reset'):
        agent.reset()
    if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps'):
        agent.memory.steps.clear()
    
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
    
    try:
        result = agent.run(full_prompt)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    
    # Extract tool outputs from memory steps
    tool_outputs = []
    final_text = None
    tool_call_count = 0
    has_echo_fail = False
    has_real_tool = False
    
    try:
        steps = agent.memory.steps if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps') else []
        
        for step in steps:
            # Extract tool outputs
            if hasattr(step, 'tool_calls') and step.tool_calls:
                tool_call_count += 1
                for tc in step.tool_calls:
                    tc_name = getattr(tc, 'name', '') if hasattr(tc, 'name') else ''
                    if tc_name in ('bash', 'bash_tool'):
                        output = str(step.observations) if hasattr(step, 'observations') and step.observations else ''
                        try:
                            parsed = json.loads(output)
                            if isinstance(parsed, dict) and any(k in parsed for k in ('stdout', 'stderr', 'error')):
                                tool_outputs.append({
                                    "stdout": parsed.get("stdout"),
                                    "stderr": parsed.get("stderr"),
                                    "error": parsed.get("error"),
                                })
                                if "echo" in str(tc_name) or (isinstance(parsed.get("error"), str) and "echo" in parsed.get("error")):
                                    has_echo_fail = True
                                elif "error" not in parsed:
                                    has_real_tool = True
                        except (json.JSONDecodeError, TypeError):
                            pass
            
            # Get final text from last step
            if hasattr(step, 'model_output') and step.model_output:
                final_text = str(step.model_output).strip()
    except Exception:
        pass
    
    # Trigger-phrase validation: only return tool outputs if user asked for a command
    last_user_msg = ""
    for m in reversed(messages):
        if m["role"] == "user":
            last_user_msg = m["content"].lower()
            break
    
    has_command_trigger = any(phrase in last_user_msg for phrase in [
        "run ", "execute ", "run the command", "run ls", "run pwd", "run '", "run \"", "run:"])
    
    # If no command trigger, ignore tool outputs and return text answer
    if not has_command_trigger or (has_echo_fail and not has_real_tool):
        tool_outputs = []
        if final_text and len(final_text) > 0:
            if len(final_text) > 500:
                final_text = final_text[:500].rsplit(' ', 1)[0] + '...'
            return {"text": final_text, "toolOutputs": []}
    
    # Tool outputs take priority (if we got here, user asked for a command)
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
    print(f"Config: {CONFIG_PATH}")
    app.run(host="0.0.0.0", port=AGENT_PORT)

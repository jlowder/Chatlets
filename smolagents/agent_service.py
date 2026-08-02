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
    import os
    os.environ["LITELLM_TIMEOUT"] = "300"

    model = LiteLLMModel(
        model_id=f"openai/{cfg['model']}",
        api_base=cfg["baseURL"],
        api_key=cfg["apiKey"],
        extra_body={"max_tokens": 4096},
    )

    agent = ToolCallingAgent(
        tools=[bash_tool],
        model=model,
        max_steps=1,
    )
    agent.prompt_templates["system_prompt"] = (
        "You are a helpful assistant. You have ONE tool available: 'bash' which executes shell commands.\n\n"
        "CRITICAL RULES:\n"
        "1. Answer questions directly from your knowledge — do NOT use the bash tool for greetings, facts, definitions, math, explanations, or general knowledge.\n"
        "2. Only use bash when the user EXPLICITLY asks to run a command (e.g., 'run ls', 'execute pwd', 'run the command ls').\n"
        "3. If the user says 'hi', 'hello', 'help', or asks a question — just reply directly.\n"
        "4. Do NOT invent tools that don't exist. The only tool is 'bash' with the argument 'command' (a string).\n"
        "5. Do NOT call bash for echo, google_search, or anything not explicitly requested.\n\n"
        "When you DO need to use bash, call it like: bash(command='ls -la')\n"
        "When you DON'T need a tool, just provide your answer directly."
    )
    return agent


async def run_agent(messages: list) -> dict:
    """Run the agent and return the result."""
    agent = create_agent()
    
    # Build conversation context
    user_messages = []
    for m in messages:
        if m["role"] == "user":
            user_messages.append(f"User: {m['content']}")
        elif m["role"] == "assistant":
            user_messages.append(f"Assistant: {m['content']}")
    
    history = "\n".join(user_messages[:-1]) if len(user_messages) > 1 else ""
    current_prompt = user_messages[-1].replace("User: ", "") if user_messages else ""
    
    full_prompt = f"Previous conversation:\n{history}\n\n{current_prompt}" if history else current_prompt
    
    # Suppress trace output
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    
    try:
        result = agent.run(full_prompt)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    
    result_str = str(result) if result is not None else ""
    
    # Extract tool outputs from agent.memory.steps (canonical approach)
    tool_outputs = []
    try:
        steps = agent.memory.steps if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps') else []
        for step in steps:
            # Skip final_answer steps
            if hasattr(step, 'is_final_answer') and step.is_final_answer:
                continue
            if hasattr(step, 'tool_calls') and step.tool_calls:
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
                        except (json.JSONDecodeError, TypeError):
                            pass
        
        # If we found tool outputs, return only those (suppress text)
        if tool_outputs:
            return {
                "text": "",
                "toolOutputs": tool_outputs,
            }
    except Exception:
        pass
    
    # Clean the result — strip reasoning blocks
    import re
    
    def clean_result(text: str) -> str:
        """Strip reasoning/thinking blocks from agent output."""
        # If output has no reasoning markers, return as-is (clean response)
        if not re.search(r'(Thought:|Observation:|Action:|Action Input:)', text, re.IGNORECASE):
            # Strip markdown code blocks if present
            text = re.sub(r'```python\s*.*?\s*```', '', text, flags=re.DOTALL)
            text = re.sub(r'```\s*.*?\s*```', '', text, flags=re.DOTALL)
            return text.strip()
        
        # Has reasoning — take text after the last "Observation:" or the final answer
        obs_parts = re.split(r'Observation:', text, flags=re.IGNORECASE)
        if len(obs_parts) > 1:
            text = obs_parts[-1].strip()
        
        # Now remove any remaining Thought: blocks
        parts = re.split(r'Thought:.*?(?=(Observation|Action:|$))', text, flags=re.IGNORECASE | re.DOTALL)
        text = parts[-1] if parts else text
        
        # Strip any code blocks
        text = re.sub(r'```python\s*.*?\s*```', '', text, flags=re.DOTALL)
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        
        return text.strip()
    
    result_str = clean_result(result_str)
    
    # Safety: truncate to 500 chars to prevent runaway output
    if len(result_str) > 500:
        result_str = result_str[:500].rsplit(' ', 1)[0] + '...'
    
    if not result_str:
        result_str = "I couldn't process that request."
    
    return {
        "text": result_str,
        "toolOutputs": [],
    }


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

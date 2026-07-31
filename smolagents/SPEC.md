# Chatlets — smolagents Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using smolagents' code-first paradigm. A `CodeAgent` generates Python code snippets to invoke tools and solve tasks. Tools are registered via `@tool` decorator or by subclassing `Tool`. The agent executes its generated code locally (safe by default) or in a sandbox, returning results via `final_answer()`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Shared Frontend (shared/)                     │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Chat UI: input + response + tool output cards       │  │
│  └───────────────────────────────────────────────────────┘  │
│        │                                                    │
│        │ fetch POST /api/chat                               │
│        ▼                                                    │
│  next.config.mjs (CHATLET_BACKEND=smolagents)               │
│  rewrites → smolagents backend on :5000                    │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { prompt }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              smolagents backend (port 5000)                │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ CodeAgent.run() │───▶│ bash Tool (@tool decorated)  │   │
│  │                 │    │  - Python function           │   │
│  │  ┌────────────┐ │    │  - subprocess.run(timeout)   │   │
│  │  │   prompt   │ │    │  - 30s timeout              │   │
│  │  └────────────┘ │    │  - returns stdout/stderr     │   │
│  │        │        │    └───────────────────────────────┘   │
│  │        │           ▲                            │         │
│  │        └───────────┼────────────────────────────┘         │
│  │            │       │                                     │
│  │            ▼       │                                     │
│  │  ┌──────────────┐  │                                     │
│  │  │  Result      │◀─┼─────────────────────────────────────┤
│  │  │  - output    │  │                                     │
│  │  │  - steps────┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call via LiteLLM                │
         │ max_steps: 30 (default)                               │
         │ Allow List Check                                      │
         │                                                       │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    LLM via URL (LiteLLM)                           │
└────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### `POST /api/chat`

| Property | Value |
|----------|-------|
| **Content-Type** | `application/json` |
| **Request Body** | `{ prompt: string }` |
| **Success Response** | `{ text: string, toolOutputs: { stdout?: string, stderr?: string, error?: string }[] }` |
| **Error Response** | `{ error: string }` |

---

## API Contract

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | `string` | Yes | User's chat message |
| `text` | `string` | Yes | LLM response text |
| `toolOutputs` | `object[]` | No | Array of bash tool execution results |
| `error` | `string` | No | Error message if request fails |

---

## Technical Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Agent Framework** | smolagents (Hugging Face) | 1.x |
| **LLM Provider** | LiteLLM | 1.x |
| **Validation** | Pydantic | 2.x |
| **Type Safety** | TypeScript | 5.x (for proxy/API layer) |

---

## Key Components

### `app/api/chat/route.ts` (or `agent_service.py` equivalent)

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference via a smolagents CodeAgent

```python
Key imports:
  - CodeAgent from smolagents
  - LiteLLMModel from smolagents.models

Key exports:
  - POST(req: NextRequest)

Configuration:
  - model: LiteLLMModel with openai-compatible baseURL
  - tools: [@tool decorated function]
  - agent: CodeAgent with tools, model
  - run(): agent.run(prompt) → string output
```

### CodeAgent Definition

**Type**: Python class (`CodeAgent`)  
**Purpose**: Code-generating agent that writes Python to invoke tools

```python
from smolagents import CodeAgent, LiteLLMModel

agent = CodeAgent(
    tools=[bash_tool],
    model=model,
    max_steps=30,
    additional_authorized_imports=["json", "subprocess"],
)
```

### Bash Tool

**Type**: Python function decorated with `@tool`  
**Purpose**: Turn a Python function into an agent-accessible tool

```python
from smolagents import tool

@tool
def bash_tool(command: str) -> str:
    """Execute a bash command on the server.
    
    Args:
        command: The bash/shell command to execute
    """
    # ... implementation ...
```

---

## LLM Configuration

```python
from smolagents import LiteLLMModel

model = LiteLLMModel(
    model_id="modelName",
    api_base="baseUrl",
    api_key="example",
)
```

| Setting | Value |
|---------|-------|
| **Model ID** | `modelName` |
| **Base URL** | `baseUrl` |
| **API Key** | `example` |
| **Provider Type** | OpenAI-compatible (via LiteLLM) |
| **Max Tokens** | Model-dependent |

Configuration data is persisted to a file called `llm-config.json`.

---

## Bash Tool Design

### Schema Definition

smolagents uses the `@tool` decorator to turn Python functions into agent-accessible tools. Type hints and docstrings are auto-converted into tool schemas.

```python
import json
import subprocess
from smolagents import tool

ALLOW_LIST = {"ls", "pwd"}
ALLOW_ALL = False

@tool
def bash_tool(command: str) -> str:
    """Execute a bash command on the server.
    
    You MUST provide a "command" parameter with the exact shell command to run.
    This is the ONLY way to run commands. For example: command="pwd", 
    command="ls -la", command="npm run build".
    
    Args:
        command: The bash/shell command to execute
        
    Returns:
        JSON string with stdout, stderr, and optional error
    """
    base_cmd = command.split()[0] if command.strip() else ""
    if base_cmd not in ALLOW_LIST and not ALLOW_ALL:
        return json.dumps({
            "error": f"Command '{base_cmd}' not allowed",
            "stdout": "",
            "stderr": ""
        })
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        return json.dumps({
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "Command timed out (30s)",
            "stdout": "",
            "stderr": ""
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "stdout": "",
            "stderr": ""
        })
```

### Execution Configuration

| Setting | Value |
|---------|-------|
| **Command Runner** | `subprocess.run()` (synchronous) |
| **Timeout** | 30,000 ms (30 seconds) |
| **Captured Output** | `stdout`, `stderr`, `error` |
| **Max Steps** | 30 (default) |

### Allow List Filtering

The bash tool enforces an allow list that restricts which commands can be executed. Before running a command, the tool checks if the base command (first word) is in the allow list.

### Return Types

smolagents tool results are captured as strings in the agent's execution logs:

```python
# Success (returned as string)
json.dumps({
    "stdout": str,    # Trimmed
    "stderr": str     # Trimmed
})

# Error (returned as string)
json.dumps({
    "error": str,     # Error message
    "stdout": str,    # Trimmed (may be partial)
    "stderr": str     # Trimmed
})
```

---

## Command Allow List

### Default Allow List

By default, the allow list includes:
- `ls` — List directory contents
- `pwd` — Print working directory

### User Editable

Users can modify the allow list through the shared frontend UI:
- **Add commands**: Enter a new command to add it to the list
- **Remove commands**: Click the remove button next to any command

### Allow All Mode

A toggle setting enables "Allow All" mode:
- **Enabled**: The allow list is ignored; any command the LLM generates will execute
- **Disabled**: Only commands in the allow list are permitted

---

## Agent Architecture

### Code Generation Loop

smolagents `CodeAgent` uses a code-first paradigm — it generates Python code snippets to invoke tools:

```
User prompt → LLM generates Python code → Execute code → Observe output → Repeat → final_answer()
```

```python
from smolagents import CodeAgent, LiteLLMModel, tool
import json
import subprocess

ALLOW_LIST = {"ls", "pwd"}
ALLOW_ALL = False

# Step 1: Define the model
model = LiteLLMModel(
    model_id="modelName",
    api_base="baseUrl",
    api_key="example",
)

# Step 2: Define the tool
@tool
def bash_tool(command: str) -> str:
    """Execute a bash command on the server.
    
    You MUST provide a "command" parameter with the exact shell command to run.
    This is the ONLY way to run commands. For example: command="pwd", 
    command="ls -la", command="npm run build".
    
    Args:
        command: The bash/shell command to execute
    """
    base_cmd = command.split()[0] if command.strip() else ""
    if base_cmd not in ALLOW_LIST and not ALLOW_ALL:
        return json.dumps({
            "error": f"Command '{base_cmd}' not allowed",
            "stdout": "",
            "stderr": ""
        })
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        return json.dumps({
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "Command timed out (30s)",
            "stdout": "",
            "stderr": ""
        })
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "stdout": "",
            "stderr": ""
        })

# Step 3: Create the CodeAgent
agent = CodeAgent(
    tools=[bash_tool],
    model=model,
    max_steps=30,
    additional_authorized_imports=["json", "subprocess"],
)

# Step 4: Run the agent
result = agent.run(prompt)
# result is a string (the final_answer output)

# Step 5: Inspect the run
# agent.logs stores fine-grained logs of each step
# agent.write_memory_to_messages() returns chat message history
```

**Key smolagents concepts used**:
- `CodeAgent` — generates Python code snippets to invoke tools, performs computations, and returns `final_answer()`
- `CodeAgent` vs `ToolCallingAgent` — two paradigms: code generation vs structured JSON tool calls
- `@tool` — decorator that turns a Python function into a tool; type hints and docstrings auto-generate the schema
- `additional_authorized_imports=["json", "subprocess"]` — allows the agent to import these modules in generated code
- `max_steps=30` — maximum number of execution steps before termination
- `final_answer(value)` — special function the agent calls to return its final result
- `final_answer_checks=[validator_func]` — list of validation functions that check the final answer
- `agent.logs` — fine-grained logs of each step (each step stored as a dict)
- `agent.write_memory_to_messages()` — returns chat message history for the model

### Code Execution

Generated Python code is executed in a safe environment:

- **Local execution** (default): Code runs in the same Python process with import restrictions
- **Sandboxed execution**: Use `executor_type="docker"`, `"e2b"`, or `"blaxel"` for isolated execution
- **Import safety**: Python interpreter doesn't allow imports outside a safe list by default; `additional_authorized_imports` extends this

### Final Answer

The agent calls `final_answer(value)` to return its result:

```python
from smolagents import final_answer

@tool
def bash_tool(command: str) -> str:
    """Execute a bash command and return the result."""
    # ... execute command ...
    return final_answer(result_content)
```

Validation functions can be attached:

```python
def validate_answer(value: str) -> bool:
    return len(value) > 0

agent = CodeAgent(
    tools=[bash_tool],
    model=model,
    final_answer_checks=[validate_answer],
)
```

### Managed Agents

smolagents supports hierarchical multi-agent systems:

```python
researcher = CodeAgent(
    tools=[web_search_tool],
    model=model,
    name="researcher",
    description="Searches the web for information.",
)

agent = CodeAgent(
    tools=[bash_tool],
    model=model,
    managed_agents=[researcher],
)
```

Sub-agents with `name` and `description` attributes can be managed by a parent agent.

---

## Hub Integration

### Push to Hub

Share agents with the Hugging Face Hub:

```python
agent.push_to_hub("user/agent-name")
```

### Load from Hub

Load shared agents:

```python
agent = CodeAgent.from_hub("user/agent-name", trust_remote_code=True)
```

---

## GradioUI Note

smolagents includes a built-in Gradio UI for interactive chat:

```python
from smolagents import GradioUI

GradioUI(agent).launch()
```

**Note for Chatlets**: This backend is **backend-only**. The shared frontend (`shared/`) provides the chat UI. GradioUI is available for development/testing but not used in production.

---

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, makes LLM calls
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. smolagents CodeAgent Pattern

```python
agent = CodeAgent(
    tools=[bash_tool],
    model=model,
    max_steps=30,
    additional_authorized_imports=["json", "subprocess"],
)

result = agent.run(prompt)
# result is a string (the final_answer output)
```

**Key differences from other frameworks**:
- Code-first paradigm: agent writes Python code to invoke tools (not JSON tool calls)
- Simpler API: just `agent.run(prompt)` — no explicit graph or state management
- Sandbox execution: generated code runs safely (local or Docker/E2B)
- Hub integration: push/load agents from Hugging Face Hub
- GradioUI: built-in interactive UI for development

### 3. Tool Output Structure

Tool results are extracted from `agent.logs` or `agent.write_memory_to_messages()`:
- `stdout` — green-tinted output card with dark terminal background
- `stderr` — red-tinted card for error streams
- `error` — inline error message if execution failed

---

## Key Dependencies

```json
{
  "dependencies": {
    "smolagents": "^1.x",
    "litellm": "^1.x",
    "next": "16.2.10 (for API routes only)"
  },
  "devDependencies": {
    "@types/node": "^20",
    "eslint": "^9",
    "typescript": "^5"
  }
}
```

---

## Running

```bash
cd smolagents
pip install smolagents litellm
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=smolagents`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **next.config.mjs** rewrites the request to `smolagents` backend on `:5000`
4. **API Route** creates a smolagents `CodeAgent` with model, bash tool, and authorized imports
5. **Agent** generates Python code to invoke `bash_tool(command="...")`
6. **CodeAgent** executes the generated code locally (safe by default)
7. **LLM** generates code based on prompt and available tools
8. **bash_tool()** executes command via `subprocess.run()` (30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
9. **Agent** iterates: generates code → executes → observes output → generates more code
10. **Agent** calls `final_answer(result)` when done (or `max_steps` reached)
11. **API Route** returns `{ text: result, toolOutputs[] }` from agent logs
12. **Frontend** displays response text and tool output cards

---

## Future Considerations

- **Multi-agent**: Use `managed_agents=[...]` for hierarchical agent teams
- **Sub-agents**: Create agents with `name` and `description` for parent delegation
- **Sandboxed execution**: Use `executor_type="docker"` or `"e2b"` for secure code execution
- **Push to Hub**: Share agents via `agent.push_to_hub("user/name")`
- **Load from Hub**: Load shared agents via `CodeAgent.from_hub("user/name")`
- **Final answer checks**: Add `final_answer_checks=[validator]` for output validation
- **ToolCallingAgent**: Use `ToolCallingAgent` for structured JSON tool calls (less expressive, more reliable)
- **Base tools**: Add `add_base_tools=True` for DuckDuckGo search, Python interpreter, transcriber
- **Model providers**: Use `InferenceClientModel`, `OpenAIModel`, `AzureOpenAIModel`, `AmazonBedrockModel`, `MLXModel`
- **Add request/response logging**
- **Configure environment variables for API credentials**
- **Add loading states for individual tool calls**
- **Support streaming tool outputs via SSE**

---

## smolagents vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | smolagents |
|---------------|------------|
| `generateText()` | `CodeAgent.run(prompt)` |
| `tool({ parameters, execute })` | `@tool` decorated function |
| `maxSteps: 5` | `max_steps=30` |
| Tool result as object | Tool result as string |
| Built-in streaming (`useChat`) | Not built-in (GradioUI for interactive) |
| Auto message history | `agent.write_memory_to_messages()` |
| Implicit tool routing | Agent generates Python code to call tools |
| `ai` package | `smolagents` (Hugging Face) |
| TypeScript-first | Python-first |

## smolagents vs LangChain: Key Mapping

| LangChain (createReactAgent) | smolagents |
|------------------------------|------------|
| `createReactAgent({ llm, tools })` | `CodeAgent(tools=[...], model=model)` |
| `StateGraph` with nodes/edges | Implicit code generation loop |
| `maxIterations: 5` | `max_steps=30` |
| `MemorySaver` / `SqliteSaver` | `agent.write_memory_to_messages()` |
| `invoke()` | `run(prompt)` |
| `stream()` | Not built-in |
| Explicit message management | `agent.logs` + `write_memory_to_messages()` |
| `thread_id` in configurable | Not built-in |
| `class extends Tool` | `@tool` decorated function |

## smolagents vs CrewAI: Key Mapping

| CrewAI | smolagents |
|--------|------------|
| `Crew.kickoff()` | `CodeAgent.run(prompt)` |
| `new Agent({ role, goal, tools })` | `CodeAgent(tools=[...], model=model)` |
| `new Task({ description, agent })` | `agent.run(prompt)` (prompt is inline) |
| `process: 'sequential'` | Single agent (managed_agents for multi) |
| `maxIter: 5` | `max_steps=30` |
| Tool as class | `@tool` decorated function |
| 3-layer: Agent → Task → Crew | 1-layer: Agent |

## smolagents vs Agno: Key Mapping

| Agno | smolagents |
|------|------------|
| `Agent.run(user=prompt)` | `CodeAgent.run(prompt)` |
| Python function as tool | `@tool` decorated function |
| `tool_call_limit=5` | `max_steps=30` |
| `RunOutput` | String (final_answer output) |
| `stream=True` | Not built-in |
| `session_id` | Not built-in |
| Automatic agent loop | Automatic code generation loop |
| `Agent` (1 primitive) | `CodeAgent` + `ToolCallingAgent` (2 agents) |
| `Team` / `Workflow` primitives | `managed_agents` for multi-agent |
| Type safety | Type hints for tool schemas |

## smolagents vs LangGraph: Key Mapping

| LangGraph | smolagents |
|-----------|------------|
| `StateGraph().addNode().compile()` | `CodeAgent()` — implicit code loop |
| `Annotation.Root` state | No explicit state |
| `maxIter: 5` | `max_steps=30` |
| `MemorySaver` | `agent.write_memory_to_messages()` |
| `invoke()` | `run(prompt)` |
| `stream()` | Not built-in |
| Explicit nodes/edges | Agent generates Python code |
| `interrupt` (HITL) | `agent.interrupt()` |
| Python + JS | Python-only |

## smolagents vs Microsoft Agent Framework: Key Mapping

| MAF | smolagents |
|-----|------------|
| `Agent.run(prompt, session=session)` | `CodeAgent.run(prompt)` |
| `@tool` decorated function | `@tool` decorated function |
| `FunctionInvocationContext` | Not built-in |
| Provider max iterations | `max_steps=30` |
| `AgentResult` | String (final_answer) |
| `agent.create_session()` | Not built-in |
| Automatic agent loop | Automatic code generation loop |
| Harness / Workflow | managed_agents for multi-agent |
| Multi-language | Python-only |

## smolagents vs Pydantic AI: Key Mapping

| Pydantic AI | smolagents |
|-------------|------------|
| `Agent.run(prompt, deps=deps)` | `CodeAgent.run(prompt)` |
| `@agent.tool` decorated function | `@tool` decorated function |
| `UsageLimits(tool_call_limit=5)` | `max_steps=30` |
| `AgentRunResult` | String (final_answer) |
| `run_stream()` | Not built-in |
| `agent.create_session()` | Not built-in |
| Automatic agent loop | Automatic code generation loop |
| `Agent[DepT, OutputT]` | No type parameters |
| Capabilities | managed_agents for multi-agent |

## smolagents vs LlamaIndex Workflows: Key Mapping

| LlamaIndex Workflows | smolagents |
|---------------------|------------|
| `Workflow.run(input=...)` | `CodeAgent.run(prompt)` |
| `@step` functions with typed events | `@tool` decorated functions |
| `Event` classes | No explicit events |
| `ctx.store` | Not built-in |
| `timeout=120` | `max_steps=30` |
| `FunctionTool.from_defaults(func)` | `@tool` decorated function |
| Event-driven loops | Code generation loop |
| `Workflow` + `Event` + `@step` | `CodeAgent` + `@tool` |
| Python-first | Python-first |

## smolagents vs Mastra: Key Mapping

| Mastra | smolagents |
|--------|------------|
| `agent.generate(prompt)` | `CodeAgent.run(prompt)` |
| `createTool({ inputSchema, execute })` | `@tool` decorated function |
| `maxSteps: 5` | `max_steps=30` |
| `FullOutput` | String (final_answer) |
| `agent.stream()` | Not built-in |
| `Memory` + `SQLiteStorage` | `agent.write_memory_to_messages()` |
| Agent loop | Automatic code generation loop |
| `Workflow` class | `managed_agents` for multi-agent |

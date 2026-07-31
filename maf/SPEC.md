# Chatlets — Microsoft Agent Framework Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using Microsoft Agent Framework's (MAF) agent-centric approach. An `Agent` is created from a chat client with tools, instructions, and session management. MAF provides production-grade features out of the box: compaction, observability, middleware, and multi-language support (Python, C#, Go).

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
│  next.config.mjs (CHATLET_BACKEND=maf)                      │
│  rewrites → maf backend on :5000                           │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { prompt }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              maf backend (port 5000)                       │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ Agent.run()     │───▶│ bash Tool (@tool decorated)  │   │
│  │                 │    │  - FunctionInvocationContext │   │
│  │                 │    │  - subprocess.run(timeout)   │   │
│  │  ┌────────────┐ │    │  - 30s timeout              │   │
│  │  │   prompt   │ │    │  - returns stdout/stderr     │   │
│  │  └────────────┘ │    └───────────────────────────────┘   │
│  │        │        │    ▲                            │      │
│  │        └─────────┼────────────────────────────┘         │
│  │            │       │                                     │
│  │            ▼       │                                     │
│  │  ┌──────────────┐  │                                     │
│  │  │  AgentResult │◀─┼─────────────────────────────────────┤
│  │  │  - text      │  │                                     │
│  │  │  - tool_calls────┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call                            │
         │ session-based state                                   │
         │ Allow List Check                                      │
         │                                                       │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    LLM via URL                                     │
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
| **Agent Framework** | Microsoft Agent Framework (Python) | 1.x |
| **LLM Provider** | `agent-framework-openai` | 1.x |
| **Validation** | Pydantic | 2.x |
| **Type Safety** | TypeScript | 5.x (for proxy/API layer) |

---

## Key Components

### `app/api/chat/route.ts` (or `agent_service.py` equivalent)

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference via a Microsoft Agent Framework agent

```python
Key imports:
  - Agent, tool, FunctionInvocationContext from agent_framework
  - OpenAIChatClient from agent_framework.openai

Key exports:
  - POST(req: NextRequest)

Configuration:
  - client: OpenAIChatClient with openai-compatible baseURL
  - tools: [@tool decorated function]
  - agent: Agent with instructions, session management
  - run(): agent.run(prompt, session=session) → AgentResult
```

### Agent Definition

**Type**: Python class (`Agent`)  
**Purpose**: Core primitive that encapsulates client, tools, instructions, and session

```python
agent = Agent(
    client=client,
    name="chat-agent",
    instructions=[
        "You are a helpful assistant that can execute bash commands on the server.",
        "Use the bash tool to run commands and return the results to the user.",
    ],
    tools=[bash_tool],
)
```

### Bash Tool

**Type**: Python function decorated with `@tool`  
**Purpose**: Turn a Python function into an agent-accessible tool with typed parameters

```python
from agent_framework import tool
from typing import Annotated
from pydantic import Field

@tool(
    name="bash",
    description="Execute a bash command on the server."
)
def bash_tool(
    command: Annotated[str, Field(description="The bash/shell command to execute")],
    ctx: FunctionInvocationContext,
) -> str:
    """Execute a bash command and return stdout/stderr."""
    # ... implementation ...
```

---

## LLM Configuration

```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    model="modelName",
    base_url="baseUrl",
    api_key="example",
)
```

| Setting | Value |
|---------|-------|
| **Model** | `modelName` |
| **Base URL** | `baseUrl` |
| **API Key** | `example` |
| **Provider Type** | OpenAI-compatible |
| **Max Retries** | Client default |

Configuration data is persisted to a file called `llm-config.json`.

---

## Bash Tool Design

### Schema Definition

MAF uses the `@tool` decorator to turn Python functions into agent-accessible tools. Type hints with `Annotated` and Pydantic's `Field` provide descriptions to the model.

```python
import json
import subprocess
from typing import Annotated
from pydantic import Field
from agent_framework import tool, FunctionInvocationContext

ALLOW_LIST = {"ls", "pwd"}
ALLOW_ALL = False

@tool(
    name="bash",
    description="""Execute a bash command on the server.
    You MUST provide a "command" parameter with the exact shell command to run.
    This is the ONLY way to run commands. For example: command="pwd", 
    command="ls -la", command="npm run build"."""
)
def bash_tool(
    command: Annotated[str, Field(description="The bash/shell command to execute")],
    ctx: FunctionInvocationContext,
) -> str:
    """Execute a bash command and return stdout/stderr.
    
    Args:
        command: The shell command to execute
        ctx: Runtime context (injected by MAF, not sent to model)
        
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
| **Max Iterations** | Client/provider default (configurable per chat client) |

### Allow List Filtering

The bash tool enforces an allow list that restricts which commands can be executed. Before running a command, the tool checks if the base command (first word) is in the allow list.

### Return Types

MAF tool results are captured as strings in the agent's response:

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

### @tool Decorator Pattern

MAF uses the `@tool` decorator to turn Python functions into agent-accessible tools. Type hints with `Annotated` and Pydantic's `Field` provide descriptions to the model:

```python
@tool(
    name="bash",
    description="Execute a bash command on the server."
)
def bash_tool(
    command: Annotated[str, Field(description="The bash/shell command to execute")],
    ctx: FunctionInvocationContext,
) -> str:
    # ... implementation ...
```

**Key decorator options**:
- `@tool(name=..., description=..., schema=...)` — explicit tool control with Pydantic model or JSON schema dict
- `@tool(approval_mode="always")` — require approval before execution
- `FunctionInvocationContext` (`ctx`) — special parameter auto-injected by MAF (not sent to model); provides `ctx.kwargs`, `ctx.session`, and methods like `ctx.add_tools()` / `ctx.remove_tools()`

### Agent Pattern

```python
from agent_framework import Agent, tool, FunctionInvocationContext
from agent_framework.openai import OpenAIChatClient
from typing import Annotated
from pydantic import Field

# Step 1: Define the function tool
@tool(
    name="bash",
    description="Execute a bash command on the server."
)
def bash_tool(
    command: Annotated[str, Field(description="The bash/shell command to execute")],
    ctx: FunctionInvocationContext,
) -> str:
    # ... implementation ...

# Step 2: Create the chat client
client = OpenAIChatClient(
    model="modelName",
    base_url="baseUrl",
    api_key="example",
)

# Step 3: Create the agent
agent = Agent(
    client=client,
    name="chat-agent",
    instructions=[
        "You are a helpful assistant that can execute bash commands on the server.",
        "Use the bash tool to run commands and return the results to the user.",
        "Always explain what you did after running commands.",
    ],
    tools=[bash_tool],
)

# Step 4: Create a session for multi-turn conversations
session = agent.create_session()

# Step 5: Run the agent
result = await agent.run(prompt, session=session)

# Step 6: Access results
final_text = result.text                    # Final text response
tool_calls = result.tool_calls              # List of tool calls made
tool_results = [tc.result for tc in tool_calls]  # Tool execution results
```

**Key Microsoft Agent Framework concepts used**:
- `Agent` — the core primitive; encapsulates client, tools, instructions, and session
- `tools=[bash_tool]` — Python functions decorated with `@tool` are auto-registered as tools
- `FunctionInvocationContext` (`ctx`) — special parameter auto-injected by MAF (not sent to model); provides `ctx.kwargs`, `ctx.session`, and methods like `ctx.add_tools()` / `ctx.remove_tools()`
- `agent.create_session()` — creates a session for multi-turn conversation history
- `agent.run(prompt, session=session)` — runs the agent; session persists context across calls
- `AgentResult` — contains `.text` (final response), `.tool_calls` (list of executed tools)
- `@tool(name=..., description=..., schema=...)` — decorator for explicit tool control
- `Annotated[str, Field(description="...")]` — type hints provide parameter descriptions to the model

### Harness

MAF provides a `Harness` — an opinionated agent with batteries-included features:

```python
from agent_framework import create_harness_agent

harness = create_harness_agent(
    client=client,
    instructions="You are a helpful assistant.",
    tools=[bash_tool],
)
```

**Harness features**:
- Todo list management
- File memory
- Web search integration
- Mode switching
- Auto-approval for tools

### WorkflowBuilder

MAF supports multi-step orchestration via `WorkflowBuilder` and the `@workflow`/`@step` functional API:

```python
from agent_framework import WorkflowBuilder, workflow, step

@workflow
def my_workflow(input: str) -> str:
    # Multi-step orchestration
    pass
```

---

## Session Management

Sessions persist conversation context across multiple `agent.run()` calls:

```python
session = agent.create_session()

# First turn
result1 = await agent.run("Hello", session=session)

# Second turn — session maintains history
result2 = await agent.run("What did I just say?", session=session)
```

---

## Production Features

### Compaction

Built-in context-window compaction via chat client options. When conversation exceeds token limits, MAF automatically summarizes earlier messages.

```python
client = OpenAIChatClient(
    model="modelName",
    base_url="baseUrl",
    api_key="example",
    compaction_enabled=True,  # Enable automatic compaction
)
```

### OpenTelemetry Observability

MAF provides built-in OpenTelemetry tracing for all agent actions:

```python
# MAF auto-instruments agent runs, tool calls, and LLM interactions
# Export to any OpenTelemetry collector (Jaeger, Tempo, etc.)
```

### Middleware/Filters

Intercept agent actions with pre/post hooks on tool calls:

```python
from agent_framework import Filter

class ToolLoggingFilter(Filter):
    async def on_tool_call(self, ctx, next_fn):
        print(f"Calling tool: {ctx.kwargs.get('name')}")
        result = await next_fn()
        print(f"Tool result: {result[:100]}...")
        return result
```

### Tool Approval

Mark tools with `approval_mode="always"` for safety gates:

```python
@tool(approval_mode="always")
def dangerous_tool(param: str) -> str:
    # Requires explicit user approval before execution
    pass
```

---

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, makes LLM calls
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. MAF Agent Pattern

```python
agent = Agent(
    client=client,
    name="chat-agent",
    instructions=["You are a helpful assistant that can execute bash commands."],
    tools=[bash_tool],
)

session = agent.create_session()
result = await agent.run(prompt, session=session)
```

**Key differences from other frameworks**:
- Single `Agent` primitive (not layered like CrewAI's Agent → Task → Crew)
- Session-based context persistence (not hidden in framework internals)
- Production features built-in: compaction, observability, middleware
- Multi-language support: Python, C#, Go

### 3. Tool Output Structure

Tool results are extracted from `result.tool_calls[]`:
- `stdout` — green-tinted output card with dark terminal background
- `stderr` — red-tinted card for error streams
- `error` — inline error message if execution failed

---

## Key Dependencies

```json
{
  "dependencies": {
    "agent-framework": "^1.x",
    "agent-framework-openai": "^1.x",
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
cd maf
pip install agent-framework agent-framework-openai
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=maf`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **next.config.mjs** rewrites the request to `maf` backend on `:5000`
4. **API Route** creates an MAF `Agent` with chat client, bash tool, and instructions
5. **API Route** creates a `session` for conversation state
6. **Agent** calls `agent.run(prompt, session=session)`
7. **Agent** sends context + tool definitions to the LLM via the chat client
8. **LLM** processes prompt, may request tool calls
9. **MAF** validates arguments, executes `bash_tool()` (30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
10. **Tool results** added to session context; agent loop continues
11. **Agent** loops until LLM returns final response (no more tool calls)
12. **API Route** returns `{ text, toolOutputs[] }` extracted from `AgentResult`
13. **Frontend** displays response text and tool output cards

---

## Multi-Language Support

MAF is available in multiple languages with identical patterns:

| Language | Package | Notes |
|----------|---------|-------|
| **Python** | `agent-framework` | Primary implementation, full feature parity |
| **C#** | `Microsoft.Agents` | .NET SDK, same `Agent`/`@tool` patterns |
| **Go** | `github.com/microsoft/agents-go` | Go SDK, idiomatic Go patterns |

The Python `@tool` decorator maps to:
- C#: `[Tool]` attribute on methods
- Go: `tool.New()` constructor function

---

## Future Considerations

- **Harness mode**: Use `create_harness_agent()` for batteries-included features (todo list, file memory, web search, mode switching, auto-approval)
- **Workflows**: Use MAF's `@workflow`/`@step` functional API or `WorkflowBuilder` for multi-step orchestration
- **Multi-agent**: Pass `background_agents` to harness for parallel delegation
- **Compaction**: Enable context-window compaction via chat client options
- **Tool approval**: Mark tools with `approval_mode="always"` for safety gates
- **Sessions**: Use `agent.create_session()` for multi-turn persistence
- **Middleware**: Add filters for pre/post tool call hooks
- **Observability**: Built-in OpenTelemetry tracing (already available)
- **Multi-language**: C# and Go SDKs available for the same patterns
- **Agent skills**: Discover and load skills from the file system
- **Looping**: Use `loop_should_continue` predicate for iterative workflows
- **Add request/response logging**
- **Configure environment variables for API credentials**
- **Add loading states for individual tool calls**
- **Support streaming tool outputs via SSE**

---

## Microsoft Agent Framework vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | Microsoft Agent Framework |
|---------------|--------------------------|
| `generateText()` | `Agent.run(prompt, session=session)` |
| `tool({ parameters, execute })` | `@tool` decorated function |
| `maxSteps: 5` | Chat client max iterations (provider-dependent) |
| Tool result as object | Tool result as string (captured in `AgentResult`) |
| Built-in streaming (`useChat`) | Chat client streaming support |
| Auto message history | `session` object (explicit) |
| Implicit tool routing | Automatic in Agent loop |
| `ai` package | `agent-framework` + provider packages |
| TypeScript-first | Python, C#, Go (multi-language) |

## Microsoft Agent Framework vs LangChain: Key Mapping

| LangChain (createReactAgent) | Microsoft Agent Framework |
|------------------------------|--------------------------|
| `createReactAgent({ llm, tools })` | `Agent(client=client, tools=[func])` |
| `StateGraph` with nodes/edges | Implicit agent loop (Agent handles the loop) |
| `maxIterations: 5` | Provider max iterations |
| `MemorySaver` / `SqliteSaver` | `agent.create_session()` + chat client storage |
| `invoke()` | `run(prompt, session=session)` |
| `stream()` | Chat client streaming |
| Explicit message management | Session-based context |
| `thread_id` in configurable | `session` object |
| `class extends Tool` | `@tool` decorated function |

## Microsoft Agent Framework vs CrewAI: Key Mapping

| CrewAI | Microsoft Agent Framework |
|--------|--------------------------|
| `Crew.kickoff()` | `Agent.run(prompt, session=session)` |
| `new Agent({ role, goal, tools })` | `Agent(client=client, name=..., instructions=..., tools=[...])` |
| `new Task({ description, agent })` | `agent.run(prompt)` (prompt is inline) |
| `process: 'sequential'` | Single agent (Harness for multi-agent) |
| `maxIter: 5` | Provider max iterations |
| Tool as class | `@tool` decorated function |
| 3-layer: Agent → Task → Crew | 1-layer: Agent (Harness/Workflow primitives) |

## Microsoft Agent Framework vs Agno: Key Mapping

| Agno | Microsoft Agent Framework |
|------|--------------------------|
| `Agent.run(user=prompt)` | `Agent.run(prompt, session=session)` |
| Python function as tool | `@tool` decorated function |
| `tool_call_limit=5` | Provider max iterations |
| `RunOutput` | `AgentResult` |
| `stream=True` | Chat client streaming |
| `session_id` | `agent.create_session()` |
| Automatic agent loop | Automatic agent loop |
| `Agent` (1 primitive) | `Agent` (1 primitive) + `Harness` + `Workflow` |
| `Team` / `Workflow` primitives | `WorkflowBuilder` + `@workflow` API |
| Multi-language | Python, C#, Go |

## Microsoft Agent Framework vs LangGraph: Key Mapping

| LangGraph | Microsoft Agent Framework |
|-----------|--------------------------|
| `StateGraph().addNode().compile()` | `Agent()` — implicit loop |
| `Annotation.Root` state | `session` object |
| `maxIter: 5` | Provider max iterations |
| `MemorySaver` | `agent.create_session()` |
| `invoke()` | `run(prompt, session=session)` |
| `stream()` | Chat client streaming |
| Explicit nodes/edges | Implicit (or `WorkflowBuilder` for explicit) |
| `interrupt` (HITL) | `RequestInfoExecutor` / tool approval |
| Python + JS | Python, C#, Go |

## Microsoft Agent Framework vs LlamaIndex Workflows: Key Mapping

| LlamaIndex Workflows | Microsoft Agent Framework |
|---------------------|--------------------------|
| `Workflow.run(input=...)` | `Agent.run(prompt, session=session)` |
| `@step` functions with typed events | `@tool` functions + implicit routing |
| `Event` classes | `AgentResult` / `FunctionInvocationContext` |
| `ctx.store` | `session` object |
| `timeout=120` | Provider max iterations |
| `FunctionTool.from_defaults(func)` | `@tool` decorated function |
| Event-driven loops | Implicit agent loop |
| `Workflow` + `Event` + `@step` | `Agent` + `session` + `@tool` |
| Python-first | Python, C#, Go |

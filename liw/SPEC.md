# Chatlets — LlamaIndex Workflows Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using LlamaIndex Workflows' event-driven, step-based paradigm. A `Workflow` is defined with typed `@step`-decorated functions that pass `Event` objects between each other. The workflow automatically routes events based on type annotations, enabling loops and conditional branching.

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
│  next.config.mjs (CHATLET_BACKEND=liw)                      │
│  rewrites → liw backend on :5000                           │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { prompt }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              liw backend (port 5000)                       │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ Workflow.run()  │───▶│ bash Tool (FunctionTool)     │   │
│  │                 │    │  - FunctionTool.from_defaults│   │
│  │                 │    │  - subprocess.run(timeout)   │   │
│  │  ┌────────────┐ │    │  - 30s timeout              │   │
│  │  │   prompt   │ │    │  - returns stdout/stderr     │   │
│  │  └────────────┘ │    └───────────────────────────────┘   │
│  │        │        │    ▲                            │      │
│  │        └─────────┼────────────────────────────┘         │
│  │            │       │                                     │
│  │            ▼       │                                     │
│  │  ┌──────────────┐  │                                     │
│  │  │  Return JSON │◀─┼─────────────────────────────────────┤
│  │  │  - response  │  │                                     │
│  │  │  - events────┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call                            │
         │ timeout: 120s (max workflow runtime)                  │
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
| **Workflow Framework** | LlamaIndex Workflows | 0.x (via `llama-index-core`) |
| **LLM Provider** | `llama-index-llms-openai-compatible` | 0.x |
| **Validation** | Pydantic | 2.x |
| **Type Safety** | TypeScript | 5.x (for proxy/API layer) |

---

## Key Components

### `app/api/chat/route.ts` (or `agent_service.py` equivalent)

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference via a LlamaIndex Workflow

```ts
Key imports (Python):
  - Workflow, StartEvent, StopEvent, step, Context, Event from llama_index.core.workflow
  - FunctionTool from llama_index.core.tools
  - ChatMemoryBuffer from llama_index.core.memory
  - ChatMessage from llama_index.core.llms

Key exports:
  - POST(req: NextRequest)

Configuration:
  - llm: OpenAI-compatible via llama-index llm provider
  - tools: [FunctionTool.from_defaults(bash_func)]
  - workflow: ChatWorkflow with typed steps
  - timeout: 120s (max workflow runtime)
```

### Workflow Definition

**Type**: Python class with `@step`-decorated async functions  
**Purpose**: Define the event-driven chat workflow with 4 steps

```python
class ChatWorkflow(Workflow):
    def __init__(self, *args, llm=None, tools=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tools = tools or []
        self.llm = llm

    @step
    async def prepare_chat_history(self, ctx: Context, ev: StartEvent) -> InputEvent:
        """Entry point: initialize memory and build chat history."""

    @step
    async def handle_llm_input(self, ctx: Context, ev: InputEvent) -> Union[ToolCallEvent, StopEvent]:
        """Call LLM with chat history + tools. Returns ToolCallEvent or StopEvent."""

    @step
    async def handle_tool_calls(self, ctx: Context, ev: ToolCallEvent) -> InputEvent:
        """Execute tool calls and return updated chat history."""
```

### Custom Event Types

**Type**: Typed `Event` subclasses  
**Purpose**: Define the data contracts between workflow steps

```python
class InputEvent(Event):
    """Event carrying chat history for LLM processing."""
    input: list[ChatMessage]

class ToolCallEvent(Event):
    """Event carrying tool calls to be executed."""
    tool_calls: list[ToolSelection]

class StreamEvent(Event):
    """Event for streaming response deltas."""
    delta: str
```

### Bash Tool

**Type**: `FunctionTool.from_defaults(func)`  
**Purpose**: Wrap a Python function as a LlamaIndex tool with auto-schemed parameters

```python
def bash_command(command: str) -> str:
    """Execute a bash command on the server.
    
    Args:
        command: The bash/shell command to execute
        
    Returns:
        JSON string with stdout, stderr, and optional error
    """
    # ... execute and return result as JSON string
```

---

## LLM Configuration

```python
from llama_index.llms.openai_compatible import OpenAICompatible

llm = OpenAICompatible(
    model="modelName",
    api_key="example",
    base_url="baseUrl",
)
```

| Setting | Value |
|---------|-------|
| **Model** | `modelName` |
| **Base URL** | `baseUrl` |
| **API Key** | `example` |
| **Provider Type** | OpenAI-compatible |
| **Max Tokens** | Model-dependent |

Configuration data is persisted to a file called `llm-config.json`.

---

## Bash Tool Design

### Schema Definition

LlamaIndex wraps Python functions as tools using `FunctionTool.from_defaults()`. Type hints and docstrings are auto-converted into tool schemas.

```python
import json
import subprocess
from llama_index.core.tools import FunctionTool

ALLOW_LIST = {"ls", "pwd"}
ALLOW_ALL = False

def bash_command(command: str) -> str:
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

bash_tool = FunctionTool.from_defaults(bash_command)
```

### Execution Configuration

| Setting | Value |
|---------|-------|
| **Command Runner** | `subprocess.run()` (synchronous) |
| **Timeout** | 30,000 ms (30 seconds) |
| **Captured Output** | `stdout`, `stderr`, `error` |
| **Workflow Timeout** | 120,000 ms (120 seconds) |

### Allow List Filtering

The bash tool enforces an allow list that restricts which commands can be executed. Before running a command, the tool checks if the base command (first word) is in the allow list.

### Return Types

LlamaIndex `FunctionTool` results are captured as `ToolOutput` objects with a `.content` string:

```python
# Success (returned as string, wrapped in ToolOutput)
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

## Workflow Pattern

### 4-Step Event-Driven Flow

```
StartEvent → prepare_chat_history → InputEvent → handle_llm_input
                                                        ↓
                                           { ToolCallEvent | StopEvent }
                                                ↓              ↓
                                        handle_tool_calls  →  End
                                                ↓
                                         InputEvent (loop back)
```

### Type-Driven Event Routing

LlamaIndex Workflows automatically routes events based on step type annotations:

```python
# Step returning InputEvent → next step accepting InputEvent is called
@step
async def handle_llm_input(self, ctx: Context, ev: InputEvent) -> Union[ToolCallEvent, StopEvent]:
    # ...

# Step accepting ToolCallEvent
@step
async def handle_tool_calls(self, ctx: Context, ev: ToolCallEvent) -> InputEvent:
    # ...
```

### Persistent State via `ctx.store`

The `Context` object provides built-in key-value storage that persists across steps:

```python
# Get or create memory
memory = await ctx.store.get("memory", default=None)
if not memory:
    memory = ChatMemoryBuffer.from_defaults(llm=self.llm)

# Persist changes
memory.put(ChatMessage(role="user", content=prompt))
await ctx.store.set("memory", memory)
```

**Key features**:
- `ctx.store.set(key, value)` — persist data across steps
- `ctx.store.get(key, default=...)` — retrieve persisted data
- `ChatMemoryBuffer` — LlamaIndex's built-in chat memory, auto-manages conversation history

### Context & Streaming

```python
# Run with persistent context (for multi-turn)
ctx = Context(workflow)
result = await workflow.run(input=prompt, ctx=ctx)

# Stream events to client
ctx.write_event_to_stream(StreamEvent(delta=response.delta or ""))
```

---

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, makes LLM calls
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. LlamaIndex Workflows Event-Driven Pattern

```python
class ChatWorkflow(Workflow):
    def __init__(self, *args, llm=None, tools=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tools = tools or []
        self.llm = llm

    @step
    async def prepare_chat_history(self, ctx: Context, ev: StartEvent) -> InputEvent:
        memory = await ctx.store.get("memory", default=None)
        if not memory:
            memory = ChatMemoryBuffer.from_defaults(llm=self.llm)
        memory.put(ChatMessage(role="user", content=ev.input))
        await ctx.store.set("memory", memory)
        return InputEvent(input=memory.get())

    @step
    async def handle_llm_input(self, ctx: Context, ev: InputEvent) -> Union[ToolCallEvent, StopEvent]:
        response_stream = await self.llm.stream_chat_with_tools(
            self.tools, chat_history=ev.input
        )
        final_response = None
        async for response in response_stream:
            final_response = response
            ctx.write_event_to_stream(StreamEvent(delta=response.delta or ""))
        
        memory = await ctx.store.get("memory")
        memory.put(final_response.message)
        await ctx.store.set("memory", memory)
        
        tool_calls = self.llm.get_tool_calls_from_response(final_response, error_on_no_tool_call=False)
        if not tool_calls:
            return StopEvent(result={"response": final_response.message.content})
        return ToolCallEvent(tool_calls=tool_calls)

    @step
    async def handle_tool_calls(self, ctx: Context, ev: ToolCallEvent) -> InputEvent:
        tools_by_name = {tool.metadata.get_name(): tool for tool in self.tools}
        tool_msgs = []
        for tool_call in ev.tool_calls:
            tool = tools_by_name.get(tool_call.tool_name)
            tool_output = tool(**tool_call.tool_kwargs) if tool else None
            tool_msgs.append(ChatMessage(
                role="tool",
                content=tool_output.content if tool else f"Tool {tool_call.tool_name} does not exist",
            ))
        
        memory = await ctx.store.get("memory")
        for msg in tool_msgs:
            memory.put(msg)
        await ctx.store.set("memory", memory)
        return InputEvent(input=memory.get())

# Run the workflow
workflow = ChatWorkflow(llm=llm, tools=[bash_tool], timeout=120)
result = await workflow.run(input=prompt)
final_text = result["response"]
```

**Key LlamaIndex Workflows concepts used**:
- `Event` — typed data containers that flow between steps (extend `Event` base class)
- `@step` — decorator marking async functions as workflow steps
- `StartEvent` — built-in event to initiate the workflow (contains initial input)
- `StopEvent` — built-in event to terminate the workflow (contains final result)
- `Context` (`ctx`) — provides `ctx.store` for persistent state across steps
- `ctx.store.set()` / `ctx.store.get()` — key-value storage that persists across step invocations
- `ctx.write_event_to_stream()` — writes events to the SSE stream for client-side updates
- **Type-driven routing** — workflow routes events based on step type annotations (e.g., step returning `InputEvent` → next step accepting `InputEvent`)
- **Loops** — natural loops form when a step returns an event type that another step consumes (e.g., `ToolCallEvent → handle_tool_calls → InputEvent → handle_llm_input → ToolCallEvent`)
- **Conditional routing** — step returns different event types (`Union[ToolCallEvent, StopEvent]`), workflow routes accordingly
- `timeout=120` — max workflow runtime in seconds (prevents infinite loops)

### 3. Tool Output Structure

Tool results are extracted from `result["response"]` and `ToolOutput.content` strings:
- `stdout` — green-tinted output card with dark terminal background
- `stderr` — red-tinted card for error streams
- `error` — inline error message if execution failed

---

## Key Dependencies

```json
{
  "dependencies": {
    "llama-index-core": "^0.x",
    "llama-index-llms-openai-compatible": "^0.x",
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
cd liw
pip install llama-index-core llama-index-llms-openai-compatible
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=liw`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **next.config.mjs** rewrites the request to `liw` backend on `:5000`
4. **API Route** creates a `ChatWorkflow` with LLM + bash tool + typed steps
5. **Workflow** starts with `StartEvent(input=prompt)` → `prepare_chat_history()` step
6. **prepare_chat_history** builds chat history and returns `InputEvent`
7. **InputEvent** triggers `handle_llm_input()` step → LLM call with tools
8. **LLM** processes chat history, may emit tool calls
9. **handle_llm_input** routes to `ToolCallEvent` (if tools) or `StopEvent` (if done)
10. **ToolCallEvent** triggers `handle_tool_calls()` step
11. **handle_tool_calls** executes `bash_tool()` via `FunctionTool` (30s timeout)
    - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
12. **Tool results** added to memory; `InputEvent` returned → loop back to step 7
13. **Workflow** terminates when `StopEvent` is emitted
14. **API Route** returns `{ text: result["response"], toolOutputs[] }`
15. **Frontend** displays response text and tool output cards

---

## Streaming Considerations

LlamaIndex Workflows support streaming via `ctx.write_event_to_stream()` and `handler.stream_events()`:

```python
# Stream events from the workflow
handler = await workflow.run(input=prompt, return_messages=True)
for event in handler.stream_events():
    # Emit events to client via SSE
```

The `handle_llm_input()` step already uses `stream_chat_with_tools()` for token-level streaming and writes `StreamEvent(delta=...)` chunks to the event stream.

---

## Future Considerations

- **Streaming**: Use `handler.stream_events()` with SSE for real-time response streaming
- **Human-in-the-loop**: Pause at a step and resume via `WorkflowServer` + `WorkflowClient`
- **Persistence**: Save `Context` to database for cross-session conversation history
- **Parallel steps**: Use workflow parallelism for independent tool executions
- **Nested workflows**: Embed sub-workflows within parent workflows
- **Observability**: Add Llamatrace/OpenTelemetry tracing
- **WorkflowServer**: Deploy workflows as REST APIs via `WorkflowServer`
- **AgentWorkflow**: Use built-in `AgentWorkflow` for simpler agent setups
- **Multi-agent patterns**: Combine agents as tools via `AgentWorkflow`
- **Add request/response logging**
- **Configure environment variables for API credentials**
- **Add loading states for individual workflow steps**
- **Support streaming tool outputs via SSE**

---

## LlamaIndex Workflows vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | LlamaIndex Workflows |
|---------------|---------------------|
| `generateText()` | `Workflow.run(input=prompt)` |
| `tool({ parameters, execute })` | `FunctionTool.from_defaults(func)` |
| `maxSteps: 5` | `timeout=120` (runtime limit) |
| Tool result as object | Tool result as `ToolOutput` (.content string) |
| Built-in streaming (`useChat`) | `handler.stream_events()` + `ctx.write_event_to_stream()` |
| Auto message history | Explicit `ChatMemoryBuffer` + `ctx.store` |
| Implicit tool routing | Typed event routing (`Union[ToolCallEvent, StopEvent]`) |
| `ai` package | `llama-index-core` (Workflows included) |
| Single function call | Multi-step event-driven workflow |

## LlamaIndex Workflows vs LangChain: Key Mapping

| LangChain (createReactAgent) | LlamaIndex Workflows |
|------------------------------|---------------------|
| `createReactAgent({ llm, tools })` | `ChatWorkflow(llm, tools, steps)` |
| `StateGraph` with nodes/edges | `@step` functions with typed events |
| `maxIterations: 5` | `timeout=120` (time-based, not count-based) |
| `MemorySaver` | `ctx.store` (built-in key-value) + `ChatMemoryBuffer` |
| `invoke()` | `run(input=...)` |
| `stream()` | `handler.stream_events()` |
| `HumanMessage`/`AIMessage` | `ChatMessage` objects |
| `thread_id` in configurable | `Context` object passed to `run()` |
| Explicit nodes/edges | Typed event routing |

## LlamaIndex Workflows vs CrewAI: Key Mapping

| CrewAI | LlamaIndex Workflows |
|--------|---------------------|
| `Crew.kickoff()` | `Workflow.run(input=...)` |
| `Agent` + `Task` + `Crew` | Single `Workflow` with typed steps |
| 3-layer abstraction | 1-layer: events + steps |
| `maxIter: 5` | `timeout=120` |
| Tool as class | `FunctionTool.from_defaults(func)` |
| Sequential process | Event-driven (loops, conditionals, parallel) |
| Role/goal/backstory | Step functions (no roles) |

## LlamaIndex Workflows vs Agno: Key Mapping

| Agno | LlamaIndex Workflows |
|------|---------------------|
| `Agent.run(user=prompt)` | `Workflow.run(input=prompt)` |
| Python function as tool | `FunctionTool.from_defaults(func)` |
| `tool_call_limit=5` | `timeout=120` |
| `RunOutput` | `dict` result from `StopEvent` |
| `stream=True` | `handler.stream_events()` |
| `session_id` | `Context` object |
| Automatic agent loop | Explicit step-by-step event routing |
| `Agent` (1 primitive) | `Workflow` + `Event` + `@step` (3 primitives) |
| `Team` / `Workflow` primitives | Nested workflows, parallel steps |

## LlamaIndex Workflows vs LangGraph: Key Mapping

| LangGraph | LlamaIndex Workflows |
|-----------|---------------------|
| `StateGraph().addNode().compile()` | `Workflow` with `@step` functions |
| `Annotation.Root` state | `Event` classes + `ctx.store` |
| `maxIter: 5` | `timeout=120` |
| `MemorySaver` | `ctx.store` (built-in) |
| `invoke()` | `run(input=...)` |
| `stream()` with `StreamMode` | `handler.stream_events()` |
| Conditional edges (`addConditionalEdges`) | `Union[EventA, EventB]` return type |
| `addEdge()` | Type-driven automatic routing |
| Human-in-the-loop (`interrupt`) | `WorkflowServer` + `WorkflowClient` |
| Python + JS support | Python-first |

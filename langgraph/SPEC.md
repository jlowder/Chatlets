# Chatlets — LangGraph.js Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using LangGraph.js's explicit state machine approach. State, nodes, and edges are all defined by hand, giving full control over the agent's execution graph — including conditional routing, human-in-the-loop interrupts, and composable sub-graphs.

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
│  next.config.mjs (CHATLET_BACKEND=langgraph)                │
│  rewrites → langgraph backend on :5000                     │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { prompt }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              langgraph backend (port 5000)                 │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ StateGraph      │───▶│ bash Tool                   │   │
│  │ .addNode()      │    │  - zod input schema          │   │
│  │ .compile()      │    │  - execAsync(cmd, timeout)   │   │
│  │ .invoke()       │    │  - 30s timeout              │   │
│  │                 │    │  - returns stdout/stderr     │   │
│  │  ┌────────────┐ │    └───────────────────────────────┘   │
│  │  │   prompt   │ │    ▲                            │      │
│  │  └────────────┘ │    │                            │      │
│  │        │        └────┼────────────────────────────┘         │
│  │        └─────────────┼────────────────────────────┘         │
│  │            │         │                                     │
│  │            ▼         │                                     │
│  │  ┌──────────────┐    │                                     │
│  │  │  Return JSON │◀───┼─────────────────────────────────────┤
│  │  │  - text      │    │                                     │
│  │  │  - toolCalls─────┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call                            │
         │ max_iter: 5 (max graph iterations)                    │
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
| **Agent Graph** | LangGraph.js | 0.2.x |
| **Core** | @langchain/core | 0.3.x |
| **Provider** | @langchain/openai | 0.3.x |
| **Validation** | Zod | 3.25.0 |
| **Type Safety** | TypeScript | 5.x |

---

## Key Components

### `app/api/chat/route.ts`

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference via a LangGraph state machine

```ts
Key imports:
  - ChatOpenAI from @langchain/openai
  - { StateGraph, MessagesAnnotation, Annotation } from "@langchain/langgraph"
  - { ToolMessage, AIMessage, HumanMessage } from "@langchain/core/messages"
  - { z } from "zod"

Key exports:
  - POST(req: NextRequest)

Configuration:
  - model: ChatOpenAI with openai-compatible baseURL
  - tools: [bashTool]
  - graph: explicit StateGraph with model node + tools node
  - maxIter: 5 (via graph compile config)
```

### State Definition

**Type**: Typed state annotation  
**Purpose**: Define the persistent state schema for the execution graph

```ts
import { Annotation, MessagesAnnotation } from "@langchain/langgraph";

const ChatAnnotation = Annotation.Root({
  ...MessagesAnnotation.spec,  // inherits messages array
  allowList: Annotation<string[]>({
    reducer: (state, update) => update,
    default: () => ["ls", "pwd"],
  }),
  allowAll: Annotation<boolean>({
    reducer: (state, update) => update ?? false,
    default: () => false,
  }),
});
```

### Node Functions

```ts
async function modelNode(state: typeof ChatAnnotation.State) {
  const response = await model.invoke(state.messages);
  return { messages: [response] };
}

async function toolsNode(state: typeof ChatAnnotation.State) {
  // Execute tool calls and return ToolMessage results
  const toolMessages = await executeToolCalls(state.messages, bashTool);
  return { messages: toolMessages };
}
```

### Bash Tool

**Type**: LangChain Tool (`extends Tool`)  
**Purpose**: Safely execute shell commands with allow-list enforcement

```ts
import { Tool } from "@langchain/core/tools";
import { z } from "zod";

class BashTool extends Tool {
  name = "bash";
  description = `Execute a bash command on the server. You MUST provide a "command"
  parameter with the exact shell command to run. This is the ONLY way to run
  commands. For example: command="pwd", command="ls -la", command="npm run build".`;

  schema = z.object({
    command: z.string().describe('The bash/shell command to execute'),
  });

  async _call(input: z.infer<typeof this.schema>): Promise<string> {
    const { command } = input;
    // ... execute and return result
  }
}
```

---

## LLM Configuration

```ts
const model = new ChatOpenAI({
  modelName: 'modelName',
  baseUrl: 'baseUrl',
  apiKey: 'example',
  configuration: {
    maxRetries: 0,
  },
});
```

| Setting | Value |
|---------|-------|
| **Model** | `modelName` |
| **Base URL** | `baseUrl` |
| **API Key** | `example` |
| **Provider Type** | OpenAI-compatible (via `@langchain/openai`) |
| **Max Retries** | `0` (no retries) |

Configuration data is persisted to a file called `llm-config.json`.

---

## Bash Tool Design

### Schema Definition

```ts
import { z } from "zod";
import { Tool } from "@langchain/core/tools";

class BashTool extends Tool {
  name = "bash";
  description = `Execute a bash command on the server. You MUST provide a "command"
  parameter with the exact shell command to run. This is the ONLY way to run
  commands. For example: command="pwd", command="ls -la", command="npm run build".`;

  schema = z.object({
    command: z.string().describe('The bash/shell command to execute'),
  });

  async _call(input: z.infer<typeof this.schema>): Promise<string> {
    const { command } = input;
    // ... execute and return result
  }
}
```

### Execution Configuration

| Setting | Value |
|---------|-------|
| **Command Runner** | `child_process.exec` (promisified) |
| **Timeout** | 30,000 ms (30 seconds) |
| **Captured Output** | `stdout`, `stderr`, `error` |
| **maxIter** | 5 (multi-step reasoning) |

### Allow List Filtering

The bash tool enforces an allow list that restricts which commands can be executed. Before running a command, the tool checks if the base command (first word) is in the allow list.

### Return Types

LangChain tools return a **string** that gets wrapped in a `ToolMessage`. The string representation:

```ts
// Success (returned as string)
JSON.stringify({
  stdout: string,  // Trimmed
  stderr: string   // Trimmed
})

// Error (returned as string)
JSON.stringify({
  error: string,   // Error message
  stdout: string,  // Trimmed (may be partial)
  stderr: string   // Trimmed
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

## Graph Architecture

### Node & Edge Definition

```ts
const graph = new StateGraph(ChatAnnotation)
  .addNode("model", modelNode)
  .addNode("tools", toolsNode)
  .addEdge("__start__", "model")
  .addConditionalEdges("model", routeResponse, {
    tools: "tools",
    __end__: "__end__",
  })
  .addEdge("tools", "model")
  .compile({
    checkpointSaver: new MemorySaver(),
    maxIter: 5,
    name: "chat-agent",
  });

const result = await graph.invoke({
  messages: [new HumanMessage(prompt)],
  allowList: ["ls", "pwd"],
  allowAll: false,
}, {
  configurable: {
    thread_id: "chat-session-id",
  },
});
```

### Graph Flow

```
__start__ → model → { tools | __end__ }
                    ↓          ↑
                 tools → model
```

**Key LangGraph concepts used**:
- `Annotation.Root` / `MessagesAnnotation` — define a typed, persistent state schema
- `addNode()` — each node is an async function that receives state and returns partial state updates
- `addConditionalEdges()` — dynamic routing based on state (e.g., "has tool calls?" → loop back to model)
- `addEdge()` — fixed transitions (tools → model, start → model)
- `.compile()` — produces an executable graph with checkpointing
- `MemorySaver` / `SqliteSaver` / `PostgresSaver` — persistent state across invocations (thread-safe)
- `maxIter` — limits graph iterations to prevent infinite loops
- `thread_id` — enables multi-conversation state isolation

### Conditional Routing

```ts
function routeResponse(state: typeof ChatAnnotation.State) {
  const lastMessage = state.messages[state.messages.length - 1];
  if ("tool_calls" in lastMessage && lastMessage.tool_calls?.length > 0) {
    return "tools";
  }
  return "__end__";
}
```

---

## Checkpointing & State Management

LangGraph uses checkpointing for state persistence across steps. This enables resumable execution, human-in-the-loop interrupts, and multi-threaded conversations.

```ts
const graph = new StateGraph(ChatAnnotation)
  .addNode("model", modelNode)
  .addNode("tools", toolsNode)
  .addEdge("__start__", "model")
  .addConditionalEdges("model", routeResponse, {
    tools: "tools",
    __end__: "__end__",
  })
  .addEdge("tools", "model")
  .compile({
    checkpointSaver: new MemorySaver(),
    maxIter: 5,
    name: "chat-agent",
  });
```

**Checkpoint Saver Options**:

| Saver | Use Case | Persistence |
|-------|----------|-------------|
| `MemorySaver` | Development, single-process | In-memory, lost on restart |
| `SqliteSaver` | Production, single-machine | SQLite file, survives restarts |
| `PostgresSaver` | Production, distributed | PostgreSQL, thread-safe across processes |

**Key message objects**:
- `HumanMessage` — user's prompt text
- `AIMessage` — LLM's response (may include tool calls)
- `ToolMessage` — bash tool execution result (stdout/stderr/error)

---

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, makes LLM calls
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. LangGraph State Machine Pattern

```ts
const graph = new StateGraph(ChatAnnotation)
  .addNode("model", modelNode)
  .addNode("tools", toolsNode)
  .addEdge("__start__", "model")
  .addConditionalEdges("model", routeResponse, {
    tools: "tools",
    __end__: "__end__",
  })
  .addEdge("tools", "model")
  .compile({
    checkpointSaver: new MemorySaver(),
    maxIter: 5,
    name: "chat-agent",
  });

const result = await graph.invoke({
  messages: [new HumanMessage(prompt)],
}, {
  configurable: { thread_id: "chat-session-id" },
});
```

**Key differences from Vercel AI SDK**:
- LangGraph agents use explicit state machines (not hidden abstraction)
- Nodes and edges are hand-authored, giving full control over execution flow
- `addConditionalEdges()` enables dynamic routing (e.g., loop on tool calls, exit otherwise)
- `maxIter` limits graph iterations to prevent infinite loops
- `thread_id` enables multi-conversation state isolation

### 3. Human-in-the-Loop

LangGraph supports pausing execution at any node and resuming via `graph.updateState()`:

```ts
// Pause at the tools node for human approval
await graph.updateState(config, { messages: [new ToolMessage(result)] });

// Resume from checkpoint
const result = await graph.invoke(null, { configurable });
```

### 4. Composability

Sub-graphs can be composed as nodes within a parent graph:

```ts
// A research sub-graph
const researchGraph = new StateGraph(ResearchAnnotation)
  .addNode("search", searchNode)
  .addNode("summarize", summarizeNode)
  .compile();

// Use as a node in the main graph
const graph = new StateGraph(ChatAnnotation)
  .addNode("research", researchGraph)  // sub-graph as node
  // ... other nodes
  .compile();
```

### 5. Tool Output Structure

Tool results are extracted from `result.messages[]` as `ToolMessage` objects containing:
- `stdout` — green-tinted output card with dark terminal background
- `stderr` — red-tinted card for error streams
- `error` — inline error message if execution failed

---

## Key Dependencies

```json
{
  "dependencies": {
    "@langchain/core": "^0.3.x",
    "@langchain/langgraph": "^0.2.x",
    "@langchain/openai": "^0.3.x",
    "zod": "^3.25.0",
    "next": "16.2.10 (for API routes only)"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^19",
    "eslint": "^9",
    "typescript": "^5"
  }
}
```

---

## Running

```bash
cd langgraph
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=langgraph`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **next.config.mjs** rewrites the request to `langgraph` backend on `:5000`
4. **API Route** builds a LangGraph `StateGraph` with `model` node + `tools` node
5. **Graph** starts at `model` node, invoking the LLM with `[new HumanMessage(prompt)]`
6. **LLM** processes prompt and may emit tool calls
7. **Router** checks `lastMessage.tool_calls` — if present, routes to `tools` node via `addConditionalEdges()`
8. **Tools Node** executes each tool (bash command via `execAsync()`, 30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
9. **Graph** loops back to `model` node with tool results
10. **Graph** repeats up to `maxIter: 5` times, then ends
11. **API Route** returns `{ text, toolOutputs[] }` extracted from final state messages
12. **Frontend** displays response text and tool output cards

---

## Streaming Considerations

LangGraph supports streaming via `graph.stream()`:

```ts
// Streaming approach (future enhancement)
for await (const chunk of graph.stream({
  messages: [new HumanMessage(prompt)],
}, { streamMode: "events" })) {
  // Emit events to client via SSE
}
```

Available `StreamMode` options:
- `"events"` — fine-grained event stream (model start/end, tool start/end, etc.)
- `"messages"` — message-by-message updates
- `"updates"` — full state updates at each step

---

## Future Considerations

- Checkpoint persistence: Swap `MemorySaver` for `SqliteSaver` or `PostgresSaver` for production
- Add streaming: Use `graph.stream()` with `StreamMode.events` or `StreamMode.messages`
- Human-in-the-loop: Pause at a node and resume via `graph.updateState()`
- Multi-agent: Compose multiple sub-graphs as nodes in a parent graph
- Add request/response logging
- Configure environment variables for API credentials
- Add loading states for individual graph steps
- Support streaming tool outputs via SSE
- Add team-based allow list defaults via shared state

---

## LangGraph vs LangChain: Key Mapping

| LangChain (createReactAgent) | LangGraph (StateGraph) |
|------------------------------|------------------------|
| `createReactAgent({ llm, tools })` | `new StateGraph().addNode().addEdge().compile()` |
| Hidden state management | Explicit `Annotation.Root` state schema |
| Hidden node/edge structure | Hand-authored nodes and conditional edges |
| `maxIterations: 5` | `maxIter: 5` in `.compile()` config |
| `MemorySaver` (convenience) | `MemorySaver` / `SqliteSaver` / `PostgresSaver` (first-class) |
| `thread_id` in configurable | `thread_id` in configurable (same API) |
| `invoke()` | `invoke()` (same interface) |
| `stream()` | `stream()` with `StreamMode` options |
| Implicit ReAct loop | Explicit `model → tools → model` graph edges |
| One-shot agent builder | Composable sub-graphs, interrupts, human-in-the-loop |

## LangGraph vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | LangGraph |
|---------------|-----------|
| `generateText()` | `StateGraph.compile().invoke()` |
| `tool({ parameters, execute })` | `class extends Tool { schema, _call() }` |
| `maxSteps: 5` | `maxIter: 5` |
| Tool result as object | Tool result as JSON string (wrapped in `ToolMessage`) |
| Built-in streaming (`useChat`) | `graph.stream()` with `StreamMode` |
| Auto message history | Explicit `Annotation.Root` with messages |
| Implicit tool routing | Conditional edges with `routeResponse()` |
| `ai` package | `@langchain/langgraph` + `@langchain/core` |

## LangGraph vs CrewAI: Key Mapping

| CrewAI | LangGraph Equivalent |
|--------|----------------------|
| `new Agent()` | Implicit in node functions (`modelNode`) |
| `new Task()` | Messages passed to `graph.invoke()` |
| `new Crew()` | `new StateGraph().compile()` |
| `crew.kickoff()` | `graph.invoke()` |
| `class extends Tool` | `class extends Tool` (identical pattern) |
| `maxIter: 5` | `maxIter: 5` |
| CrewAI memory | `MemorySaver` / `SqliteSaver` |
| `crew.stream()` | `graph.stream()` with `StreamMode` |
| Declarative agent/task | Explicit node/edge graph definition |
| Process modes | Conditional edges + interrupts |

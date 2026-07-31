# Chatlets — LangChain.js Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using LangChain.js and LangGraph.js. The app uses `createReactAgent()` for ReAct-style reasoning with tool use, backed by a checkpoint saver for state persistence across steps.

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
│  next.config.mjs (CHATLET_BACKEND=langchain)                │
│  rewrites → langchain backend on :5000                     │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { prompt }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              langchain backend (port 5000)                 │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ createReactAgent│───▶│ bash Tool                   │   │
│  │ + agent.invoke()│    │  - zod input schema          │   │
│  │                 │    │  - execAsync(cmd, timeout)   │   │
│  │  ┌────────────┐ │    │  - 30s timeout              │   │
│  │  │   prompt   │ │    │  - returns stdout/stderr     │   │
│  │  └────────────┘ │    └───────────────────────────────┘   │
│  │        │        │    ▲                            │      │
│  │        └─────────┼────────────────────────────┘         │
│  │            │       │                                     │
│  │            ▼       │                                     │
│  │  ┌──────────────┐  │                                     │
│  │  │  Return JSON │◀─┼─────────────────────────────────────┤
│  │  │  - text      │  │                                     │
│  │  │  - toolCalls────┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call                            │
         │ max_iterations: 5 (max tool-call cycles)              │
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
| **Agent Framework** | LangChain.js | 0.3.x |
| **Agent Graph** | @langchain/langgraph | 0.2.x |
| **Core** | @langchain/core | 0.3.x |
| **Provider** | @langchain/openai | 0.3.x |
| **Validation** | Zod | 3.25.0 |
| **Type Safety** | TypeScript | 5.x |

---

## Key Components

### `app/api/chat/route.ts`

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference and tool execution via `createReactAgent()`

```ts
Key imports:
  - ChatOpenAI from @langchain/openai
  - { createReactAgent } from "@langchain/langgraph"
  - { ToolMessage, AIMessage, HumanMessage } from "@langchain/core/messages"
  - { z } from "zod"

Key exports:
  - POST(req: NextRequest)

Configuration:
  - model: ChatOpenAI with openai-compatible baseURL
  - tools: [bashTool]
  - maxIterations: 5
  - checkpointSaver: MemorySaver / SqliteSaver / PostgresSaver
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
| **maxIterations** | 5 (multi-step reasoning) |

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

## Checkpointing & State Management

LangGraph agents use checkpointing for state persistence across steps. This enables multi-turn conversations and resumable agent execution.

```ts
const agent = createReactAgent({
  llm: model,
  tools: [bashTool],
  checkpointSaver: new MemorySaver(),  // or SqliteSaver / PostgresSaver
  messageWriter: undefined,  // optional: write messages to stdout
});

const result = await agent.invoke({
  messages: [new HumanMessage(prompt)],
}, {
  configurable: {
    thread_id: "chat-session-id",
  },
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

### 2. LangChain Agent Pattern

```ts
const agent = createReactAgent({
  llm: model,
  tools: [bashTool],
  checkpointSaver: new MemorySaver(),  // or SqliteSaver / PostgresSaver
  messageWriter: undefined,  // optional
});

const result = await agent.invoke({
  messages: [new HumanMessage(prompt)],
}, {
  configurable: {
    thread_id: "chat-session-id",
  },
});
```

**Key differences from Vercel AI SDK**:
- LangGraph agents use checkpointing for state persistence across steps
- Messages are explicit `HumanMessage`/`AIMessage`/`ToolMessage` objects
- `createReactAgent` provides ReAct-style reasoning with tool use
- `maxIterations` limits the number of tool call/response cycles

### 3. Tool Output Structure

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
cd langchain
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=langchain`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ prompt }`
3. **next.config.mjs** rewrites the request to `langchain` backend on `:5000`
4. **API Route** creates a LangGraph agent via `createReactAgent()` with LLM + bash tool
5. **Agent** invokes the LLM with `[new HumanMessage(prompt)]`
6. **LLM** processes prompt, may call bash tool (up to `maxIterations: 5`)
7. **Bash Tool** executes command via `execAsync()` (30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
8. **Agent** collects tool results (as `ToolMessage` objects) and continues until final answer
9. **API Route** returns `{ text, toolOutputs[] }` extracted from agent messages
10. **Frontend** displays response text and tool output cards

---

## Streaming Considerations

LangChain.js supports streaming via `StreamEvents` from `@langchain/core`:

```ts
// Streaming approach (future enhancement)
for await (const event of streamEvents) {
  if (event.event === "on_chat_model_stream") {
    // Stream token to client via SSE
  }
  if (event.event === "on_tool_start") {
    // Emit tool invocation event
  }
}
```

Manual SSE + `StreamEvents` provides granular control over streaming tokens and tool outputs, unlike Vercel AI SDK's built-in `useChat` streaming.

---

## Future Considerations

- Checkpoint persistence: Swap `MemorySaver` for `SqliteSaver` or `PostgresSaver` for thread-safe state
- Add streaming responses via `StreamEvents` from `@langchain/core/messages`
- Support multi-turn conversation history with LangGraph checkpointing
- Add request/response logging
- Configure environment variables for API credentials
- Add loading states for individual tool calls
- Support streaming tool outputs via SSE
- Add team-based allow list defaults via shared state

---

## LangChain.js vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | LangChain.js Equivalent |
|---------------|------------------------|
| `createOpenAICompatible()` | `new ChatOpenAI({ baseUrl, apiKey, modelName })` |
| `generateText()` | `createReactAgent().invoke()` |
| `tool({ parameters, execute })` | `class extends Tool { schema, _call() }` |
| `maxSteps: 5` | `maxIterations: 5` |
| Tool result as object | Tool result as JSON string (wrapped in `ToolMessage`) |
| Built-in streaming (`useChat`) | Manual SSE + `StreamEvents` |
| Auto message history | Explicit `HumanMessage`/`AIMessage` management |
| Memory state | `MemorySaver` / `CheckpointSaver` |

## LangChain.js vs CrewAI: Key Mapping

| CrewAI | LangChain.js Equivalent |
|--------|------------------------|
| `new Agent()` | Implicit in `createReactAgent()` |
| `new Task()` | Passed as messages to `agent.invoke()` |
| `new Crew()` | Replaced by `createReactAgent()` graph |
| `crew.kickoff()` | `agent.invoke({ messages })` |
| `class extends Tool` | `class extends Tool` (identical pattern) |
| `maxIter: 5` | `maxIterations: 5` |
| CrewAI memory | `MemorySaver` / `SqliteSaver` |
| `crew.stream()` | `StreamEvents` iteration |

# Chatlets — Mastra Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using the Mastra framework. An `Agent` is defined with a model, instructions, and tools, then invoked via `agent.generate()`. Mastra provides production-grade features: model routing (40+ providers), memory, signals, workflows, and observability.

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
│  next.config.mjs (CHATLET_BACKEND=mastra)                   │
│  rewrites → mastra backend on :5000                        │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { messages }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              mastra backend (port 5000)                    │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ agent.generate()│───▶│ bash Tool (via Mastra)       │   │
│  │                 │    │  - createTool() + Zod        │   │
│  │  ┌────────────┐ │    │  - execAsync(cmd, timeout)   │   │
│  │  │  messages  │ │    │  - 30s timeout              │   │
│  │  └────────────┘ │    │  - returns stdout/stderr     │   │
│  │        │        │    └───────────────────────────────┘   │
│  │        │           ▲                            │         │
│  │        └───────────┼────────────────────────────┘         │
│  │            │       │                                     │
│  │            ▼       │                                     │
│  │  ┌──────────────┐  │                                     │
│  │  │  Return JSON │◀─┼─────────────────────────────────────┤
│  │  │  - text      │  │                                     │
│  │  │  - toolCalls──┘                                │      │
│  │  └──────────────┘                                   │      │
│  └─────────────────┘                                   │      │
│        │                                               │      │
└────────┼────────────────────────────────────────────────┘      │
         │                                                       │
         │ OpenAI-compatible API call via Model Router          │
         │ maxSteps: 5 (multi-step reasoning)                    │
         │ Allow List Check                                      │
         │                                                       │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                    LLM via Model Router (40+ providers)           │
└────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### `POST /api/chat`

| Property | Value |
|----------|-------|
| **Content-Type** | `application/json` |
| **Request Body** | `{ messages: Array<{ role, content }> }` |
| **Success Response** | `{ text: string, toolOutputs: { stdout?: string, stderr?: string, error?: string }[] }` |
| **Error Response** | `{ error: string }` |

---

## API Contract

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `object[]` | Yes | Array of `{ role, content }` message objects |
| `text` | `string` | Yes | LLM response text |
| `toolOutputs` | `object[]` | No | Array of bash tool execution results |
| `error` | `string` | No | Error message if request fails |

---

## Session Memory

The API supports full conversation history. Every request sends the complete message array, allowing the agent to reference prior turns. The last message in the array is always the new user input; all prior messages provide context.

- **Request shape**: `{ messages: Array<{ role: "user" | "assistant", content: string }> }`
- **History length**: No hard limit — the full conversation is sent each turn
- **Fallback**: If the request contains only `{ prompt: string }` (legacy format), the backend treats it as a single-user-message conversation

### Implementation (mastra)

The backend joins the messages array into a conversation string and passes it to `agent.generate()`:

```typescript
// Backend receives { messages: [{role, content}, ...] }
const conversation = messages.map(m => `${m.role}: ${m.content}`).join("\n");
const result = await agent.generate(conversation, { maxSteps: 5 });
```

---

## Technical Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Agent Framework** | @mastra/core | Latest |
| **Model Provider** | @ai-sdk/openai-compatible-v6 | (via Mastra Model Router) |
| **Validation** | Zod | 3.25.0 |
| **Type Safety** | TypeScript | 5.x |

---

## Key Components

### `app/api/chat/route.ts`

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference and tool execution via Mastra Agent

```ts
Key exports:
  - POST(req: NextRequest)

Configuration:
  - Model: OpenAI-compatible via Mastra Model Router
    - Config: { id: "custom/model", url: baseURL, apiKey }
  - tools: { bash }
  - maxSteps: 5
```

### Agent Definition

**Type**: `Agent` class from `@mastra/core`  
**Purpose**: Define an agent with model, instructions, and tools

```ts
import { Agent } from '@mastra/core/agent';

const agent = new Agent({
  id: 'chat-agent',
  name: 'Chat Agent',
  instructions: 'You are a helpful assistant. Use the bash tool when necessary.',
  model: openaiCompatible('modelName', { baseURL, apiKey }),
  tools: { bash: bashTool },
});
```

### Bash Tool

**Type**: `createTool()` from `@mastra/core/tools`  
**Purpose**: Define a tool with Zod input schema and execute function

```ts
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const bashTool = createTool({
  id: 'bash',
  description: `Execute a bash command on the server. You MUST provide a "command"
  parameter with the exact shell command to run.`,
  inputSchema: z.object({
    command: z.string().describe('The bash/shell command to execute'),
  }),
  execute: async ({ command }, context) => { ... }
});
```

---

## LLM Configuration

### Mastra Model Resolution

Mastra uses a Model Router that accepts OpenAI-compatible configuration via `OpenAICompatibleConfig`:

```ts
const model: MastraModelConfig = {
  id: 'provider-name/model-name',  // e.g., 'openai/gpt-4o' or 'custom/my-model'
  url: 'baseUrl',                   // OpenAI-compatible endpoint
  apiKey: 'apiKey',
};
```

Alternatively, a provider tool can be created directly:

```ts
import { createOpenAICompatible } from '@ai-sdk/openai-compatible-v6';

const provider = createOpenAICompatible({
  name: 'provider-name',
  baseURL: 'baseUrl',
  apiKey: 'example',
  supportsStructuredOutputs: true,
});

const model = provider.chatModel('modelName');
```

| Setting | Value |
|---------|-------|
| **Model** | `modelName` (via provider.chatModel) or `{ id, url, apiKey }` |
| **Base URL** | `baseUrl` (custom OpenAI-compatible endpoint) |
| **API Key** | `apiKey` (or falls back to env vars) |
| **Provider Type** | `@ai-sdk/openai-compatible-v6` (via Mastra Model Router) |
| **Max Retries** | `0` (no retries) |

Configuration data is persisted to a file called `config.json` (same format as vercel-ai).

---

## Bash Tool Design

### Schema Definition

```ts
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const bashTool = createTool({
  id: 'bash',
  description: `Execute a bash command on the server. You MUST provide a "command" 
  parameter with the exact shell command to run. This is the ONLY way to run 
  commands. For example: command="pwd", command="ls -la", command="npm run build".`,
  
  inputSchema: z.object({
    command: z.string().describe('The bash/shell command to execute'),
  }),
  
  execute: async ({ command }, context) => { ... }
});
```

### Execution Configuration

| Setting | Value |
|---------|-------|
| **Command Runner** | `child_process.exec` (promisified) |
| **Timeout** | 30,000 ms (30 seconds) |
| **Captured Output** | `stdout`, `stderr`, `error` |
| **maxSteps** | 5 (multi-step reasoning) |

### Allow List Filtering

The bash tool enforces an allow list that restricts which commands can be executed. Before running a command, the tool checks if the base command (first word) is in the allow list.

### Return Types

```ts
// Success
{
  stdout: string,  // Trimmed
  stderr: string   // Trimmed
}

// Error
{
  error: string,   // Error message
  stdout: string,  // Trimmed (may be partial)
  stderr: string   // Trimmed
}
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

## Mastra Architecture

### Model Router

Mastra's Model Router abstracts LLM providers, supporting **40+ providers** through a unified interface:

```ts
import { createOpenAICompatible } from '@ai-sdk/openai-compatible-v6';
import { Mastra } from '@mastra/core';

const provider = createOpenAICompatible({
  name: 'custom-provider',
  baseURL: 'https://api.example.com/v1',
  apiKey: process.env.API_KEY,
});

const mastra = new Mastra({
  engines: {},
  // Register provider with Model Router
});
```

**Key benefits**:
- Switch providers without changing agent code
- Unified configuration across OpenAI, Anthropic, Google, Azure, and 40+ others
- OpenAI-compatible endpoint support via `@ai-sdk/openai-compatible-v6`

### Agent Pattern

```ts
import { Agent } from '@mastra/core/agent';

const agent = new Agent({
  id: 'chat-agent',
  name: 'Chat Agent',
  instructions: 'You are a helpful assistant that can execute bash commands.',
  model: provider.chatModel('modelName'),
  tools: { bash: bashTool },
});

const result = await agent.generate(prompt, { maxSteps: 5 });
```

### Memory

Mastra provides built-in memory for conversation persistence:

```ts
import { Memory } from '@mastra/core/memory';

const memory = new Memory({
  mastra,
  storage: new SQLiteStorage(),  // or InMemoryStorage for dev
});

// Attach to agent
const agent = new Agent({
  id: 'chat-agent',
  memory: memory,
  // ...
});
```

### Signals

Signals enable real-time event streaming between agents and workflows:

```ts
import { Mastra } from '@mastra/core';
import { Subject } from 'rxjs';

const mastra = new Mastra({
  // Signals configuration
});

// Subscribe to agent events
const subscription = mastra.signals.subscribe('agent:generate', (event) => {
  console.log('Agent step:', event);
});
```

### Workflows

Mastra integrates workflows for multi-step orchestration:

```ts
import { Workflow, step } from '@mastra/core/workflows';

const workflow = new Workflow({ name: 'chat-workflow' })
  .step({
    id: 'generate',
    validate: false,
    run: async ({ context }) => {
      return await agent.generate(context.input, { maxSteps: 5 });
    },
  })
  .commit();
```

---

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, invokes Mastra Agent
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. Mastra Agent Tool Calling

```ts
const agent = new Agent({
  id: 'chat-agent',
  name: 'Chat Agent',
  instructions: 'You are a helpful assistant...',
  model: myModel,  // OpenAI-compatible model
  tools: { bash: bashTool },
});

const result = await agent.generate(prompt, { maxSteps: 5 });
```

### 3. Tool Output Structure

Tool results are extracted from `result.toolResults[]` (from Mastra `FullOutput`):
- `stdout` — green-tinted output card with dark terminal background
- `stderr` — red-tinted card for error streams
- `error` — inline error message if execution failed

---

## Generation Result

```ts
const result = await agent.generate(prompt, { maxSteps: 5 });

// result (FullOutput):
//   .text         → Final assistant text response
//   .toolResults  → Array of { toolName, toolCallId, args, result, isError }
//   .steps        → Execution steps with reasoning, tool calls
//   .usage        → Token usage statistics
```

---

## Key Dependencies

```json
{
  "dependencies": {
    "@mastra/core": "latest",
    "@ai-sdk/openai-compatible-v6": "latest",
    "ai": "^7.0.34",
    "zod": "^3.25.0",
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
cd mastra
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=mastra`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ messages }`
3. **next.config.mjs** rewrites the request to `mastra` backend on `:5000`
4. **API Route** creates/gets Mastra Agent and builds a conversation string from the messages, then calls `agent.generate(conversation, { maxSteps: 5 })`
5. **Agent** processes the full conversation, may call bash tool (up to 5 steps)
6. **Bash Tool** executes command via `execAsync()` (30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
7. **Agent** returns `FullOutput` with `text` and `toolResults[]`
8. **API Route** returns `{ text, toolOutputs[] }`
9. **Frontend** displays response text and tool output cards

---

## Future Considerations

- Allow list enhancements: wildcard patterns (`ls*`), regex matching, per-session settings, shared team defaults
- Add streaming responses via `agent.stream()` with `onChunk` callback
- Support multi-turn conversation history with Mastra Memory
- Add request/response logging
- Configure environment variables for API credentials
- Add loading states for individual tool calls
- Support streaming tool outputs
- Add observability/tracing via Mastra Observability
- Leverage Mastra's MCP server capabilities for tool exposure

---

## Mastra vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | Mastra |
|---------------|--------|
| `generateText()` | `agent.generate(messages, { maxSteps })` |
| `tool({ parameters, execute })` | `createTool({ inputSchema, execute })` |
| `maxSteps: 5` | `maxSteps: 5` in `agent.generate()` options |
| Tool result as object | Tool result in `result.toolResults[]` |
| Built-in streaming (`useChat`) | `agent.stream()` with `onChunk` |
| Auto message history | `Memory` + `SQLiteStorage` |
| Implicit tool routing | Agent loop with `tools` map |
| `ai` package | `@mastra/core` + `@ai-sdk/openai-compatible-v6` |
| Stateless per-call | Agent instance with memory, signals, workflows |

## Mastra vs LangChain: Key Mapping

| LangChain (createReactAgent) | Mastra |
|------------------------------|--------|
| `createReactAgent({ llm, tools })` | `new Agent({ model, instructions, tools })` |
| `StateGraph` with nodes/edges | Implicit agent loop in `agent.generate()` |
| `maxIterations: 5` | `maxSteps: 5` |
| `MemorySaver` | `Memory` + `SQLiteStorage` |
| `invoke()` | `agent.generate()` |
| `stream()` | `agent.stream()` |
| `HumanMessage`/`AIMessage` | Internal message handling |
| `thread_id` in configurable | Session-based in `Memory` |
| `class extends Tool` | `createTool({ inputSchema, execute })` |

## Mastra vs CrewAI: Key Mapping

| CrewAI | Mastra |
|--------|--------|
| `Crew.kickoff()` | `agent.generate()` |
| `Agent` + `Task` + `Crew` | Single `Agent` with tools |
| 3-layer abstraction | 1-layer: Agent with optional Memory/Workflows |
| `maxIter: 5` | `maxSteps: 5` |
| Tool as class | `createTool({ inputSchema, execute })` |
| Sequential process | Agent loop (implicit) |
| Role/goal/backstory | `instructions` string |

## Mastra vs Agno: Key Mapping

| Agno | Mastra |
|------|--------|
| `Agent.run(user=prompt)` | `agent.generate(prompt)` |
| Python function as tool | `createTool({ inputSchema, execute })` |
| `tool_call_limit=5` | `maxSteps: 5` |
| `RunOutput` | `FullOutput` |
| `stream=True` | `agent.stream()` |
| `session_id` | `Memory` + session management |
| Automatic agent loop | Automatic agent loop |
| `Agent` (1 primitive) | `Agent` + `Memory` + `Workflow` + `Signals` |
| `Team` / `Workflow` primitives | `Workflow` class |

## Mastra vs LangGraph: Key Mapping

| LangGraph | Mastra |
|-----------|--------|
| `StateGraph().addNode().compile()` | `agent.generate()` (implicit) |
| `Annotation.Root` state | Internal message state |
| `maxIter: 5` | `maxSteps: 5` |
| `MemorySaver` | `Memory` + `SQLiteStorage` |
| `invoke()` | `agent.generate()` |
| `stream()` | `agent.stream()` |
| Explicit nodes/edges | Implicit agent loop |
| `interrupt` (HITL) | `Workflow` step control |
| Python + JS | TypeScript-only |

## Mastra vs LlamaIndex Workflows: Key Mapping

| LlamaIndex Workflows | Mastra |
|---------------------|--------|
| `Workflow.run(input=...)` | `agent.generate(prompt)` |
| `@step` functions with typed events | `workflow.step()` with async run |
| `Event` classes | Internal state objects |
| `ctx.store` | `Memory` + storage engine |
| `timeout=120` | Provider timeout |
| `FunctionTool.from_defaults(func)` | `createTool({ execute })` |
| Event-driven loops | Agent loop (implicit) |
| `Workflow` + `Event` + `@step` | `Agent` + `Memory` + `Workflow` |
| Python-first | TypeScript-first |

## Mastra vs Microsoft Agent Framework: Key Mapping

| MAF | Mastra |
|-----|--------|
| `Agent.run(prompt, session=session)` | `agent.generate(prompt)` |
| `@tool` decorated function | `createTool({ inputSchema, execute })` |
| `FunctionInvocationContext` | `context` parameter in `execute()` |
| `agent.create_session()` | `Memory` + `SQLiteStorage` |
| `AgentResult` | `FullOutput` |
| `WorkflowBuilder` | `Workflow` class |
| Harness (opinionated agent) | Optional agent composition |
| Python, C#, Go | TypeScript-only |

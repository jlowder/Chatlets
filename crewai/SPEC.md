# Chatlets — CrewAI Backend

> **Note:** This is a **backend-only** implementation. The shared frontend (in `shared/`) provides the chat UI for all Chatlets. See [vercel-ai/SPEC.md](../vercel-ai/SPEC.md) for the full architecture.

---

## Project Overview

A minimal chat backend that connects to an OpenAI-compatible LLM with bash execution capabilities using CrewAI's multi-agent orchestration. A single `BashAgent` is defined with a role, goal, and backstory, equipped with a `bash` tool and governed by an allow list. The agent is assembled into a `Crew` and tasked to execute user requests.

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
│  next.config.mjs (CHATLET_BACKEND=crewai)                   │
│  rewrites → crewai backend on :5000                        │
└─────────────────────────────────────────────────────────────┘
                        │
                        │ HTTP POST /api/chat { messages }
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              crewai backend (port 5000)                    │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐   │
│  │ CrewAI Crew     │───▶│ bash Tool                   │   │
│  │ .kickoff()      │    │  - zod input schema          │   │
│  │                 │    │  - execAsync(cmd, timeout)   │   │
│  │  ┌────────────┐ │    │  - 30s timeout              │   │
│  │  │  messages  │ │    │  - returns stdout/stderr     │   │
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
         │ max_tokens: 4096 (context window)                     │
         │ max_iter: 5 (max tool-call cycles)                    │
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

### Implementation (crewai)

The backend reads the messages array and builds a context string that is prepended to the task description:

```typescript
// Backend receives { messages: [{role, content}, ...] }
const messages = req.body.messages;
const context = messages
  .slice(0, -1)
  .map(m => `${m.role}: ${m.content}`)
  .join("\n");
const task = new Task({
  description: context ? `${context}\n\nUser request: ${lastMessage.content}` : lastMessage.content,
  // ...
});
```

---

## Technical Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Agent Framework** | CrewAI | 2.x |
| **Validation** | Zod | 3.25.0 |
| **Type Safety** | TypeScript | 5.x |

---

## Key Components

### `app/api/chat/route.ts` (or `agent_service.py` equivalent)

**Type**: API Route (POST)  
**Purpose**: Orchestrate LLM inference via a CrewAI agent crew

```ts
Key imports:
  - { Agent } from "crewai"
  - { Task } from "crewai"
  - { Crew } from "crewai"
  - { z } from "zod"

Key exports:
  - POST(req: NextRequest)

Configuration:
  - model: OpenAI-compatible via CrewAI's llm config
  - tools: [bashTool]
  - agent: BashAgent with role, goal, backstory
  - task: ExecuteTask describing the user prompt
  - crew: Crew orchestrating agent + task
  - maxIter: 5 (via process config)
```

### Bash Tool

**Type**: CrewAI Tool (`extends Tool`)  
**Purpose**: Safely execute shell commands with allow-list enforcement

```ts
class BashTool extends Tool {
  name = "bash";
  description = `Execute a bash command on the server. You MUST provide a "command"
  parameter with the exact shell command to run. This is the ONLY way to run
  commands. For example: command="pwd", command="ls -la", command="npm run build".`;

  schema = z.object({
    command: z.string().describe('The bash/shell command to execute'),
  });

  async _run(input: z.infer<typeof this.schema>): Promise<string> {
    const { command } = input;
    // ... execute and return result
  }
}
```

---

## LLM Configuration

```ts
const llm = {
  modelName: 'modelName',
  baseUrl: 'baseUrl',
  apiKey: 'example',
  maxTokens: 4096,
};
```

| Setting | Value |
|---------|-------|
| **Model** | `modelName` |
| **Base URL** | `baseUrl` |
| **API Key** | `example` |
| **Provider Type** | OpenAI-compatible (via CrewAI's native config) |
| **Max Tokens** | `4096` (context window limit) |

Configuration data is persisted to a file called `llm-config.json`.

---

## Bash Tool Design

### Schema Definition

```ts
import { z } from "zod";
import { Tool } from "crewai/tools";

class BashTool extends Tool {
  name = "bash";
  description = `Execute a bash command on the server. You MUST provide a "command"
  parameter with the exact shell command to run. This is the ONLY way to run
  commands. For example: command="pwd", command="ls -la", command="npm run build".`;

  schema = z.object({
    command: z.string().describe('The bash/shell command to execute'),
  });

  async _run(input: z.infer<typeof this.schema>): Promise<string> {
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

CrewAI tools return a **string** that gets returned to the agent as a result. The string representation:

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

## Design Patterns

### 1. Backend-Only API

- **API Route** (`api/chat/route.ts`): Holds API key, makes LLM calls
- **Benefit**: API key never exposed to browser
- The shared frontend communicates via a standardized `POST /api/chat` contract

### 2. CrewAI Agent Pattern

```ts
// Step 1: Define the agent with role, goal, and backstory
const bashAgent = new Agent({
  role: 'Command Executor',
  goal: 'Execute bash commands accurately and return results to the user',
  backstory: `You are a helpful assistant that can execute bash commands on a server.
  You are given commands to run and you execute them safely using an allow list.
  You always return the command output clearly.`,
  llm: modelConfig,
  tools: [new BashTool()],
  allowDelegation: false,
  maxIter: 5,
});

// Step 2: Define the task that describes the user's request
const executeTask = new Task({
  description: `Execute the following user request: ${prompt}.
  Use the bash tool to run any commands needed and return the complete result.`,
  expectedOutput: 'A clear response containing the command outputs and explanation',
  agent: bashAgent,
});

// Step 3: Assemble the crew
const crew = new Crew({
  agents: [bashAgent],
  tasks: [executeTask],
  process: 'sequential',  // or 'hierarchical'
  verbose: false,
  maxIter: 5,
});

// Step 4: Execute
const result = await crew.kickoff();
// result.raw contains the agent's final output
```

**Key CrewAI concepts used**:
- `Agent` — defines an agent's role, goal, backstory, tools, and LLM config
- `Task` — describes what needs to be done, its expected output, and which agent performs it
- `Crew` — orchestrates agents and tasks using a process (sequential, hierarchical)
- `kickoff()` — executes the crew and returns results
- `process: 'sequential'` — tasks execute in order (suitable for single-agent chat)
- `process: 'hierarchical'` — manager agent delegates to worker agents (overkill for single-agent chat)
- `maxIter` — limits the number of tool call/response cycles per task
- Tool results are automatically passed back to the agent for next iteration

---

## Key Dependencies

```json
{
  "dependencies": {
    "crewai": "^2.x",
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
cd crewai
pip install crewai
npm install
npm run dev    # starts backend on port 5000
```

The shared frontend proxies to this backend via `shared/next.config.mjs` (`CHATLET_BACKEND=crewai`). After implementing, add your port and URL to `shared/config/backends.ts`.

---

## Data Flow Summary

1. **User** types prompt and clicks Send in the shared frontend
2. **Frontend** sends `POST /api/chat` with `{ messages }`
3. **next.config.mjs** rewrites the request to `crewai` backend on `:5000`
4. **API Route** creates a CrewAI `Agent` with role, goal, backstory, and bash tool
5. **API Route** creates a `Task` describing the user's request from the last message
6. **API Route** assembles a `Crew` with the agent and task
7. **Crew** executes via `kickoff()` — the agent processes the full conversation context
8. **Agent** may call bash tool (up to `maxIter: 5` times)
9. **Bash Tool** executes command via `execAsync()` (30s timeout)
   - **Allow List Check** verifies the base command is permitted (or "Allow All" is enabled)
10. **Agent** collects tool results and iterates until final answer
11. **Crew** returns result via `kickoff()`
12. **API Route** returns `{ text, toolOutputs[] }` extracted from the crew result
13. **Frontend** displays response text and tool output cards

---

## Future Considerations

- Multi-agent crews: Add a `ResearcherAgent` and `SummarizerAgent` working in parallel
- Process modes: Switch to `process: 'hierarchical'` for manager/worker delegation
- Add streaming via CrewAI's `stream()` or `asyncKoff()`
- Support multi-turn conversation history via task context
- Add request/response logging
- Configure environment variables for API credentials
- Add loading states for individual agent steps
- Support streaming tool outputs via SSE
- Add team-based allow list defaults via shared agent config
- Add memory/persistence via CrewAI's memory feature

---

## CrewAI vs Vercel AI SDK: Key Mapping

| Vercel AI SDK | CrewAI |
|---------------|--------|
| `generateText()` | `Crew.kickoff()` |
| `tool({ parameters, execute })` | `class extends Tool { schema, _run() }` |
| `maxSteps: 5` | `maxIter: 5` in agent/crew config |
| Tool result as object | Tool result as JSON string |
| Built-in streaming (`useChat`) | `crew.stream()` / `crew.asyncKoff()` |
| Auto message history | Agent retains conversation context |
| Implicit tool routing | Agent internally manages tool calls |
| `ai` package | `crewai` package |
| Single function call | Three-layer abstraction: Agent → Task → Crew |

## CrewAI vs LangChain: Key Mapping

| LangChain (createReactAgent) | CrewAI |
|------------------------------|--------|
| `createReactAgent({ llm, tools })` | `new Agent() → new Task() → new Crew()` |
| `StateGraph` with nodes/edges | Implicit agent loop managed by Crew |
| `maxIterations: 5` | `maxIter: 5` |
| `MemorySaver` / `SqliteSaver` | CrewAI built-in memory |
| `invoke()` | `kickoff()` |
| `stream()` | `stream()` / `asyncKoff()` |
| Explicit message management | Crew handles message context |
| `thread_id` in configurable | Task-level context sharing |
| State machine (explicit) | Agent orchestration (declarative) |

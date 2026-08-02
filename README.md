# Chatlets

A simple chat interface with tool calling, implemented ten times
using a different backend framework each time.  This creates a level
playing field to compare these frameworks side-by-side. 

Plus you can point your coding agent at a backend to use it as a
template, which helps it to generate working code without having to
iterate (as much).

## Architecture

```
Browser → Shared Frontend (:3000) → Backend Service
```

The shared frontend proxies requests to whichever backend you configure via `CHATLET_BACKEND`. One API contract to rule them all (`POST /api/chat` → `{ text, toolOutputs }`), and in the darkness bind them.

Two deployment patterns exist:

- **Monolithic** — Single Next.js process (vercel-ai, langchain, langgraph)
- **Split** — Flask agent service + Next.js proxy (crewai, smolagents, pydantic, maf, mastra, agno, liw)

## Backends

| Framework | Pattern | Port | Notes |
|-----------|---------|------|-------|
| Vercel AI SDK | Monolithic | 4000 | @ai-sdk/openai-compatible |
| Agno | Split | 3001 | Flask agent + proxy |
| CrewAI 2.x | Split | 3002 | LLM class required |
| LangChain | Monolithic | 5001 | createReactAgent |
| LangGraph | Monolithic | 5002 | StateGraph with routing |
| LlamaIndex Workflows | Split | 5003 | Event-driven agent |
| Microsoft Agent Framework | Split | 5005 | @tool decorator |
| Mastra | Monolithic | 5007 | Direct fetch + AI SDK |
| Pydantic AI | Split | 5009 | @agent.tool decorator |
| Smolagents | Split | 5011 | CodeAgent / ToolCallingAgent |

## Getting Started

1. Install dependencies: `npm install` (root), then `cd shared && npm install` and `cd <backend> && npm install`

2. Set up config: `cp example.config.json config.json` in each backend folder. Fill in your model endpoint, API key, and model name.

3. Start the backend. Monolithic backends: `cd <backend> && npm run dev`. Split backends: `cd <backend> && npm run dev:all` (starts Flask + proxy).

4. Start the shared frontend: `cd shared && npm run dev`.

5. Switch backends by setting `CHATLET_BACKEND=<name>` in the shared frontend's environment.

## API Contract

All backends implement:

```
POST /api/chat
Body: { messages: [{ role: "user" | "assistant", content: string }] }
Response: { text: string, toolOutputs: [{ stdout?: string, stderr?: string, error?: string }] }
```

The frontend sends the full message history on every request. The backend returns either a text response or structured tool output.

## Bash Tool

Every backend includes a sandboxed bash tool. Commands are restricted to an allowlist defined in `config.json`:

```json
{
  "bash": {
    "allowList": ["ls", "pwd"],
    "allowAll": false
  }
}
```

Feeling reckless? Go ahead and set `allowAll: true` to permit any command. Just remember that these agents... they are subtle and quick to anger.

## File Layout

```
shared/           Shared Next.js frontend + proxy
  app/            API routes (proxy)
  components/     ChatPage, ToolCard, TypingIndicator
  config/         Backend registry (backends.ts)
  types/          Shared TypeScript types
<backend>/        Each backend implementation
  app/api/chat/   Backend API route
  agent_service.py  Flask agent service (split backends)
  config.json     Model + tool settings
  example.config.json  Template with placeholder values
  venv/            Python virtual environment
  scripts/         Venv auto-detection scripts
```

## Compare

Run two or more backends simultaneously on different ports. Switch the frontend to each one and compare:

- Tool execution reliability
- Response latency
- Memory handling
- Error recovery
- Prompt adherence

# Chatlets

Side-by-side chat interface implementations across many AI frameworks, with a **shared frontend** and **backend-only framework folders**.

## Architecture

```
                    ┌────────────────────┐
                    │   Shared Frontend   │
                    │  (Next.js, :3000)   │
                    │                     │
                    │  /api/chat          │
                    └──┬────┬────┬────┬───┘
                       │    │    │    │
              CHATLET  │    │    │    │  env var
              BACKEND  ▼    ▼    ▼    ▼
                  vercel-ai  agno  ...  ...
                  (:4000)   (:3001)  etc
```

Each framework backend runs independently. The shared frontend proxies to whichever backend is selected via the `CHATLET_BACKEND` environment variable.

## Getting Started

```bash
# Install shared frontend deps
cd shared && bun install

# Start the frontend, pointing at a backend
CHATLET_BACKEND=vercel-ai bun dev

# Or switch backends
CHATLET_BACKEND=agno bun dev
```

Each backend may need its own setup. See individual backend SPEC.md files.

## Available Frameworks

| Framework    | Status | Backend Port | How to Run          |
|-------------|--------|-------------|---------------------|
| Vercel AI   | ✅ Done | 4000       | `bun dev` in vercel-ai/ |
| Agno        | ✅ Done | 3001        | `npm run dev:all` in agno/ |
| CrewAI      | ⬜      | —           |                     |
| LangChain   | ⬜      | —           |                     |
| LangGraph   | ⬜      | —           |                     |
| LIW         | ⬜      | —           |                     |
| MAF         | ⬜      | —           |                     |
| Mastra      | ⬜      | —           |                     |
| Pydantic    | ⬜      | —           |                     |
| SmolAgents  | ⬜      | —           |                     |

## Adding a New Framework

1. Create a folder with the same name as the framework
2. Implement a backend that exposes a chat endpoint (see other SPEC.md files for patterns)
3. Return `{ text: string, toolOutputs: ToolOutput[] }` from the endpoint
4. Add an entry to `shared/config/backends.ts`
5. Update `shared/next.config.mjs` with the proxy destination
6. Add the framework to this README table

## Shared Frontend

Located in `shared/`. All frameworks share this single UI. Key components:

- `components/ChatPage.tsx` — main chat interface
- `components/ToolCard.tsx` — renders tool call outputs
- `components/TypingIndicator.tsx` — loading dots animation
- `types/chat.ts` — TypeScript type definitions
- `config/backends.ts` — backend registry
- `next.config.mjs` — dev proxy rewrites

## API Contract

All backends must implement:

```
POST /chat  (or /api/chat for Next.js backends)
  Request:  { "prompt": "string" }
  Response: { "text": "string", "toolOutputs": [{ "stdout": "...", "stderr": "...", "error": "..." }] }
```

## config.json

Each backend reads its own `config.json` for LLM settings:

```json
{
  "provider": "YOUR_PROVIDER",
  "baseURL": "http://localhost:8080/v1",
  "apiKey": "your-api-key",
  "model": "model-name",
  "allowList": ["ls", "pwd"],
  "allowAll": false
}
```

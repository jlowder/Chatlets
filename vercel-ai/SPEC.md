# Chatlets — Vercel AI Backend

## Overview

This is a **backend-only** Next.js app that exposes a chat API for the Chatlets shared frontend. It uses the Vercel AI SDK with `@ai-sdk/openai-compatible` to connect to any OpenAI-compatible LLM, with built-in bash tool calling for shell command execution.

The shared frontend proxies requests to this backend and renders all UI.

---

## Running

```bash
cd vercel-ai
bun install   # first time only
bun dev       # starts on port 4000
```

The shared frontend proxies `/api/chat` to `http://localhost:4000/api/chat` (configured in `shared/next.config.mjs`).

---

## API Contract

### `POST /api/chat`

**Request body:**
```json
{ "prompt": "string" }
```

**Response (200):**
```json
{
  "text": "string",
  "toolOutputs": [{ "stdout": "...", "stderr": "...", "error": "..." }]
}
```

**Response (400):**
```json
{ "error": "Missing prompt" }
```

**Response (500):**
```json
{ "error": "string" }
```

---

## Architecture

```
┌──────────────────────┐         ┌──────────────────────────┐
│   Shared Frontend    │         │  vercel-ai Backend       │
│  (Next.js, :3000)    │         │  (Next.js, :4000)        │
│                      │  rewrite│                          │
│  /api/chat ──────▶ /api/chat  │  app/api/chat/route.ts   │
└──────────────────────┘         │                          │
                                 │  ┌────────────────────┐  │
                                 │  │ generateText()     │  │
                                 │  │  - Vercel AI SDK   │  │
                                 │  │  - maxSteps: 5     │  │
                                 │  │  - bash tool       │  │
                                 │  └─────────┬──────────┘  │
                                 │            │              │
                                 │            ▼              │
                                 │  ┌──────────────────┐    │
                                 │  │ OpenAI-Compat    │    │
                                 │  │ (config.json)    │    │
                                 │  └──────────────────┘    │
                                 └──────────────────────────┘
```

---

## LLM Configuration

Read from `config.json` in the project root on each request:

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

| Field | Description |
|-------|-------------|
| `provider` | Provider name for the SDK |
| `baseURL` | OpenAI-compatible API base URL |
| `apiKey` | API key for authentication |
| `model` | Model name to use |
| `allowList` | Allowed base commands for bash tool |
| `allowAll` | If true, skip allow list entirely |

---

## Bash Tool

The backend exposes a `bash` tool via Vercel AI SDK's `generateText()`. The LLM can invoke it up to 5 times per turn (`maxSteps: 5`).

### Execution

- Uses `lib/execAsync.ts` — promisified `child_process.exec` with **30s timeout**
- Checks command against allow list in `config.json` before executing
- Returns `{ stdout, stderr }` on success, or `{ error, stdout?, stderr? }` on failure

### Return Format

```ts
// Success
{ stdout: string; stderr: string }

// Error
{ error: string; stdout?: string; stderr?: string }
```

### Allow List

| Mode | Behavior |
|------|----------|
| `allowAll: true` | All commands execute without restriction |
| `allowAll: false` | Only commands whose base (first word) is in `allowList` execute |

Default allow list: `["ls", "pwd"]` — editable in `config.json`.

---

## Code Structure

```
vercel-ai/
├── app/api/chat/route.ts    # POST endpoint — LLM orchestration
├── config.json              # LLM config + allow list
├── lib/execAsync.ts         # Shell command execution (30s timeout)
├── package.json
├── tsconfig.json
└── SPEC.md
```

### `app/api/chat/route.ts`

**Entry point** — handles all HTTP requests.

```ts
POST(request):
  1. Parse { prompt } from body
  2. Load config.json
  3. Create OpenAI-compatible provider
  4. Call generateText({ model, prompt, tools: { bash }, maxSteps: 5 })
  5. Extract text + toolOutputs from response steps
  6. Return { text, toolOutputs }
```

### `lib/execAsync.ts`

Shell command executor:
- Wraps `child_process.exec` with `promisify`
- 30,000ms timeout
- Returns `{ stdout: string, stderr: string }` (trimmed)

---

## Integration with Shared Frontend

The shared frontend (in `shared/`) serves as the single UI for all Chatlets backends. It proxies `/api/chat` to whichever backend is active via `next.config.mjs` rewrites, controlled by the `CHATLET_BACKEND` environment variable:

| Env var | Proxy target |
|---------|-------------|
| `CHATLET_BACKEND=vercel-ai` | `http://localhost:4000` |
| `CHATLET_BACKEND=agno` | `http://localhost:8081` |

Default: `vercel-ai`.

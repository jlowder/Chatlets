export interface BackendDefinition {
  name: string;
  label: string;
  url: string;
  port: number;
  description: string;
}

export const BACKENDS: BackendDefinition[] = [
  { name: 'vercel-ai', label: 'Vercel AI SDK', url: 'http://localhost:4000', port: 4000, description: 'Vercel AI SDK with @ai-sdk/openai-compatible' },
  { name: 'agno', label: 'Agno', url: 'http://localhost:3001', port: 3001, description: 'Agno Python agent with Flask service + Next.js proxy' },
  { name: 'crewai', label: 'CrewAI', url: 'http://localhost:3002', port: 3002, description: 'CrewAI Python agent with Flask service + Next.js proxy' },
];

export function getBackendUrl(): string | null {
  const backend = process.env.CHATLET_BACKEND;
  const found = BACKENDS.find(b => b.name === backend);
  return found ? found.url : null;
}

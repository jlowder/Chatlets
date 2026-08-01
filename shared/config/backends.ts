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
  { name: 'langchain', label: 'LangChain', url: 'http://localhost:5001', port: 5001, description: 'LangChain + LangGraph createReactAgent with checkpointing' },
  { name: 'langgraph', label: 'LangGraph', url: 'http://localhost:5002', port: 5002, description: 'LangGraph StateGraph with explicit model/tools nodes and conditional routing' },
  { name: 'liw', label: 'LlamaIndex Workflows', url: 'http://localhost:5003', port: 5003, description: 'LlamaIndex Workflows event-driven agent with Flask service + Next.js proxy' },
  { name: 'maf', label: 'Microsoft Agent Framework', url: 'http://localhost:5005', port: 5005, description: 'Microsoft Agent Framework with @tool decorator and session management' },
  { name: 'mastra', label: 'Mastra', url: 'http://localhost:5007', port: 5007, description: 'Mastra AI framework with Agent, Model Router, and createTool' },
];

export function getBackendUrl(): string | null {
  const backend = process.env.CHATLET_BACKEND;
  const found = BACKENDS.find(b => b.name === backend);
  return found ? found.url : null;
}

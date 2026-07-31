export interface ToolOutput {
  stdout?: string;
  stderr?: string;
  error?: string;
}

export interface ChatResponse {
  text?: string;
  toolOutputs?: ToolOutput[];
  error?: string;
}

export interface ChatRequest {
  prompt: string;
}

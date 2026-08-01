import { NextResponse } from 'next/server';
import { ChatOpenAI } from '@langchain/openai';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { MemorySaver } from '@langchain/langgraph';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { Tool } from '@langchain/core/tools';
import { z } from 'zod';
import { exec } from 'child_process';
import { readFile } from 'fs/promises';
import { join } from 'path';

const execAsync = (command: string, timeout = 30000): Promise<{ stdout: string; stderr: string }> => {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error('Command timed out'));
    }, timeout);
    exec(command, { timeout }, (error, stdout, stderr) => {
      clearTimeout(timer);
      if (error) {
        reject(error);
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
};

interface LLMConfig {
  baseURL: string;
  apiKey: string;
  model: string;
  allowList?: string[];
  allowAll?: boolean;
}

async function loadConfig(): Promise<LLMConfig> {
  const configPath = join(process.cwd(), 'config.json');
  const raw = await readFile(configPath, 'utf-8');
  return JSON.parse(raw);
}

class BashTool extends Tool {
  name = 'bash';
  description = 'Execute a shell command. Only use for explicit command requests (e.g., "run ls"), NOT for general knowledge, math, definitions, or factual queries.';
  schema = z.object({ command: z.string().describe('The shell command to execute') });

  async _call(input: { command: string }): Promise<string> {
    const cfg = await loadConfig();
    const cmd = input.command.trim();
    const cmdName = cmd.split(/\s+/)[0];

    if (!cfg.allowAll && cfg.allowList && !cfg.allowList.includes(cmdName)) {
      return JSON.stringify({ error: `Command '${cmdName}' not allowed` });
    }

    try {
      const { stdout, stderr } = await execAsync(cmd);
      if (stderr) return JSON.stringify({ stdout: stdout.trim(), stderr: stderr.trim() });
      return JSON.stringify({ stdout: stdout.trim() });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      return JSON.stringify({ error: msg });
    }
  }
}

export async function POST(request: Request) {
  try {
    const cfg = await loadConfig();
    const body = await request.json();

    // Support both new messages format and legacy prompt format
    const messages = body.messages || [{ role: 'user' as const, content: body.prompt }];
    const prompt = messages[messages.length - 1]?.content;
    const historyMessages = messages.slice(0, -1);

    // Create model
    const model = new ChatOpenAI({
      model: cfg.model,
      apiKey: cfg.apiKey,
      configuration: {
        baseURL: cfg.baseURL,
      },
      maxRetries: 0,
    });

    // Create agent with memory
    const bashTool = new BashTool();
    const memory = new MemorySaver();
    const agent = createReactAgent({
      llm: model,
      tools: [bashTool],
      checkpointSaver: memory,
      messagesModifier: new SystemMessage(
        `You are a helpful assistant. Answer questions directly from your knowledge whenever possible. Only use the bash tool when the user explicitly requests a shell command (e.g., "run ls", "execute the script", "check disk space"). Do NOT use bash for: general knowledge questions, math, definitions, explanations, or factual queries. The user does not want command-line access unless they specifically ask for it.`,
      ),
    });

    // Convert messages to LangChain message types
    const langchainMessages: (HumanMessage | AIMessage)[] = [];
    for (const m of historyMessages) {
      if (m.role === 'user') {
        langchainMessages.push(new HumanMessage(m.content));
      } else if (m.role === 'assistant') {
        langchainMessages.push(new AIMessage(m.content));
      }
    }

    // Generate a unique thread_id per request so MemorySaver doesn't accumulate outputs
    const threadId = crypto.randomUUID();

    // Invoke agent with history
    const result = await agent.invoke({
      messages: [...langchainMessages, new HumanMessage(prompt)],
    }, {
      configurable: { thread_id: threadId },
    });

    // Extract final text from last AI message
    const outputMessages = result.messages;
    const lastMsg = outputMessages[outputMessages.length - 1];
    const text = typeof lastMsg.content === 'string' ? lastMsg.content : JSON.stringify(lastMsg.content);

    // Build tool outputs from ToolMessage entries in this invocation only
    // (unique thread_id prevents accumulation from prior requests)
    const toolOutputs: Array<{ stdout?: string; stderr?: string; error?: string }> = [];
    for (const m of outputMessages) {
      if (m instanceof ToolMessage) {
        const parsed = typeof m.content === 'string' ? JSON.parse(m.content) : m.content;
        toolOutputs.push({
          stdout: parsed.stdout,
          stderr: parsed.stderr,
          error: parsed.error,
        });
      }
    }

    // Suppress text output when tool outputs were used
    // (the tool results are shown separately, so the text would be redundant)
    if (toolOutputs.length > 0) {
      return NextResponse.json({ text: "", toolOutputs });
    }

    return NextResponse.json({ text, toolOutputs });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('LangChain backend error:', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

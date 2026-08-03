import { NextResponse } from 'next/server';
import { ChatOpenAI } from '@langchain/openai';
import { MessagesAnnotation, StateGraph } from '@langchain/langgraph';
import { ToolMessage } from '@langchain/core/messages';
import { StructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { exec } from 'child_process';
import { readFile } from 'fs/promises';
import { join } from 'path';
import { HumanMessage, AIMessage } from '@langchain/core/messages';
import { MemorySaver } from '@langchain/langgraph';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../../shared/config-loader';

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

class BashTool extends StructuredTool {
  name = 'bash';
  description = 'Execute a shell command. Only use for explicit command requests, NOT for general knowledge, math, definitions, or factual queries.';
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

const bashTool = new BashTool();

async function modelNode(state: typeof MessagesAnnotation.State) {
  const cfg = await loadConfig();
  const model = new ChatOpenAI({
    model: cfg.model,
    apiKey: cfg.apiKey,
    configuration: {
      baseURL: cfg.baseURL,
    },
    maxRetries: 0,
  }).bindTools([bashTool]);

  const config = loadChatletsConfig();
  const bashPrompt = getBashCommandsPrompt(config);
  const systemMessage = new HumanMessage(
    `You are a helpful assistant. ${bashPrompt} Answer questions directly from your knowledge whenever possible. Only use the bash tool when the user explicitly requests a shell command. Do NOT use bash for general knowledge questions, math, definitions, explanations, or factual queries.`
  );

  const response = await model.invoke([systemMessage, ...state.messages]);
  return { messages: [response] };
}

async function toolsNode(state: typeof MessagesAnnotation.State) {
  const lastMessage = state.messages[state.messages.length - 1] as AIMessage;
  const toolMessages: ToolMessage[] = [];

  if (lastMessage.tool_calls) {
    for (const toolCall of lastMessage.tool_calls) {
      const result = await bashTool.invoke(toolCall.args);
      toolMessages.push(
        new ToolMessage({
          content: result,
          name: toolCall.name,
          tool_call_id: toolCall.id ?? '',
        })
      );
    }
  }

  return { messages: toolMessages };
}

function routeResponse(state: typeof MessagesAnnotation.State): 'tools' | '__end__' {
  const lastMessage = state.messages[state.messages.length - 1] as AIMessage;
  if (lastMessage.tool_calls && lastMessage.tool_calls.length > 0) {
    return 'tools';
  }
  return '__end__';
}

// Build and compile the graph
const graph = new StateGraph(MessagesAnnotation)
  .addNode('model', modelNode)
  .addNode('tools', toolsNode)
  .addEdge('__start__', 'model')
  .addConditionalEdges('model', routeResponse, {
    tools: 'tools',
    __end__: '__end__',
  })
  .addEdge('tools', 'model')
  .compile({
    checkpointer: new MemorySaver(),
  });

let currentThreadId = crypto.randomUUID();

export async function POST(request: Request) {
  try {
    const cfg = await loadConfig();
    const body = await request.json();

    // Support both new messages format and legacy prompt format
    const messages = body.messages || [{ role: 'user' as const, content: body.prompt }];
    const prompt = messages[messages.length - 1]?.content;
    const historyMessages = messages.slice(0, -1);

    // If history is empty, treat as a brand new conversation
    if (historyMessages.length === 0) {
      currentThreadId = crypto.randomUUID();
    }

    // Convert messages to LangChain message types
    const langchainMessages: (HumanMessage | AIMessage)[] = [];
    for (const m of historyMessages) {
      if (m.role === 'user') {
        langchainMessages.push(new HumanMessage(m.content));
      } else if (m.role === 'assistant') {
        langchainMessages.push(new AIMessage(m.content));
      }
    }

    const threadConfig = { configurable: { thread_id: currentThreadId } };

    // Check if the current thread checkpointer is empty but we have incoming history
    const state = await graph.getState(threadConfig);
    const hasState = state.values && state.values.messages && state.values.messages.length > 0;

    if (!hasState && langchainMessages.length > 0) {
      await graph.updateState(threadConfig, {
        messages: langchainMessages,
      });
    }

    // Get the message count before invoking
    const stateBefore = await graph.getState(threadConfig);
    const beforeMsgCount = stateBefore.values?.messages?.length ?? 0;

    // Invoke graph with only the latest user prompt to leverage native session memory
    const result = await graph.invoke({
      messages: [new HumanMessage(prompt)],
    }, threadConfig);

    // Extract new messages generated in this invocation
    const outputMessages = result.messages;
    const newMessages = outputMessages.slice(beforeMsgCount);

    // Extract final text from last AI message of the current run
    const lastMsg = newMessages[newMessages.length - 1] || outputMessages[outputMessages.length - 1];
    const text = typeof lastMsg.content === 'string' ? lastMsg.content : JSON.stringify(lastMsg.content);

    // Build tool outputs from ToolMessage entries in this invocation only
    const toolOutputs: Array<{ stdout?: string; stderr?: string; error?: string }> = [];
    for (const m of newMessages) {
      if (m instanceof ToolMessage) {
        const parsed = typeof m.content === 'string' ? JSON.parse(m.content) : m.content;
        toolOutputs.push({
          stdout: parsed.stdout,
          stderr: parsed.stderr,
          error: parsed.error,
        });
      }
    }

    // Suppress text when tools were used
    if (toolOutputs.length > 0) {
      return NextResponse.json({ text: '', toolOutputs });
    }

    return NextResponse.json({ text, toolOutputs });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('LangGraph backend error:', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

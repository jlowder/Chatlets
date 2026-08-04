import { NextResponse } from 'next/server';
import { ChatOpenAI } from '@langchain/openai';
import { MessagesAnnotation, StateGraph } from '@langchain/langgraph';
import { ToolMessage } from '@langchain/core/messages';
import { StructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { execFile } from 'child_process';
import { createHash } from 'crypto';
import { HumanMessage, AIMessage } from '@langchain/core/messages';
import { MemorySaver } from '@langchain/langgraph';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../../shared/config-loader';

function tokenize(command: string): string[] {
  const args: string[] = [];
  let current = "";
  let inDoubleQuotes = false;
  let inSingleQuotes = false;
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    if (char === '"' && !inSingleQuotes) {
      inDoubleQuotes = !inDoubleQuotes;
    } else if (char === "'" && !inDoubleQuotes) {
      inSingleQuotes = !inSingleQuotes;
    } else if (char === " " && !inDoubleQuotes && !inSingleQuotes) {
      if (current) {
        args.push(current);
        current = "";
      }
    } else {
      current += char;
    }
  }
  if (current) {
    args.push(current);
  }
  return args;
}

const execAsync = (command: string, timeout = 30000): Promise<{ stdout: string; stderr: string }> => {
  return new Promise((resolve, reject) => {
    const cmd = command.trim();
    if (!cmd) {
      return reject(new Error('Empty command'));
    }

    const args = tokenize(cmd);
    if (args.length === 0) {
      return reject(new Error('Empty command'));
    }

    const cmdName = args[0];

    execFile(cmdName, args.slice(1), { timeout }, (error, stdout, stderr) => {
      if (error) {
        const errWithOutputs = Object.assign(error, { stdout, stderr });
        if ((error as any).killed && (error as any).signal === 'SIGTERM') {
          errWithOutputs.message = 'Command timed out';
        }
        return reject(errWithOutputs);
      }
      resolve({ stdout, stderr });
    });
  });
};

class BashTool extends StructuredTool {
  name = 'bash';
  description = 'Execute a shell command. Only use for explicit command requests, NOT for general knowledge, math, definitions, or factual queries.';
  schema = z.object({ command: z.string().describe('The shell command to execute') });

  async _call(input: { command: string }): Promise<string> {
    const cfg = loadChatletsConfig();
    const cmd = input.command.trim();

    const args = tokenize(cmd);
    const cmdName = args[0] ?? '';

    if (!cfg.allowAll && cfg.allowList && !cfg.allowList.includes(cmdName)) {
      return JSON.stringify({ error: `Command '${cmdName}' not allowed` });
    }

    try {
      const { stdout, stderr } = await execAsync(cmd);
      const out: Record<string, string> = { stdout: stdout.trim() };
      if (stderr.trim()) {
        out.stderr = stderr.trim();
      }
      return JSON.stringify(out);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      const stdout = (err as any).stdout ?? '';
      const stderr = (err as any).stderr ?? '';
      return JSON.stringify({
        error: msg,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      });
    }
  }
}

const bashTool = new BashTool();

async function modelNode(state: typeof MessagesAnnotation.State) {
  const cfg = loadChatletsConfig();
  const model = new ChatOpenAI({
    model: cfg.model,
    apiKey: cfg.apiKey,
    configuration: {
      baseURL: cfg.baseURL,
    },
    maxRetries: 0,
  }).bindTools([bashTool]);

  const bashPrompt = getBashCommandsPrompt(cfg);
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

function getThreadId(messages: any[]): string {
  if (!messages || messages.length === 0) {
    return crypto.randomUUID();
  }
  const firstMessageContent = messages[0]?.content || '';
  return createHash('sha256').update(firstMessageContent).digest('hex');
}

export async function POST(request: Request) {
  try {
    const cfg = loadChatletsConfig();
    const body = await request.json();

    // Support both new messages format and legacy prompt format
    const messages = body.messages || [{ role: 'user' as const, content: body.prompt }];
    const prompt = messages[messages.length - 1]?.content;
    const historyMessages = messages.slice(0, -1);

    // Convert messages to LangChain message types
    const langchainMessages: (HumanMessage | AIMessage)[] = [];
    for (const m of historyMessages) {
      if (m.role === 'user') {
        langchainMessages.push(new HumanMessage(m.content));
      } else if (m.role === 'assistant') {
        langchainMessages.push(new AIMessage(m.content));
      }
    }

    const threadId = getThreadId(messages);
    const threadConfig = { configurable: { thread_id: threadId } };

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

import { NextResponse } from 'next/server';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { execFile } from 'node:child_process';
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

const bashTool = createTool({
  id: 'bash',
  description: 'Execute a shell command. Only use for explicit command requests (e.g., "run ls"), NOT for general knowledge, math, definitions, or factual queries.',
  inputSchema: z.object({
    command: z.string().describe('The bash/shell command to execute'),
  }),
  execute: async ({ command }) => {
    console.log('=== bashTool execute called ===');
    console.log('command:', command);
    const cfg = loadChatletsConfig();
    const cmd = command.trim();

    const args = tokenize(cmd);
    const cmdName = args[0] ?? '';

    const allowAll = cfg.allowAll ?? false;
    const allowList = cfg.allowList ?? ['ls', 'pwd'];

    if (!allowAll && !allowList.includes(cmdName)) {
      console.log('Command not allowed:', cmdName);
      return {
        stdout: '',
        stderr: '',
        error: `Command '${cmdName}' not allowed`,
      };
    }

    try {
      const { stdout, stderr } = await execAsync(cmd, 30000);
      console.log('execAsync success:', { stdout, stderr });
      return {
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      };
    } catch (err: any) {
      console.log('execAsync error:', err);
      if (err.message && err.message.includes('timeout')) {
        return {
          stdout: '',
          stderr: '',
          error: 'Command timed out',
        };
      }
      return {
        error: err.message ?? 'Execution failed',
        stdout: (err.stdout ?? '').trim(),
        stderr: (err.stderr ?? '').trim(),
      };
    }
  },
});

export async function POST(request: Request) {
  try {
    const data = await request.json();
    const messages = data.messages || [];
    const prompt = messages.length > 0
      ? messages[messages.length - 1].content
      : (data.prompt || '');

    if (!prompt) {
      return NextResponse.json({ error: 'No input provided' }, { status: 400 });
    }

    const cfg = loadChatletsConfig();
    const openai = createOpenAI({
      apiKey: cfg.apiKey,
      baseURL: cfg.baseURL,
    });

    const bashPrompt = getBashCommandsPrompt(cfg);
    const instructions = `You are a helpful assistant. ${bashPrompt} Answer questions directly from your knowledge whenever possible. Only use the bash tool when the user explicitly requests a shell command. Do NOT use bash for: general knowledge questions, math, definitions, explanations, or factual queries.`;

    const agent = new Agent({
      id: 'chat-agent',
      name: 'Chat Agent',
      instructions,
      model: openai(cfg.model),
      tools: {
        bash: bashTool,
      },
    });

    const formattedMessages = messages.map((m: any) => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content,
    }));

    if (formattedMessages.length === 0 && data.prompt) {
      formattedMessages.push({ role: 'user', content: data.prompt });
    }

    const result = await agent.generate(formattedMessages, { maxSteps: 5 });

    console.log('=== Raw Agent.generate Result ===');
    console.log(JSON.stringify(result, null, 2));

    // Extract text response
    const text = result.text || '';

    // Collect tool results from all possible paths in result to ensure absolute robustness
    const rawToolResults: any[] = [];
    const seenToolCallIds = new Set<string>();

    const addRaw = (tr: any) => {
      if (!tr) return;
      const id = tr.toolCallId || tr.id || tr.toolCall?.id;
      if (id && !seenToolCallIds.has(id)) {
        seenToolCallIds.add(id);
        rawToolResults.push(tr);
      }
    };

    // 1. result.toolResults
    for (const tr of result.toolResults || []) {
      addRaw(tr);
    }

    // 2. result.toolInvocations
    for (const tr of (result as any).toolInvocations || []) {
      addRaw(tr);
    }

    // 3. result.steps (toolResults and toolInvocations)
    for (const step of result.steps || []) {
      for (const tr of (step as any).toolResults || []) {
        addRaw(tr);
      }
      for (const tr of (step as any).toolInvocations || []) {
        addRaw(tr);
      }
    }

    // 4. result.messages (toolInvocations and content.toolInvocations)
    for (const msg of (result as any).messages || []) {
      for (const tr of msg.toolInvocations || []) {
        addRaw(tr);
      }
      if (msg.content && typeof msg.content === 'object') {
        for (const tr of msg.content.toolInvocations || []) {
          addRaw(tr);
        }
      }
    }

    // 5. result.content (toolInvocations)
    if ((result as any).content && typeof (result as any).content === 'object') {
      for (const tr of (result as any).content.toolInvocations || []) {
        addRaw(tr);
      }
    }

    // Extract tool outputs and map them to standard format robustly
    const toolOutputs: any[] = rawToolResults.map((tr: any) => {
      console.log('=== Mapping tr ===', JSON.stringify(tr, null, 2));

      // 1. Resolve output container: tr.payload.result or tr.result or tr.output or tr itself
      let rawOutput = tr.payload?.result !== undefined
        ? tr.payload.result
        : (tr.result !== undefined ? tr.result : (tr.output !== undefined ? tr.output : tr));

      // 2. If it is a string, try parsing it as JSON first (e.g. if stringified by the runner)
      if (typeof rawOutput === 'string') {
        try {
          rawOutput = JSON.parse(rawOutput);
        } catch {
          // If not valid JSON, treat the plain string as stdout
          return {
            stdout: rawOutput.trim(),
            stderr: '',
            error: tr.isError || tr.payload?.isError ? (tr.error?.message || tr.payload?.error?.message || 'Execution failed') : undefined,
          };
        }
      }

      // 3. Resolve from object fields
      const stdout = rawOutput.stdout !== undefined ? rawOutput.stdout : (rawOutput.result?.stdout !== undefined ? rawOutput.result.stdout : '');
      const stderr = rawOutput.stderr !== undefined ? rawOutput.stderr : (rawOutput.result?.stderr !== undefined ? rawOutput.result.stderr : '');
      const error = rawOutput.error !== undefined ? rawOutput.error : (rawOutput.result?.error !== undefined ? rawOutput.result.error : undefined);

      return {
        stdout: typeof stdout === 'string' ? stdout.trim() : (stdout !== null && stdout !== undefined ? String(stdout) : ''),
        stderr: typeof stderr === 'string' ? stderr.trim() : (stderr !== null && stderr !== undefined ? String(stderr) : ''),
        error: error || (tr.isError || tr.payload?.isError ? (tr.error?.message || tr.payload?.error?.message || 'Execution failed') : undefined),
      };
    });

    // 4. Double-insurance fallback: If toolOutputs is still empty, try extracting from steps content
    if (toolOutputs.length === 0 && result.steps) {
      for (const step of result.steps) {
        for (const item of step.content ?? []) {
          if (item.type === 'tool-result') {
            let output = item.output;
            if (typeof output === 'string') {
              try { output = JSON.parse(output); } catch {}
            }
            if (output && (output.stdout !== undefined || output.stderr !== undefined || output.error !== undefined)) {
              toolOutputs.push({
                stdout: output.stdout ?? '',
                stderr: output.stderr ?? '',
                error: output.error ?? undefined,
              });
            }
          }
        }
      }
    }

    console.log('=== Mastra Response ===');
    console.log({ text, toolOutputs });

    const returnText = toolOutputs.length > 0 ? '' : text;

    return NextResponse.json({ text: returnText, toolOutputs });

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('Mastra backend error:', msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

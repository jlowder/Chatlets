import { NextResponse } from 'next/server';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { promises as fsPromises } from 'node:fs';
import { join } from 'node:path';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../../shared/config-loader';

const execAsync = promisify(exec);
const CONFIG_PATH = join(process.cwd(), 'config.json');

async function loadConfig() {
  const raw = await fsPromises.readFile(CONFIG_PATH, 'utf-8');
  return JSON.parse(raw);
}

const bashTool = createTool({
  id: 'bash',
  description: 'Execute a shell command. Only use for explicit command requests (e.g., "run ls"), NOT for general knowledge, math, definitions, or factual queries.',
  inputSchema: z.object({
    command: z.string().describe('The bash/shell command to execute'),
  }),
  execute: async ({ command }) => {
    const cfg = await loadConfig();
    const cmd = command.trim();
    const cmdName = cmd.split(/\s+/)[0] || '';

    const allowAll = cfg.allowAll ?? false;
    const allowList = cfg.allowList ?? ['ls', 'pwd'];

    if (!allowAll && !allowList.includes(cmdName)) {
      return { error: `Command '${cmdName}' not allowed` };
    }

    try {
      const { stdout, stderr } = await execAsync(cmd, { timeout: 30000 });
      return {
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      };
    } catch (err: any) {
      if (err.message && err.message.includes('timeout')) {
        return { error: 'Command timed out' };
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

    const cfg = await loadConfig();
    const openai = createOpenAI({
      apiKey: cfg.apiKey,
      baseURL: cfg.baseURL,
    });

    const config = loadChatletsConfig();
    const bashPrompt = getBashCommandsPrompt(config);
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

    // Extract text response
    const text = result.text || '';

    // Extract tool outputs and map them to standard format
    const toolOutputs = (result.toolResults || []).map((tr: any) => {
      const output = tr.result || {};
      return {
        stdout: output.stdout ?? '',
        stderr: output.stderr ?? '',
        error: output.error ?? undefined,
      };
    });

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

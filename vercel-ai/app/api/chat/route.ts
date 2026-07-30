import { NextResponse } from 'next/server';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import { generateText, tool } from 'ai';
import { z } from 'zod';
import { promises as fs } from 'fs';
import { execAsync } from '../../../lib/execAsync';

/**
 * Reads the LLM configuration from config.json.
 */
async function loadConfig() {
  const data = await fs.readFile(
    `${process.cwd()}/config.json`,
    'utf-8'
  );
  return JSON.parse(data);
}

/**
 * Bash tool definition – executes a command with a 30‑second timeout.
 */
const bashTool = tool({
  description:
    'Execute a bash command on the server. Provide the exact command string.',
  parameters: z.object({
    command: z.string().describe('The bash/shell command to execute'),
  }),
  execute: async ({ command }) => {
    // Load allow list configuration
    const cfg = await loadConfig();
    const allowAll = cfg.allowAll ?? false;
    const allowList = cfg.allowList ?? ['ls', 'pwd'];
    const baseCmd = command.trim().split(/\s+/)[0];
    if (!allowAll && !allowList.includes(baseCmd)) {
      return { error: `Command "${baseCmd}" is not allowed.` };
    }
    try {
      const { stdout, stderr } = await execAsync(command);
      return { stdout: stdout.trim(), stderr: stderr.trim() };
    } catch (err: any) {
      // execAsync throws on non‑zero exit or timeout
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
    const { prompt } = await request.json();
    if (!prompt) {
      return NextResponse.json({ error: 'Missing prompt' }, { status: 400 });
    }

    const cfg = await loadConfig();
    const provider = createOpenAICompatible({
      name: cfg.provider,
      baseURL: cfg.baseURL,
      apiKey: cfg.apiKey,
    });
    const model = provider(cfg.model, { maxRetries: 0 });

    const instructions = 'You are a helpful assistant. Use the bash tool when necessary to execute shell commands.';

    const result = await generateText({
      model,
      prompt,
      instructions,
      tools: { bash: bashTool },
      maxSteps: 5,
    });

    // Extract text and tool outputs from steps
    const lastStep = result.steps?.[result.steps.length - 1];
    const text = lastStep?.content
      ?.filter((c: any) => c.type === 'text')
      .map((c: any) => c.text ?? '')
      .join('') ?? '';

    const toolOutputs: any[] = [];
    for (const step of result.steps ?? []) {
      for (const item of step.content ?? []) {
        if (item.type === 'tool-result') {
          toolOutputs.push(item.output ?? {});
        }
      }
    }

    console.log('=== Text ===');
    console.log(text);
    console.log('=== Tool Outputs ===');
    console.log(JSON.stringify(toolOutputs, null, 2));

    return NextResponse.json({ text, toolOutputs });
  } catch (e: any) {
    console.error(e);
    return NextResponse.json({ error: e.message ?? 'Internal error' }, { status: 500 });
  }
}

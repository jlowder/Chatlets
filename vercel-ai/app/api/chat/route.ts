import { NextResponse } from 'next/server';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import { generateText, tool } from 'ai';
import { z } from 'zod';
import { promises as fs } from 'fs';
const { constants } = fs;
import { execAsync } from '../../../lib/execAsync';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../shared/config-loader';

const DEFAULT_CONFIG = {
  baseURL: 'http://localhost:8080/v1',
  apiKey: 'sk-fallback',
  model: 'gpt-4',
  allowList: [],
  allowAll: true,
};

/**
 * Reads the LLM configuration from config/config.json, walking up the directory tree.
 */
async function loadConfig() {
  let dir = process.cwd();
  const root = '/';
  while (dir !== root) {
    const configPath = `${dir}/config/config.json`;
    try {
      await fs.access(configPath, constants.F_OK);
    } catch {
      dir = `${dir}/..`;
      continue;
    }
    try {
      const data = await fs.readFile(configPath, 'utf-8');
      const parsed = JSON.parse(data);
      return { ...DEFAULT_CONFIG, ...parsed };
    } catch {
      return DEFAULT_CONFIG;
    }
  }
  return DEFAULT_CONFIG;
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
    const body = await request.json();
    const messages = body.messages || [{ role: 'user' as const, content: body.prompt }];
    const prompt = messages[messages.length - 1]?.content;
    if (!prompt) {
      return NextResponse.json({ error: 'Missing prompt' }, { status: 400 });
    }

    // Build conversation history from all messages except the last
    const history = messages
      .slice(0, -1)
      .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
      .join('\n');

    // The last message is the new prompt
    const conversation = history
      ? `${history}\n\nUser: ${prompt}`
      : prompt;

    const cfg = await loadConfig();
    const provider = createOpenAICompatible({
      name: cfg.provider,
      baseURL: cfg.baseURL,
      apiKey: cfg.apiKey,
    });
    const model = provider(cfg.model, { maxRetries: 0 });

    const config = loadChatletsConfig();
    const bashPrompt = getBashCommandsPrompt(config);
    const instructions = `You are a helpful assistant. ${bashPrompt} Answer questions directly from your knowledge whenever possible. Only use the bash tool when the user explicitly requests a shell command. Do NOT use bash for: general knowledge questions, math, definitions, explanations, or factual queries. The user does not want command-line access unless they specifically ask for it.`;

    const result = await generateText({
      model,
      prompt: conversation,
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

import { NextResponse } from 'next/server';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../../shared/config-loader';

const execAsync = promisify(exec);

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
    const cmdName = cmd.split(/\s+/)[0] || '';

    const allowAll = cfg.allowAll ?? false;
    const allowList = cfg.allowList ?? ['ls', 'pwd'];

    if (!allowAll && !allowList.includes(cmdName)) {
      console.log('Command not allowed:', cmdName);
      return { error: `Command '${cmdName}' not allowed` };
    }

    try {
      const { stdout, stderr } = await execAsync(cmd, { timeout: 30000 });
      console.log('execAsync success:', { stdout, stderr });
      return {
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      };
    } catch (err: any) {
      console.log('execAsync error:', err);
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

    // Extract tool outputs and map them to standard format robustly
    const toolOutputs: any[] = (result.toolResults || []).map((tr: any) => {
      console.log('=== Mapping tr ===', JSON.stringify(tr, null, 2));

      // 1. Resolve output container: tr.result or tr.output or tr itself
      let rawOutput = tr.result !== undefined ? tr.result : (tr.output !== undefined ? tr.output : tr);

      // 2. If it is a string, try parsing it as JSON first (e.g. if stringified by the runner)
      if (typeof rawOutput === 'string') {
        try {
          rawOutput = JSON.parse(rawOutput);
        } catch {
          // If not valid JSON, treat the plain string as stdout
          return {
            stdout: rawOutput.trim(),
            stderr: '',
            error: tr.isError ? (tr.error?.message || 'Execution failed') : undefined,
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
        error: error || (tr.isError ? (tr.error?.message || 'Execution failed') : undefined),
      };
    });

    // 4. Double-insurance fallback: If toolOutputs is empty, try extracting from steps content
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

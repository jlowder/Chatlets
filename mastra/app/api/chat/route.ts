import { NextResponse } from 'next/server';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadChatletsConfig, getBashCommandsPrompt } from '../../../shared/config-loader';

const execAsync = promisify(exec);
const CONFIG_PATH = join(process.cwd(), 'config.json');

function loadConfig() {
  const raw = readFileSync(CONFIG_PATH, 'utf-8');
  return JSON.parse(raw);
}

function executeBash(command: string, cfg: { allowList: string[]; allowAll: boolean }): Promise<string> {
  const cmd = command.trim();
  const cmdName = cmd.split(/\s+/)[0] || '';

  if (!cfg.allowAll && !cfg.allowList.includes(cmdName)) {
    return Promise.resolve(JSON.stringify({ error: `Command '${cmdName}' not allowed` }));
  }

  return execAsync(cmd, { timeout: 30000 })
    .then(({ stdout, stderr }) => {
      const output: Record<string, unknown> = { stdout };
      if (stderr) output.stderr = stderr;
      return JSON.stringify(output);
    })
    .catch((err: Error) => {
      if (err.message.includes('timeout')) {
        return JSON.stringify({ error: 'Command timed out' });
      }
      return JSON.stringify({ error: err.message });
    });
}

async function chatWithLLM(messages: any[], cfg: any) {
  const res = await fetch(`${cfg.baseURL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${cfg.apiKey}`,
    },
    body: JSON.stringify({
      model: cfg.model,
      messages: [
        {
          role: 'system',
          content: `You are a helpful assistant. ${getBashCommandsPrompt(loadChatletsConfig())} Answer questions directly from your knowledge whenever possible. Only use the bash tool when the user explicitly requests a shell command. Do NOT use bash for general knowledge questions, math, definitions, explanations, or factual queries.`,
        },
        ...messages,
      ],
      tool_choice: 'auto',
      tools: [
        {
          type: 'function',
          function: {
            name: 'bash',
            description: 'Execute a bash command and return the output',
            parameters: {
              type: 'object',
              properties: {
                command: { type: 'string', description: 'The bash command to execute' },
              },
              required: ['command'],
            },
          },
        },
      ],
      max_tokens: 4096,
      max_steps: 5,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`LLM error: ${res.status} ${err}`);
  }

  return res.json();
}

export async function POST(request: Request) {
  try {
    const cfg = loadConfig();
    const data = await request.json();

    const messages = data.messages || [];
    const prompt = messages.length > 0
      ? messages[messages.length - 1].content
      : (data.prompt || '');

    if (!prompt) {
      return NextResponse.json({ error: 'No input provided' }, { status: 400 });
    }

    let currentMessages = messages.map(m => ({ role: m.role, content: m.content }));
    let toolOutputs: any[] = [];
    let responseMessage: any;

    // Tool calling loop
    for (let step = 0; step < 5; step++) {
      const llmRes = await chatWithLLM(currentMessages, cfg);
      responseMessage = llmRes.choices?.[0]?.message;

      if (!responseMessage) {
        return NextResponse.json({ error: 'No response from LLM' }, { status: 500 });
      }

      // Add the assistant message to history
      currentMessages.push({
        role: 'assistant',
        content: responseMessage.content || '',
        tool_calls: responseMessage.tool_calls,
      });

      if (responseMessage.tool_calls) {
        // Execute each tool call
        for (const toolCall of responseMessage.tool_calls) {
          if (toolCall.function.name === 'bash') {
            const args = JSON.parse(toolCall.function.arguments || '{}');
            const result = await executeBash(args.command, cfg);

            toolOutputs.push({
              stdout: (() => { try { return JSON.parse(result).stdout; } catch { return null; } })(),
              stderr: (() => { try { return JSON.parse(result).stderr; } catch { return null; } })(),
              error: (() => { try { return JSON.parse(result).error; } catch { return null; } })(),
            });

            // Add tool result to messages
            currentMessages.push({
              role: 'tool',
              tool_call_id: toolCall.id,
              content: result,
            });
          }
        }
        // Continue loop with tool results
        continue;
      }

      // No more tool calls - return final text
      return NextResponse.json({
        text: toolOutputs.length > 0 ? '' : (responseMessage.content || ''),
        toolOutputs,
      });
    }

    // Max steps reached
    return NextResponse.json({
      text: responseMessage.content || '',
      toolOutputs,
    });

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

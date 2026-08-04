import { execFile } from 'child_process';

export function tokenize(command: string): string[] {
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

export function execAsync(command: string, timeoutMs = 30000): Promise<{ stdout: string; stderr: string }> {
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

    execFile(cmdName, args.slice(1), { timeout: timeoutMs }, (error, stdout, stderr) => {
      if (error) {
        // Embed stdout and stderr on the error object so the caller can extract them
        const errWithOutputs = Object.assign(error, { stdout, stderr });
        if ((error as any).killed && (error as any).signal === 'SIGTERM') {
          errWithOutputs.message = 'Command timed out';
        }
        return reject(errWithOutputs);
      }
      resolve({
        stdout: stdout,
        stderr: stderr,
      });
    });
  });
}

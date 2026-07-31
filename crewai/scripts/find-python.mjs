#!/usr/bin/env node

/**
 * Auto-detect Python from virtual environment and run agent_service.py.
 * Searches for .venv, venv, .env, env in priority order.
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const venvDirs = ['.venv', 'venv', '.env', 'env'];
let py = 'python';

for (const d of venvDirs) {
  const bin =
    process.platform === 'win32'
      ? path.join(d, 'Scripts', 'python.exe')
      : path.join(d, 'bin', 'python');

  if (fs.existsSync(bin)) {
    py = bin;
    break;
  }
}

console.log('Using Python:', py);

try {
  execSync(`"${py}" "${path.join(__dirname, '..', 'agent_service.py')}"`, { stdio: 'inherit' });
} catch (e) {
  process.exitCode = e.status || 1;
}

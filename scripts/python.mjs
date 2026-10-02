import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!existsSync(python)) { console.error('Create the Python environment first. See README.md.'); process.exit(1); }
  const child = spawn(python, process.argv.slice(2), { cwd: root, stdio: 'inherit' });
  child.on('error', error => { console.error(error.message); process.exit(1); });
  child.on('exit', code => process.exit(code ?? 1));
  process.on('SIGINT', () => child.kill('SIGINT'));
  process.on('SIGTERM', () => child.kill('SIGTERM'));
}

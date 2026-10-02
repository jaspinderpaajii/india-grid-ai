import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { root, python } from './python.mjs';

if (!existsSync(python) || !existsSync(path.join(root, 'artifacts/report.json'))) {
  console.error('Python environment or trained model is missing. Follow README.md setup and run npm run train.');
  process.exit(1);
}
const children = [];
let closing = false;
function stop(code = 0) {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill();
  setTimeout(() => process.exit(code), 300);
}
for (const [command, args] of [[python, ['-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000']], [process.execPath, ['node_modules/vite/bin/vite.js']]]) {
  const child = spawn(command, args, { cwd: root, stdio: 'inherit', windowsHide: true });
  children.push(child);
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => { if (!closing) stop(code ?? 1); });
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());

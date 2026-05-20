import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'python-backend');
const viteBin = path.join(rootDir, 'node_modules', 'vite', 'bin', 'vite.js');

const modeAliases = new Map([
  ['all', 'all'],
  ['both', 'all'],
  ['full', 'all'],
  ['frontend', 'frontend'],
  ['front', 'frontend'],
  ['web', 'frontend'],
  ['vite', 'frontend'],
  ['fe', 'frontend'],
  ['backend', 'backend'],
  ['back', 'backend'],
  ['api', 'backend'],
  ['fastapi', 'backend'],
  ['be', 'backend'],
]);

function normalizeMode(rawArgs) {
  const normalizedArgs = rawArgs
    .map((arg) => arg.trim().replace(/^--?/, '').toLowerCase())
    .filter(Boolean);

  if (!normalizedArgs.length) {
    return 'all';
  }

  const selected = new Set();
  for (const arg of normalizedArgs) {
    const mode = modeAliases.get(arg);
    if (!mode) {
      printUsage();
      process.exit(1);
    }
    selected.add(mode);
  }

  if (selected.has('all') || selected.size > 1) {
    return 'all';
  }

  return selected.values().next().value;
}

function printUsage() {
  console.log('用法：');
  console.log('  npm run test              # 默认同时启动前端和后端');
  console.log('  npm run test -- frontend  # 只启动前端 Vite');
  console.log('  npm run test -- backend   # 只启动后端 FastAPI');
}

function ensureViteInstalled() {
  if (existsSync(viteBin)) {
    return;
  }

  console.error('未找到 Vite，请先运行 npm install。');
  process.exit(1);
}

function checkPortAvailable(port, label) {
  return new Promise((resolve) => {
    const server = net.createServer();

    server.once('error', (error) => {
      if (error && error.code === 'EADDRINUSE') {
        console.error(`${label} 端口 ${port} 已被占用。请先关闭旧服务，或运行：`);
        console.error(`  PowerShell: Get-NetTCPConnection -LocalPort ${port} -State Listen | Select-Object OwningProcess`);
        resolve(false);
        return;
      }

      console.error(`${label} 端口 ${port} 检查失败：${error.message}`);
      resolve(false);
    });

    server.once('listening', () => {
      server.close(() => resolve(true));
    });

    server.listen(port, '127.0.0.1');
  });
}

function startProcess(label, command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd ?? rootDir,
    env: { ...process.env, ...options.env },
    stdio: 'inherit',
    windowsHide: false,
  });

  child.on('error', (error) => {
    console.error(`[${label}] 启动失败：${error.message}`);
  });

  return child;
}

function startFrontend() {
  ensureViteInstalled();
  console.log('前端：http://127.0.0.1:1420');
  return startProcess('frontend', process.execPath, [viteBin, '--host', '127.0.0.1', '--port', '1420']);
}

function startBackend() {
  console.log('后端：http://127.0.0.1:19453');
  return startProcess('backend', 'python', ['-m', 'app.main', 'serve', '--host', '127.0.0.1', '--port', '19453'], {
    cwd: backendDir,
  });
}

function stopChildren(children) {
  for (const child of children) {
    if (!child.killed && child.exitCode === null) {
      child.kill('SIGTERM');
    }
  }
}

const mode = normalizeMode(process.argv.slice(2));
const children = [];

console.log(`启动模式：${mode === 'all' ? '前端 + 后端' : mode === 'frontend' ? '仅前端' : '仅后端'}`);

const portChecks = [];
if (mode === 'all' || mode === 'backend') {
  portChecks.push(checkPortAvailable(19453, '后端'));
}
if (mode === 'all' || mode === 'frontend') {
  portChecks.push(checkPortAvailable(1420, '前端'));
}

if ((await Promise.all(portChecks)).some((available) => !available)) {
  process.exit(1);
}

if (mode === 'all' || mode === 'backend') {
  children.push(startBackend());
}

if (mode === 'all' || mode === 'frontend') {
  children.push(startFrontend());
}

let shuttingDown = false;

for (const child of children) {
  child.on('exit', (code, signal) => {
    if (shuttingDown) {
      return;
    }

    shuttingDown = true;
    stopChildren(children);
    process.exit(code ?? (signal ? 1 : 0));
  });
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    stopChildren(children);
    process.exit(0);
  });
}

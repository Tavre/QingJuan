import { spawn } from 'node:child_process';
import { copyFileSync, cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'python-backend');
const distDir = path.join(rootDir, 'dist');
const releaseDir = path.join(rootDir, 'release');
const desktopDir = path.join(releaseDir, 'desktop');
const mobileDir = path.join(releaseDir, 'mobile');
const desktopExeName = 'qingjuan-desktop.exe';
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd ?? rootDir,
      env: { ...process.env, ...options.env },
      stdio: 'inherit',
      shell: process.platform === 'win32',
      windowsHide: false,
    });

    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} ${args.join(' ')} exited with code ${code}`));
    });
  });
}

async function sleep(ms) {
  await new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function removeDir(target) {
  if (existsSync(target)) {
    for (let attempt = 0; attempt < 6; attempt += 1) {
      try {
        rmSync(target, { recursive: true, force: true });
        return;
      } catch (error) {
        if (attempt === 5) {
          throw error;
        }
        await sleep(500);
      }
    }
  }
}

function copyPwaAssets() {
  const iconSource = path.join(rootDir, 'qj_icon2.png');
  const iconTarget = path.join(distDir, 'qj_icon2.png');
  if (existsSync(iconSource)) {
    copyFileSync(iconSource, iconTarget);
  }
}

function writeDesktopHelpers() {
  writeFileSync(
    path.join(desktopDir, '启动青卷.bat'),
    [
      '@echo off',
      'cd /d "%~dp0"',
      `start "QingJuan Backend" "%~dp0${desktopExeName}" serve --host 127.0.0.1 --port 19453`,
      'timeout /t 2 /nobreak >nul',
      'start "" "http://127.0.0.1:19453"',
      '',
    ].join('\r\n'),
    'utf-8',
  );

  writeFileSync(
    path.join(desktopDir, '启动青卷-局域网.bat'),
    [
      '@echo off',
      'cd /d "%~dp0"',
      `start "QingJuan Backend" "%~dp0${desktopExeName}" serve --host 0.0.0.0 --port 19453`,
      'timeout /t 2 /nobreak >nul',
      'start "" "http://127.0.0.1:19453"',
      '',
    ].join('\r\n'),
    'utf-8',
  );

  writeFileSync(
    path.join(desktopDir, 'README.txt'),
    [
      '青卷桌面端打包产物',
      '',
      '1. 双击“启动青卷.bat”启动本机桌面版。',
      '2. 浏览器会自动打开 http://127.0.0.1:19453。',
      '3. 如需手机访问同一台电脑上的青卷，双击“启动青卷-局域网.bat”，然后在手机浏览器打开 http://电脑局域网IP:19453。',
      '4. 数据默认保存在当前用户环境对应的 QingJuan data 目录；也可启动前设置 QINGJUAN_DATA_DIR。',
      '',
    ].join('\r\n'),
    'utf-8',
  );
}

function writeMobileReadme() {
  writeFileSync(
    path.join(mobileDir, 'README.txt'),
    [
      '青卷移动端 Web / PWA 打包产物',
      '',
      '这是移动浏览器/PWA 静态包，不包含 Python 后端。',
      '部署方式：',
      '1. 将本目录作为静态站点部署，或复制到任意静态服务器。',
      '2. 后端需单独运行，并监听移动端可访问的地址，例如电脑局域网 IP 的 19453 端口。',
      '3. 如果静态站点与后端同主机，前端会默认连接 http://当前主机:19453。',
      '4. 在手机浏览器打开后，可通过浏览器菜单“添加到主屏幕”作为 PWA 使用。',
      '',
    ].join('\r\n'),
    'utf-8',
  );
}

async function buildFrontend() {
  await run(npmCommand, ['run', 'build']);
  copyPwaAssets();
}

async function buildDesktop() {
  await removeDir(desktopDir);
  mkdirSync(desktopDir, { recursive: true });

  const addDataSeparator = process.platform === 'win32' ? ';' : ':';
  await run('python', [
    '-m',
    'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onefile',
    '--name',
    'qingjuan-desktop',
    '--paths',
    backendDir,
    '--collect-all',
    'curl_cffi',
    '--collect-all',
    'websockets',
    '--collect-all',
    'PIL',
    '--add-data',
    `${distDir}${addDataSeparator}frontend-dist`,
    '--distpath',
    desktopDir,
    '--workpath',
    path.join(backendDir, 'build'),
    '--specpath',
    backendDir,
    path.join(backendDir, 'app', 'main.py'),
  ]);

  writeDesktopHelpers();
}

async function buildMobile() {
  await removeDir(mobileDir);
  mkdirSync(mobileDir, { recursive: true });
  cpSync(distDir, mobileDir, { recursive: true });
  writeMobileReadme();
}

async function main() {
  const mode = (process.argv[2] || 'all').toLowerCase();
  if (!['all', 'desktop', 'mobile'].includes(mode)) {
    throw new Error('用法：npm run build:release -- [all|desktop|mobile]');
  }

  if (mode === 'all') {
    await removeDir(releaseDir);
  }
  mkdirSync(releaseDir, { recursive: true });

  await buildFrontend();
  if (mode === 'all' || mode === 'desktop') {
    await buildDesktop();
  }
  if (mode === 'all' || mode === 'mobile') {
    await buildMobile();
  }

  console.log(`打包完成：${releaseDir}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});

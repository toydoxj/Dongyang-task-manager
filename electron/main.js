// (주)동양구조 업무관리 — Electron 진입점
//
// 개발 모드 (ELECTRON_DEV=1):
//   - 백엔드: 우리가 spawn (uv run uvicorn)
//   - 프론트: 사용자가 별도로 띄운 Next dev 서버 (ELECTRON_DEV_URL)
//
// 운영 모드 (electron-builder 패키징):
//   - 백엔드: PyInstaller 번들 (extraResources/backend/backend.exe) — Phase 4 마무리
//   - 프론트: 백엔드가 정적 빌드 서빙 → http://127.0.0.1:{port}

const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");
const { spawn } = require("child_process");
const kill = require("tree-kill");

const IS_DEV = process.env.ELECTRON_DEV === "1" || !app.isPackaged;
const DEV_URL = process.env.ELECTRON_DEV_URL || "http://localhost:3000";

let mainWindow = null;
let backendProcess = null;
let backendPort = 0;
let backendExitInfo = null;

function getFreePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

function getBackendLogPath() {
  const dir = app.getPath("userData");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, "backend.log");
}

function waitForBackend(port, maxRetries = 240) {
  return new Promise((resolve, reject) => {
    let tries = 0;
    const check = () => {
      if (backendExitInfo) {
        reject(
          new Error(
            `백엔드가 예기치 않게 종료되었습니다 (exit ${backendExitInfo.code}).`,
          ),
        );
        return;
      }
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) resolve();
        else retry();
      });
      req.on("error", retry);
      req.setTimeout(1000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (++tries >= maxRetries) {
        reject(new Error("백엔드 시작 시간 초과 (120초)"));
        return;
      }
      setTimeout(check, 500);
    };
    check();
  });
}

async function startBackend() {
  backendPort = await getFreePort();

  let cmd, args, cwd;
  if (IS_DEV) {
    // dev: uv run uvicorn 사용 (uv가 PATH에 있어야 함)
    cmd = "uv";
    args = [
      "run",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(backendPort),
    ];
    cwd = path.resolve(__dirname, "..", "backend");
  } else {
    // prod: PyInstaller 번들된 backend.exe (Phase 4에서 생성)
    cmd = path.join(process.resourcesPath, "backend", "backend.exe");
    args = [];
    cwd = path.dirname(cmd);
  }

  const logPath = getBackendLogPath();
  let logStream = null;
  try {
    logStream = fs.createWriteStream(logPath, { flags: "w" });
    logStream.write(`[launcher] cmd=${cmd}\n`);
    logStream.write(`[launcher] cwd=${cwd}\n`);
    logStream.write(`[launcher] port=${backendPort}\n\n`);
  } catch (_) {}

  backendExitInfo = null;
  backendProcess = spawn(cmd, args, {
    cwd,
    env: {
      ...process.env,
      BACKEND_PORT: String(backendPort),
      PYTHONIOENCODING: "utf-8",
    },
    stdio: ["ignore", "pipe", "pipe"],
    shell: IS_DEV, // dev에서 uv 같은 PATH 명령 해석 위해
  });

  backendProcess.stdout.on("data", (data) => {
    process.stdout.write(`[backend] ${data}`);
    if (logStream) logStream.write(data);
  });
  backendProcess.stderr.on("data", (data) => {
    process.stderr.write(`[backend:err] ${data}`);
    if (logStream) logStream.write(data);
  });
  backendProcess.on("exit", (code, signal) => {
    backendExitInfo = { code, signal };
    if (logStream) {
      logStream.write(`\n[launcher] exit code=${code} signal=${signal}\n`);
      logStream.end();
    }
    backendProcess = null;
  });

  await waitForBackend(backendPort);
}

function stopBackend() {
  if (backendProcess && backendProcess.pid) {
    kill(backendProcess.pid);
    backendProcess = null;
  }
}

async function createWindow() {
  try {
    await startBackend();
  } catch (err) {
    dialog.showErrorBox(
      "동양구조 업무관리 — 시작 오류",
      `${err.message}\n\n로그: ${getBackendLogPath()}`,
    );
    app.quit();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: `동양구조 업무관리 v${app.getVersion()}`,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 프론트엔드 주소
  const frontUrl = IS_DEV ? DEV_URL : `http://127.0.0.1:${backendPort}`;
  mainWindow.loadURL(frontUrl);

  // dev에서는 백엔드 base URL 을 환경 주입 (window.__BACKEND_URL__)
  if (IS_DEV) {
    mainWindow.webContents.on("did-finish-load", () => {
      mainWindow.webContents.executeJavaScript(
        `window.__BACKEND_URL__ = "http://127.0.0.1:${backendPort}";`,
      ).catch(() => {});
    });
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── IPC ──
ipcMain.handle("get-version", () => app.getVersion());
ipcMain.handle("get-backend-url", () => `http://127.0.0.1:${backendPort}`);

// ── 생명주기 ──
app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});

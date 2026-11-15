// Desktop shell for Phoenical, the burning calendar.
// The built site (dist/) is served from a tiny local HTTP server on 127.0.0.1, so web workers,
// lazy-loaded chunks and the URL-hash view state behave exactly as they do in a browser.
const { app, BrowserWindow, shell } = require("electron");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const DIST = path.join(__dirname, "..", "dist");
const PORT = 47615;
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".csv": "text/csv; charset=utf-8",
  ".woff2": "font/woff2",
};

function serve() {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
    let file = path.normalize(path.join(DIST, urlPath === "/" ? "index.html" : urlPath));
    // Never serve anything outside dist/.
    if (!file.startsWith(DIST)) {
      res.writeHead(403).end();
      return;
    }
    fs.readFile(file, (err, data) => {
      if (err) {
        res.writeHead(404, { "Content-Type": "text/plain" }).end("Not found");
        return;
      }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file).toLowerCase()] || "application/octet-stream" });
      res.end(data);
    });
  });
  // A fixed port keeps the same web origin between launches, so saved settings persist.
  // If it is taken, fall back to any free port.
  return new Promise((resolve) => {
    server.once("error", () => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
    server.listen(PORT, "127.0.0.1", () => resolve(server.address().port));
  });
}

async function createWindow() {
  if (!fs.existsSync(path.join(DIST, "index.html"))) {
    console.error("dist/ not found. Run `npm run build` first (or use `npm run app`).");
    app.quit();
    return;
  }
  const port = await serve();
  const win = new BrowserWindow({
    width: 1480,
    height: 940,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#0a0d14",
    title: "Phoenical · Burning Calendar",
    icon: path.join(DIST, "emblem.png"),
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  // Links to other sites (map attributions, references) open in the normal browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${port}`)) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });
  await win.loadURL(`http://127.0.0.1:${port}/`);
}

// One window only: starting the app again focuses the one that is already open.
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
  app.on("window-all-closed", () => app.quit());
}

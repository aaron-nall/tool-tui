# Copyright (c) 2026
"""Web-based configuration editor for Tool TUI."""

import json
import logging
import os
import signal
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from textual.app import App as TextualApp

from tool_tui.themes import CUSTOM_THEMES

from tool_tui.config import AppConfig, generate_schema

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tool TUI Config Editor</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1a1a1a; --card: #f5f5f5; --border: #d0d0d0;
    --accent: #0066cc; --danger: #cc3333; --success: #228833;
    --input-bg: #ffffff; --input-border: #bbbbbb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1a1a; --fg: #e0e0e0; --card: #2a2a2a; --border: #444444;
      --accent: #4499dd; --danger: #ee5555; --success: #44bb66;
      --input-bg: #333333; --input-border: #555555;
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--fg);
    max-width: 800px; margin: 0 auto; padding: 24px 16px;
  }
  h1 { font-size: 1.5rem; margin-bottom: 8px; }
  h2 { font-size: 1.1rem; margin-bottom: 12px; color: var(--accent); }
  .section { margin-bottom: 24px; }
  label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }
  select, input[type="text"] {
    width: 100%; padding: 8px; border: 1px solid var(--input-border);
    border-radius: 4px; background: var(--input-bg); color: var(--fg);
    font-size: 0.9rem;
  }
  input[type="text"].error { border-color: var(--danger); }
  .tool-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; margin-bottom: 12px; position: relative;
  }
  .tool-card .tool-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
  }
  .tool-card .tool-header span { font-weight: 700; font-size: 0.95rem; }
  .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 8px; }
  .field-row.full { grid-template-columns: 1fr; }
  .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .checkbox-row input { width: auto; }
  .checkbox-row label { display: inline; margin: 0; }
  .btn-group { display: flex; gap: 6px; }
  button {
    padding: 6px 14px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--card); color: var(--fg); cursor: pointer; font-size: 0.85rem;
  }
  button:hover { border-color: var(--accent); }
  button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  button.primary:hover { opacity: 0.9; }
  button.danger { color: var(--danger); border-color: var(--danger); }
  button.danger:hover { background: var(--danger); color: #fff; }
  .actions { display: flex; gap: 12px; align-items: center; margin-top: 16px; }
  #status {
    font-size: 0.9rem; padding: 4px 0;
  }
  #status.ok { color: var(--success); }
  #status.err { color: var(--danger); }
  .field-error { color: var(--danger); font-size: 0.8rem; margin-top: 2px; }
</style>
</head>
<body>
<h1>Tool TUI Config Editor</h1>
<p style="margin-bottom:20px;font-size:0.85rem;color:var(--border);">
  Edit your configuration below and click Save.
</p>

<div class="section">
  <label for="default-view">Default View</label>
  <select id="default-view">
    <option value="tabs">Tabs</option>
    <option value="stacked">Stacked</option>
  </select>
</div>

<div class="section">
  <label for="theme">Theme</label>
  <select id="theme">
    <option value="">(default)</option>
  </select>
</div>

<div class="section">
  <h2>Tools</h2>
  <div id="tools-list"></div>
  <button onclick="addTool()">+ Add Tool</button>
</div>

<div class="actions">
  <button class="primary" onclick="save()">Save</button>
  <button class="primary" onclick="saveAndQuit()">Save &amp; Quit</button>
  <span id="status"></span>
</div>

<script>
let tools = [];

async function loadConfig() {
  const [configResp, themesResp] = await Promise.all([
    fetch("/api/config"),
    fetch("/api/themes")
  ]);
  if (!configResp.ok) { setStatus("Failed to load config", true); return; }
  const data = await configResp.json();
  document.getElementById("default-view").value = data.default_view || "tabs";

  if (themesResp.ok) {
    const themes = await themesResp.json();
    const sel = document.getElementById("theme");
    themes.forEach(name => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
    sel.value = data.theme || "";
  }

  tools = data.tools || [];
  renderTools();
}

function renderTools() {
  const container = document.getElementById("tools-list");
  container.innerHTML = "";
  tools.forEach((tool, i) => {
    const card = document.createElement("div");
    card.className = "tool-card";
    card.dataset.index = i;

    const header = document.createElement("div");
    header.className = "tool-header";
    const title = document.createElement("span");
    title.textContent = "Tool #" + (i + 1);
    const btnGroup = document.createElement("div");
    btnGroup.className = "btn-group";
    const upBtn = document.createElement("button");
    upBtn.innerHTML = "&#9650;"; upBtn.disabled = i === 0;
    upBtn.onclick = () => moveTool(i, -1);
    const downBtn = document.createElement("button");
    downBtn.innerHTML = "&#9660;"; downBtn.disabled = i === tools.length - 1;
    downBtn.onclick = () => moveTool(i, 1);
    const removeBtn = document.createElement("button");
    removeBtn.className = "danger"; removeBtn.textContent = "Remove";
    removeBtn.onclick = () => removeTool(i);
    btnGroup.append(upBtn, downBtn, removeBtn);
    header.append(title, btnGroup);

    const row1 = document.createElement("div");
    row1.className = "field-row";
    row1.appendChild(makeField("Name", "name", i, tool.name || ""));
    row1.appendChild(makeField("Command", "command", i, tool.command || ""));

    const row2 = document.createElement("div");
    row2.className = "field-row";
    row2.appendChild(makeField("Working Directory", "working_dir", i, tool.working_dir || "", "(optional)"));
    const checkDiv = document.createElement("div");
    checkDiv.className = "checkbox-row";
    checkDiv.style.alignSelf = "end";
    checkDiv.style.paddingBottom = "8px";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.id = "autostart-" + i;
    cb.dataset.field = "autostart"; cb.dataset.index = i;
    cb.checked = !!tool.autostart;
    const cbLabel = document.createElement("label");
    cbLabel.htmlFor = "autostart-" + i; cbLabel.textContent = "Autostart";
    checkDiv.append(cb, cbLabel);
    row2.appendChild(checkDiv);

    card.append(header, row1, row2);
    container.appendChild(card);
  });
}

function makeField(labelText, field, index, value, placeholder) {
  const div = document.createElement("div");
  const lbl = document.createElement("label");
  lbl.textContent = labelText;
  const inp = document.createElement("input");
  inp.type = "text";
  inp.dataset.field = field;
  inp.dataset.index = index;
  inp.value = value;
  if (placeholder) inp.placeholder = placeholder;
  div.append(lbl, inp);
  return div;
}

function collectFormData() {
  const inputs = document.querySelectorAll("#tools-list input[data-index]");
  inputs.forEach(inp => {
    const i = parseInt(inp.dataset.index);
    const field = inp.dataset.field;
    if (field === "autostart") {
      tools[i][field] = inp.checked;
    } else {
      tools[i][field] = inp.value;
    }
  });
  const themeVal = document.getElementById("theme").value;
  return {
    default_view: document.getElementById("default-view").value,
    theme: themeVal || null,
    tools: tools.map(t => {
      const out = { name: t.name, command: t.command, autostart: t.autostart || false };
      if (t.working_dir) out.working_dir = t.working_dir;
      return out;
    })
  };
}

function addTool() {
  collectFormData();
  tools.push({ name: "", command: "", autostart: false, working_dir: "" });
  renderTools();
  const last = document.querySelector(`[data-field="name"][data-index="${tools.length - 1}"]`);
  if (last) last.focus();
}

function removeTool(i) {
  collectFormData();
  tools.splice(i, 1);
  renderTools();
}

function moveTool(i, dir) {
  collectFormData();
  const j = i + dir;
  if (j < 0 || j >= tools.length) return;
  [tools[i], tools[j]] = [tools[j], tools[i]];
  renderTools();
}

function clearErrors() {
  document.querySelectorAll(".field-error").forEach(e => e.remove());
  document.querySelectorAll("input.error").forEach(e => e.classList.remove("error"));
}

function showFieldError(index, field, msg) {
  const inp = document.querySelector(`[data-field="${field}"][data-index="${index}"]`);
  if (!inp) return;
  inp.classList.add("error");
  const err = document.createElement("div");
  err.className = "field-error";
  err.textContent = msg;
  inp.parentElement.appendChild(err);
}

async function save() {
  clearErrors();
  const data = collectFormData();
  const resp = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (resp.ok) {
    setStatus("Saved successfully!", false);
  } else {
    const body = await resp.json();
    if (body.detail && Array.isArray(body.detail)) {
      body.detail.forEach(err => {
        const loc = err.loc || [];
        if (loc[0] === "tools" && typeof loc[1] === "number" && loc[2]) {
          showFieldError(loc[1], loc[2], err.msg);
        }
      });
      setStatus("Validation errors — see fields above", true);
    } else {
      setStatus(body.detail || "Save failed", true);
    }
  }
}

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = isError ? "err" : "ok";
  if (!isError) setTimeout(() => { el.textContent = ""; }, 3000);
}

loadConfig();

// Poll heartbeat to detect Ctrl+C shutdown; close tab when server is gone
let heartbeatFails = 0;
setInterval(async () => {
  try {
    const r = await fetch("/api/ping");
    if (r.ok) heartbeatFails = 0;
    else heartbeatFails++;
  } catch (e) { heartbeatFails++; }
  if (heartbeatFails >= 2) window.close();
}, 2000);

async function saveAndQuit() {
  clearErrors();
  const data = collectFormData();
  const resp = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (resp.ok) {
    setStatus("Saved. Shutting down...", false);
    await fetch("/api/shutdown", { method: "POST" });
    setTimeout(() => window.close(), 1000);
  } else {
    const body = await resp.json();
    if (body.detail && Array.isArray(body.detail)) {
      body.detail.forEach(err => {
        const loc = err.loc || [];
        if (loc[0] === "tools" && typeof loc[1] === "number" && loc[2]) {
          showFieldError(loc[1], loc[2], err.msg);
        }
      });
      setStatus("Validation errors — see fields above", true);
    } else {
      setStatus(body.detail || "Save failed", true);
    }
  }
}
</script>
</body>
</html>
"""


def _find_free_port() -> int:
    """Find an available TCP port on localhost.

    Returns:
        An available port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _config_to_yaml(config: AppConfig) -> str:
    """Serialize an AppConfig to clean YAML.

    Args:
        config: The configuration to serialize.

    Returns:
        YAML string representation.
    """
    data = config.model_dump(mode="json")
    for key in list(data.keys()):
        if data[key] is None:
            del data[key]
    for tool in data.get("tools", []):
        for key in list(tool.keys()):
            if tool[key] is None:
                del tool[key]
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def _create_app(config_path: str) -> FastAPI:
    """Create the FastAPI application for the config editor.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(title="Tool TUI Config Editor")
    path = Path(config_path)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """Serve the editor HTML page."""
        return _HTML_TEMPLATE

    @app.get("/api/config")
    async def get_config() -> JSONResponse:
        """Load and return the current configuration."""
        if not path.exists():
            return JSONResponse(
                content=AppConfig().model_dump(mode="json"),
            )
        try:
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            config = AppConfig(**raw)
            return JSONResponse(content=config.model_dump(mode="json"))
        except ValidationError as e:
            # Return raw data alongside errors so the user can fix it
            return JSONResponse(
                status_code=422,
                content={"detail": json.loads(e.json()), "raw": raw},
            )

    @app.put("/api/config")
    async def put_config(request: Request) -> JSONResponse:
        """Validate and save the configuration."""
        body = await request.json()
        try:
            config = AppConfig(**body)
        except ValidationError as e:
            return JSONResponse(status_code=422, content={"detail": json.loads(e.json())})

        yaml_content = _config_to_yaml(config)
        try:
            with open(path, "w") as f:
                f.write(yaml_content)
        except OSError as e:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Failed to save: {e}"},
            )

        return JSONResponse(content={"status": "ok"})

    @app.get("/api/themes")
    async def get_themes() -> JSONResponse:
        """Return available Textual theme names."""
        tapp = TextualApp()
        for t in CUSTOM_THEMES:
            tapp.register_theme(t)
        themes = sorted(tapp.available_themes.keys())
        return JSONResponse(content=themes)

    @app.get("/api/schema")
    async def get_schema() -> JSONResponse:
        """Return the JSON Schema for the configuration."""
        return JSONResponse(content=json.loads(generate_schema()))

    @app.get("/api/ping")
    async def ping() -> JSONResponse:
        """Heartbeat endpoint for the frontend to detect server shutdown."""
        return JSONResponse(content={"status": "ok"})

    @app.post("/api/shutdown")
    async def shutdown() -> JSONResponse:
        """Shut down the editor server."""
        threading.Timer(0.5, os.kill, args=[os.getpid(), signal.SIGINT]).start()
        return JSONResponse(content={"status": "shutting down"})

    return app


def run_editor(config_path: str) -> None:
    """Launch the configuration editor web server.

    Starts a FastAPI server on a free port and opens the default browser.

    Args:
        config_path: Path to the YAML configuration file.
    """
    path = Path(config_path)
    if not path.exists():
        default = AppConfig()
        with open(path, "w") as f:
            yaml.dump(default.model_dump(mode="json"), f, default_flow_style=False)
        logger.info("Created default config at %s", config_path)

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    app = _create_app(config_path)

    print(f"Starting config editor at {url}")
    print("Press Ctrl+C to stop the server.")

    threading.Timer(0.5, webbrowser.open, args=[url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

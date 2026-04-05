# tool-tui

A terminal UI for managing unattended tools and processes. Define tools in a YAML config file, then start/stop them and watch their output in real time.

## Features

- **Start/stop controls** for each tool with real-time stdout/stderr streaming
- **Two view modes**: tabbed (one tool per tab) or horizontally stacked (all visible)
- **Per-tool autostart** on launch
- **TUI config editor** via `--edit`
- **Web-based config editor** via `--edit-web`
- **JSON Schema** generation for config validation via `--schema`
- Output persists across view switches

## Installation

Requires Python 3.12+.

```bash
poetry install
```

## Usage

### Run the TUI

```bash
tool-tui --config config.yaml
```

### Keybindings

| Key | Action |
|-----|--------|
| `v` | Toggle between tabbed and stacked views |
| `q` | Quit (stops all running processes) |

### Edit config in the terminal

```bash
tool-tui --edit --config config.yaml
```

Opens an interactive TUI editor. Press Ctrl+S to save, Ctrl+Q to save and quit.

### Edit config in the browser

```bash
tool-tui --edit-web --config config.yaml
```

Opens a local web editor on `127.0.0.1`. Press Ctrl+C to stop the server.

### Print JSON Schema

```bash
tool-tui --schema
```

## Configuration

Create a `config.yaml` (see `config.example.yaml`):

```yaml
default_view: tabs  # "tabs" or "stacked"

tools:
  - name: "System Monitor"
    command: "vmstat 2"
    autostart: true

  - name: "Log Tailer"
    command: "tail -f /var/log/syslog"
    autostart: false
    working_dir: "/var/log"
```

### Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `default_view` | No | `tabs` | `tabs` or `stacked` |
| `tools[].name` | Yes | | Display name (must be unique) |
| `tools[].command` | Yes | | Shell command to execute |
| `tools[].autostart` | No | `false` | Start automatically on launch |
| `tools[].working_dir` | No | | Working directory for the command |

## Development

```bash
poetry install
pre-commit install
pre-commit run --all-files
```

# Copyright (c) 2026
"""Terminal-based configuration editor for Tool TUI."""

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Select, Static

from tool_tui.config import AppConfig
from tool_tui.themes import CUSTOM_THEMES


class ToolCard(Vertical):
    """A card representing a single tool's configuration fields."""

    DEFAULT_CSS = """
    ToolCard {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    ToolCard .tool-card-header {
        height: auto;
        margin: 0 0 1 0;
    }

    ToolCard .tool-card-header Static {
        width: 1fr;
        text-style: bold;
    }

    ToolCard .tool-card-header Button {
        min-width: 4;
        margin: 0 0 0 1;
    }

    ToolCard .field-row {
        height: auto;
        margin: 0 0 1 0;
    }

    ToolCard .field-row Label {
        width: 18;
        padding: 1 1 0 0;
        text-align: right;
    }

    ToolCard .field-row Input {
        width: 1fr;
    }

    ToolCard .checkbox-row {
        height: auto;
        margin: 0 0 0 19;
    }
    """

    def __init__(self, index: int, tool_data: dict, total: int) -> None:
        """Initialize a ToolCard widget."""
        super().__init__()
        self.tool_index = index
        self.tool_data = tool_data
        self.total = total

    def compose(self) -> ComposeResult:
        """Build the ToolCard UI."""
        i = self.tool_index
        with Horizontal(classes="tool-card-header"):
            yield Static(f"Tool #{i + 1}")
            yield Button("\u25b2", id=f"up-{i}", disabled=i == 0)
            yield Button("\u25bc", id=f"down-{i}", disabled=i >= self.total - 1)
            yield Button("Remove", id=f"remove-{i}", variant="error")
        with Horizontal(classes="field-row"):
            yield Label("Name")
            yield Input(
                value=self.tool_data.get("name", ""),
                placeholder="Tool name",
                id=f"name-{i}",
            )
        with Horizontal(classes="field-row"):
            yield Label("Command")
            yield Input(
                value=self.tool_data.get("command", ""),
                placeholder="Shell command",
                id=f"command-{i}",
            )
        with Horizontal(classes="field-row"):
            yield Label("Working Directory")
            yield Input(
                value=self.tool_data.get("working_dir", "") or "",
                placeholder="(optional)",
                id=f"working_dir-{i}",
            )
        yield Checkbox(
            "Autostart",
            value=bool(self.tool_data.get("autostart", False)),
            id=f"autostart-{i}",
            classes="checkbox-row",
        )


class ConfigEditorApp(App):
    """A Textual TUI for editing the tool-tui configuration file."""

    TITLE = "Tool TUI Config Editor"

    CSS = """
    #editor-scroll {
        height: 1fr;
    }

    #editor-content {
        height: auto;
        padding: 1 2;
    }

    .section-label {
        text-style: bold;
        margin: 0 0 1 0;
    }

    .global-field {
        height: auto;
        margin: 0 0 1 0;
    }

    .global-field Label {
        width: 18;
        padding: 1 1 0 0;
        text-align: right;
    }

    .global-field Select {
        width: 1fr;
    }

    #tools-section {
        height: auto;
        margin: 1 0 0 0;
    }

    #tools-list {
        height: auto;
    }

    #tools-header {
        height: auto;
        margin: 0 0 1 0;
    }

    #tools-header Static {
        width: 1fr;
        text-style: bold;
    }

    #add-tool {
        margin: 0 0 1 0;
    }

    #button-bar {
        height: auto;
        dock: bottom;
        padding: 1 2;
        background: $surface;
    }

    #button-bar Button {
        margin: 0 1 0 0;
    }

    #status-msg {
        width: 1fr;
        padding: 0 1;
    }

    #status-msg.ok {
        color: $success;
    }

    #status-msg.err {
        color: $error;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("ctrl+q", "save_and_quit", "Save & Quit"),
    ]

    def __init__(self, config_path: str) -> None:
        """Initialize the config editor app."""
        super().__init__()
        self.config_path = config_path
        self._load_data()

    def _load_data(self) -> None:
        """Load config data from disk into self.tools and self.global_opts."""
        path = Path(self.config_path)
        if path.exists():
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            self.global_opts = {
                "default_view": raw.get("default_view", "tabs"),
                "theme": raw.get("theme") or "",
            }
            self.tools = list(raw.get("tools", []))
        else:
            self.global_opts = {"default_view": "tabs", "theme": ""}
            self.tools = []

    def compose(self) -> ComposeResult:
        """Build the editor layout."""
        yield Header()
        with VerticalScroll(id="editor-scroll"):
            with Vertical(id="editor-content"):
                yield Static("Global Settings", classes="section-label")
                with Horizontal(classes="global-field"):
                    yield Label("Default View")
                    yield Select(
                        [("Tabs", "tabs"), ("Stacked", "stacked")],
                        value=self.global_opts["default_view"],
                        id="default-view",
                        allow_blank=False,
                    )
                with Horizontal(classes="global-field"):
                    yield Label("Theme")
                    yield Select(
                        self._theme_options(),
                        value=self.global_opts["theme"] or Select.BLANK,
                        id="theme",
                    )
                with Vertical(id="tools-section"):
                    with Horizontal(id="tools-header"):
                        yield Static("Tools")
                        yield Button("+ Add Tool", id="add-tool")
                    yield Vertical(id="tools-list")
        with Horizontal(id="button-bar"):
            yield Button("Save", id="save-btn", variant="primary")
            yield Button("Save & Quit", id="save-quit-btn", variant="primary")
            yield Static("", id="status-msg")
        yield Footer()

    def _theme_options(self) -> list[tuple[str, str]]:
        """Build the list of (label, value) for the theme selector."""
        tapp = App()
        for t in CUSTOM_THEMES:
            tapp.register_theme(t)
        names = sorted(tapp.available_themes.keys())
        return [("(default)", "")] + [(n, n) for n in names]

    async def on_mount(self) -> None:
        """Register themes and build initial tool cards."""
        for t in CUSTOM_THEMES:
            self.register_theme(t)
        await self._rebuild_tools()

    async def _rebuild_tools(self) -> None:
        """Rebuild all tool cards from self.tools."""
        container = self.query_one("#tools-list", Vertical)
        await container.remove_children()
        for i, tool in enumerate(self.tools):
            card = ToolCard(i, tool, len(self.tools))
            await container.mount(card)

    def _collect(self) -> dict:
        """Collect current form state into a config dict."""
        view_select = self.query_one("#default-view", Select)
        theme_select = self.query_one("#theme", Select)
        data = {
            "default_view": view_select.value,
            "theme": theme_select.value if theme_select.value != Select.BLANK else None,
        }
        tools = []
        for i in range(len(self.tools)):
            name_input = self.query_one(f"#name-{i}", Input)
            cmd_input = self.query_one(f"#command-{i}", Input)
            wd_input = self.query_one(f"#working_dir-{i}", Input)
            auto_cb = self.query_one(f"#autostart-{i}", Checkbox)
            tool = {
                "name": name_input.value,
                "command": cmd_input.value,
                "autostart": auto_cb.value,
            }
            if wd_input.value:
                tool["working_dir"] = wd_input.value
            tools.append(tool)
        data["tools"] = tools
        return data

    def _sync_tools_from_form(self) -> None:
        """Sync self.tools from the current form state."""
        self.tools = self._collect()["tools"]

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events for add, remove, reorder, and save."""
        button_id = event.button.id or ""

        if button_id == "add-tool":
            self._sync_tools_from_form()
            self.tools.append({"name": "", "command": "", "autostart": False})
            await self._rebuild_tools()
            new_input = self.query_one(f"#name-{len(self.tools) - 1}", Input)
            new_input.focus()
            return

        if button_id.startswith("remove-"):
            idx = int(button_id.split("-", 1)[1])
            self._sync_tools_from_form()
            self.tools.pop(idx)
            await self._rebuild_tools()
            return

        if button_id.startswith("up-"):
            idx = int(button_id.split("-", 1)[1])
            if idx > 0:
                self._sync_tools_from_form()
                self.tools[idx], self.tools[idx - 1] = self.tools[idx - 1], self.tools[idx]
                await self._rebuild_tools()
            return

        if button_id.startswith("down-"):
            idx = int(button_id.split("-", 1)[1])
            if idx < len(self.tools) - 1:
                self._sync_tools_from_form()
                self.tools[idx], self.tools[idx + 1] = self.tools[idx + 1], self.tools[idx]
                await self._rebuild_tools()
            return

        if button_id == "save-btn":
            await self.action_save()
            return

        if button_id == "save-quit-btn":
            await self.action_save_and_quit()
            return

    async def action_save(self) -> None:
        """Validate and save the config."""
        data = self._collect()
        try:
            config = AppConfig(**data)
        except ValidationError as e:
            self._set_status(str(e), is_error=True)
            return

        yaml_content = self._config_to_yaml(config)
        try:
            with open(self.config_path, "w") as f:
                f.write(yaml_content)
        except OSError as e:
            self._set_status(f"Failed to save: {e}", is_error=True)
            return

        self._set_status("Saved successfully!")

    async def action_save_and_quit(self) -> None:
        """Save and exit."""
        data = self._collect()
        try:
            config = AppConfig(**data)
        except ValidationError as e:
            self._set_status(str(e), is_error=True)
            return

        yaml_content = self._config_to_yaml(config)
        try:
            with open(self.config_path, "w") as f:
                f.write(yaml_content)
        except OSError as e:
            self._set_status(f"Failed to save: {e}", is_error=True)
            return

        self.exit()

    def _set_status(self, msg: str, is_error: bool = False) -> None:
        status = self.query_one("#status-msg", Static)
        status.update(msg)
        status.set_classes("err" if is_error else "ok")
        if not is_error:
            self.set_timer(3, lambda: status.update(""))

    @staticmethod
    def _config_to_yaml(config: AppConfig) -> str:
        data = config.model_dump(mode="json")
        for key in list(data.keys()):
            if data[key] is None:
                del data[key]
        for tool in data.get("tools", []):
            for key in list(tool.keys()):
                if tool[key] is None:
                    del tool[key]
        return yaml.dump(data, default_flow_style=False, sort_keys=False)


def run_tui_editor(config_path: str) -> None:
    """Launch the TUI configuration editor.

    Args:
        config_path: Path to the YAML configuration file.
    """
    path = Path(config_path)
    if not path.exists():
        default = AppConfig()
        with open(path, "w") as f:
            yaml.dump(default.model_dump(mode="json"), f, default_flow_style=False)

    else:
        try:
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                print(f"Error: Config file must contain a YAML mapping: {config_path}", file=sys.stderr)
                sys.exit(1)
            AppConfig(**raw)
        except yaml.YAMLError as e:
            print(f"Error: Invalid YAML in {config_path}:\n{e}", file=sys.stderr)
            sys.exit(1)
        except ValidationError as e:
            print(f"Config validation error in {config_path}:\n{e}", file=sys.stderr)
            sys.exit(1)

    app = ConfigEditorApp(config_path)
    app.run()

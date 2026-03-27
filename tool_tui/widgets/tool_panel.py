# Copyright (c) 2026
"""ToolPanel composite widget for displaying and controlling a single tool."""

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, RichLog, Static
from textual import work

from tool_tui.process import OutputLine, ToolProcess


class ToolPanel(Widget):
    """A composite widget for a single tool with controls and output log.

    Displays the tool name, start/stop and clear buttons, and a scrollable
    log of the tool's stdout/stderr output.

    Attributes:
        tool_process: The ToolProcess instance this panel controls.
    """

    DEFAULT_CSS = """
    ToolPanel {
        height: 1fr;
        layout: vertical;
    }

    ToolPanel .toolbar {
        height: auto;
        padding: 0 1;
        dock: top;
    }

    ToolPanel .tool-name {
        width: 1fr;
        content-align: left middle;
        padding: 0 1;
    }

    ToolPanel .status {
        width: auto;
        padding: 0 1;
    }

    ToolPanel .status.running {
        color: $success;
    }

    ToolPanel .status.stopped {
        color: $secondary;
    }

    ToolPanel Button {
        min-width: 10;
        margin: 0 1;
        padding: 0 1;
    }

    ToolPanel RichLog {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 1 1;
    }
    """

    def __init__(self, tool_process: ToolProcess, **kwargs) -> None:
        """Initialize the ToolPanel.

        Args:
            tool_process: The ToolProcess instance to control and display.
            **kwargs: Additional keyword arguments passed to Widget.
        """
        super().__init__(**kwargs)
        self.tool_process = tool_process
        self._is_running = tool_process.is_running

    def compose(self) -> ComposeResult:
        """Compose the panel layout."""
        running = self.tool_process.is_running
        with Horizontal(classes="toolbar"):
            yield Static(self.tool_process.name, classes="tool-name")
            if running:
                yield Static("RUNNING", classes="status running", id=f"status-{self._safe_id}")
                yield Button("Stop", id=f"toggle-{self._safe_id}", variant="default")
            else:
                yield Static("STOPPED", classes="status stopped", id=f"status-{self._safe_id}")
                yield Button("Start", id=f"toggle-{self._safe_id}", variant="default")
            yield Button("Clear", id=f"clear-{self._safe_id}", variant="default")
        yield RichLog(id=f"log-{self._safe_id}", highlight=False, markup=True, wrap=True)

    @property
    def _safe_id(self) -> str:
        """str: A CSS-safe identifier derived from the tool name."""
        return self.tool_process.name.lower().replace(" ", "-")

    async def on_mount(self) -> None:
        """Replay buffered output and start streaming on mount."""
        log = self.query_one(RichLog)
        for line in self.tool_process.output_buffer:
            self._write_line(log, line)

        if self.tool_process.is_running:
            self._stream_output()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for toggle and clear.

        Args:
            event: The button pressed event.
        """
        button_id = event.button.id or ""
        safe = self._safe_id

        if button_id == f"toggle-{safe}":
            if self._is_running:
                self._stop_tool()
            else:
                self._start_tool()
        elif button_id == f"clear-{safe}":
            self._clear_log()

    @work(exclusive=True, group="tool-lifecycle")
    async def _start_tool(self) -> None:
        """Start the tool process and begin streaming output."""
        try:
            await self.tool_process.start()
        except (RuntimeError, OSError) as e:
            log = self.query_one(RichLog)
            log.write(Text(f"Error: {e}", style="bold italic"))
            return

        self._update_status(running=True)
        await self._do_stream()
        self._update_status(running=False)

    @work(exclusive=True, group="tool-lifecycle")
    async def _stop_tool(self) -> None:
        """Stop the tool process."""
        await self.tool_process.stop()
        self._update_status(running=False)

    def _clear_log(self) -> None:
        """Clear the output log and buffer."""
        self.tool_process.clear_buffer()
        self.query_one(RichLog).clear()

    @work(exclusive=True, group="tool-lifecycle")
    async def _stream_output(self) -> None:
        """Stream output from an already-running process."""
        self._update_status(running=True)
        await self._do_stream()
        self._update_status(running=False)

    async def _do_stream(self) -> None:
        """Consume output from the process queue and write to the log."""
        log = self.query_one(RichLog)
        while True:
            try:
                line = await asyncio.wait_for(self.tool_process.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if not self.tool_process.is_running:
                    break
                continue

            if line is None:
                break

            self._write_line(log, line)

    def _write_line(self, log: RichLog, line: OutputLine) -> None:
        """Write an OutputLine to the RichLog with appropriate styling.

        Args:
            log: The RichLog widget to write to.
            line: The output line to display.
        """
        if line.is_stderr:
            log.write(Text(line.text, style="bold italic"))
        else:
            log.write(line.text)

    def _update_status(self, running: bool) -> None:
        """Update the status label and toggle button in place.

        Args:
            running: Whether the process is currently running.
        """
        self._is_running = running
        safe = self._safe_id

        status = self.query_one(f"#status-{safe}", Static)
        status.update("RUNNING" if running else "STOPPED")
        status.set_classes("status running" if running else "status stopped")

        toggle_btn = self.query_one(f"#toggle-{safe}", Button)
        if running:
            toggle_btn.label = "Stop"
            toggle_btn.variant = "default"
        else:
            toggle_btn.label = "Start"
            toggle_btn.variant = "default"

# Copyright (c) 2026
"""Main application for Tool TUI."""

import logging
from functools import partial

from textual.app import App, ComposeResult
from textual.command import CommandPalette, DiscoveryHit, Hits, Provider
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, TabPane, TabbedContent

from tool_tui import __version__
from tool_tui.config import AppConfig
from tool_tui.process import ToolProcess, process_manager
from tool_tui.themes import CUSTOM_THEMES
from tool_tui.widgets.tool_panel import ToolPanel

logger = logging.getLogger(__name__)


class AllThemesProvider(Provider):
    """Theme provider that includes textual-ansi (excluded by Textual's default)."""

    @property
    def commands(self) -> list[tuple[str, partial[None]]]:
        """Return a list of (theme_name, callback) tuples for all available themes."""
        themes = self.app.available_themes

        def set_app_theme(name: str) -> None:
            self.app.theme = name

        return [(theme.name, partial(set_app_theme, theme.name)) for theme in themes.values()]

    async def discover(self) -> Hits:
        """Yield all themes as discovery hits for the command palette."""
        for name, callback in self.commands:
            yield DiscoveryHit(name, callback)

    async def search(self, query: str) -> Hits:
        """Yield themes matching the given query string."""
        matcher = self.matcher(query)
        for name, callback in self.commands:
            if (match := matcher.match(name)) > 0:
                yield DiscoveryHit(name, callback, match)


class ToolTuiApp(App):
    """A TUI application for managing unattended tools.

    Provides two view modes (tabbed and horizontally stacked) with
    start/stop controls and real-time output for each configured tool.

    Attributes:
        config: The application configuration.
        processes: Dictionary of tool name to ToolProcess.
    """

    TITLE = f"Tool TUI v{__version__}"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        ("v", "toggle_view", "Toggle View"),
        ("q", "quit_app", "Quit"),
    ]

    def __init__(self, config: AppConfig) -> None:
        """Initialize the application.

        Args:
            config: The application configuration.
        """
        super().__init__()
        self.config = config
        self.current_view = config.default_view
        self.processes: dict[str, ToolProcess] = {}

        for tool_config in config.tools:
            self.processes[tool_config.name] = ToolProcess(
                name=tool_config.name,
                command=tool_config.command,
                working_dir=tool_config.working_dir,
            )

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield Container(id="main-container")
        yield Footer()

    async def on_mount(self) -> None:
        """Build the initial view and auto-start configured tools."""
        for t in CUSTOM_THEMES:
            self.register_theme(t)
        if self.config.theme:
            self.theme = self.config.theme
        await self._build_view()

        for tool_config in self.config.tools:
            if tool_config.autostart:
                process = self.processes[tool_config.name]
                try:
                    await process.start()
                except OSError as e:
                    logger.error("Failed to auto-start '%s': %s", tool_config.name, e)

        if any(tc.autostart for tc in self.config.tools):
            await self._rebuild_view()

    async def _build_view(self) -> None:
        """Build the current view inside the main container."""
        container = self.query_one("#main-container", Container)

        if self.current_view == "tabs":
            tabbed = TabbedContent(id="tabbed-view")
            await container.mount(tabbed)
            for name, process in self.processes.items():
                pane = TabPane(name, id=f"tab-{name.lower().replace(' ', '-')}")
                await tabbed.add_pane(pane)
                panel = ToolPanel(process)
                await pane.mount(panel)
        else:
            vertical = Vertical(id="stacked-view")
            await container.mount(vertical)
            for process in self.processes.values():
                panel = ToolPanel(process)
                await vertical.mount(panel)

    async def _rebuild_view(self) -> None:
        """Clear and rebuild the main container."""
        container = self.query_one("#main-container", Container)
        await container.remove_children()
        await self._build_view()

    async def action_toggle_view(self) -> None:
        """Toggle between tabbed and stacked view modes."""
        self.current_view = "stacked" if self.current_view == "tabs" else "tabs"
        await self._rebuild_view()
        self.notify(f"Switched to {self.current_view} view")

    def search_themes(self) -> None:
        """Show theme palette including textual-ansi."""
        self.push_screen(
            CommandPalette(
                providers=[AllThemesProvider],
                placeholder="Search for themes…",
            ),
        )

    async def action_quit_app(self) -> None:
        """Stop all running processes and quit."""
        await process_manager.async_shutdown()
        self.exit()

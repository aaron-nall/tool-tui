# Copyright (c) 2026
"""Entry point for Tool TUI."""

import argparse
import logging
import sys

from pydantic import ValidationError

from tool_tui.config import generate_schema, load_config


def main() -> None:
    """Parse arguments, load config, and run the TUI application."""
    parser = argparse.ArgumentParser(description="TUI for managing unattended tools")
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING)",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the JSON Schema for the config file and exit",
    )
    parser.add_argument(
        "--edit",
        action="store_true",
        help="Launch TUI-based configuration editor",
    )
    parser.add_argument(
        "--edit-web",
        action="store_true",
        help="Launch web-based configuration editor",
    )
    args = parser.parse_args()

    if args.schema:
        print(generate_schema())
        return

    if args.edit:
        from tool_tui.tui_editor import run_tui_editor

        run_tui_editor(args.config)
        return

    if args.edit_web:
        from tool_tui.editor import run_editor

        run_editor(args.config)
        return

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as e:
        print(f"Config validation error:\n{e}", file=sys.stderr)
        sys.exit(1)

    if not config.tools:
        print("No tools configured. Add tools to your config file.", file=sys.stderr)
        sys.exit(1)

    from tool_tui.app import ToolTuiApp

    app = ToolTuiApp(config)
    app.run()


if __name__ == "__main__":
    main()

# Copyright (c) 2026
"""Configuration loading and validation for Tool TUI."""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ViewMode(str, Enum):
    """Available view modes for the TUI layout."""

    TABS = "tabs"
    STACKED = "stacked"


class ToolConfig(BaseModel):
    """Configuration for a single tool.

    Attributes:
        name: Display name of the tool.
        command: Shell command to execute.
        autostart: Whether to start the tool automatically on launch.
        working_dir: Optional working directory for the command.
    """

    name: str = Field(..., min_length=1, description="Display name of the tool")
    command: str = Field(..., min_length=1, description="Shell command to execute")
    autostart: bool = Field(default=False, description="Whether to start the tool automatically on launch")
    working_dir: Optional[str] = Field(default=None, description="Optional working directory for the command")


class AppConfig(BaseModel):
    """Top-level application configuration.

    Attributes:
        default_view: Default view mode, either "tabs" or "stacked".
        tools: List of tool configurations.
    """

    default_view: ViewMode = Field(default=ViewMode.TABS, description="Default view mode")
    theme: Optional[str] = Field(default=None, description="Textual theme name")
    tools: list[ToolConfig] = Field(default_factory=list, description="List of tool configurations")

    @model_validator(mode="after")
    def validate_unique_names(self) -> "AppConfig":
        """Validate that all tool names are unique."""
        seen = set()
        for tool in self.tools:
            if tool.name in seen:
                raise ValueError(f"Duplicate tool name: {tool.name}")
            seen.add(tool.name)
        return self

    @model_validator(mode="after")
    def warn_missing_working_dirs(self) -> "AppConfig":
        """Log warnings for working directories that do not exist."""
        for tool in self.tools:
            if tool.working_dir and not Path(tool.working_dir).is_dir():
                logger.warning("Working directory does not exist: %s", tool.working_dir)
        return self


def load_config(path: str) -> AppConfig:
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated AppConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config file contains invalid data.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML mapping")

    return AppConfig(**raw)


def generate_schema() -> str:
    """Generate JSON Schema for the configuration file.

    Returns:
        JSON string of the configuration schema.
    """
    return json.dumps(AppConfig.model_json_schema(), indent=2)

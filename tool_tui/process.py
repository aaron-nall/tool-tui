# Copyright (c) 2026
"""Async subprocess management for Tool TUI."""

import asyncio
import logging
import shlex
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STOP_TIMEOUT = 5


@dataclass
class OutputLine:
    """A single line of process output.

    Attributes:
        text: The text content of the line.
        is_stderr: Whether this line came from stderr.
        timestamp: Unix timestamp when the line was captured.
    """

    text: str
    is_stderr: bool = False
    timestamp: float = field(default_factory=time.time)


class ToolProcess:
    """Manage an async subprocess for a single tool.

    Handles starting, stopping, and streaming output from a subprocess.
    Output is buffered so it can be replayed when widgets are recreated
    during view switches.

    Attributes:
        name: Display name of the tool.
        command: Shell command string to execute.
        working_dir: Optional working directory for the process.
        output_buffer: All captured output lines.
        queue: Async queue for real-time output streaming to widgets.
    """

    def __init__(self, name: str, command: str, working_dir: str = None) -> None:
        """Initialize a ToolProcess.

        Args:
            name: Display name of the tool.
            command: Shell command string to execute.
            working_dir: Optional working directory for the process.
        """
        self.name = name
        self.command = command
        self.working_dir = working_dir
        self.output_buffer: list[OutputLine] = []
        self.queue: asyncio.Queue[OutputLine | None] = asyncio.Queue()
        self._process: asyncio.subprocess.Process | None = None
        self._read_tasks: list[asyncio.Task] = []
        self._wait_task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        """bool: Whether the subprocess is currently running."""
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Start the subprocess and begin streaming output.

        Raises:
            RuntimeError: If the process is already running.
            OSError: If the command cannot be executed.
        """
        if self.is_running:
            raise RuntimeError(f"Process '{self.name}' is already running")

        # Fresh queue for each run so stale items from prior runs are discarded
        self.queue = asyncio.Queue()

        args = shlex.split(self.command)
        logger.info("Starting process '%s': %s", self.name, args)

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
        )

        self._read_tasks = [
            asyncio.create_task(self._read_stream(self._process.stdout, is_stderr=False)),
            asyncio.create_task(self._read_stream(self._process.stderr, is_stderr=True)),
        ]

        self._wait_task = asyncio.create_task(self._wait_for_exit())

    async def _read_stream(self, stream: asyncio.StreamReader, is_stderr: bool) -> None:
        """Read lines from a stream and push to the output queue.

        Args:
            stream: The async stream reader to read from.
            is_stderr: Whether this stream is stderr.
        """
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n\r")
            output = OutputLine(text=text, is_stderr=is_stderr)
            self.output_buffer.append(output)
            await self.queue.put(output)

    async def _wait_for_exit(self) -> None:
        """Wait for the process to exit and send a sentinel to the queue."""
        if self._process:
            await self._process.wait()
            for task in self._read_tasks:
                await task
            returncode = self._process.returncode
            exit_line = OutputLine(text=f"[Process exited with code {returncode}]", is_stderr=returncode != 0)
            self.output_buffer.append(exit_line)
            await self.queue.put(exit_line)
            await self.queue.put(None)
            logger.info("Process '%s' exited with code %d", self.name, returncode)

    async def stop(self) -> None:
        """Stop the subprocess gracefully, then forcefully if needed."""
        if not self.is_running:
            return

        logger.info("Stopping process '%s'", self.name)
        self._process.terminate()

        try:
            await asyncio.wait_for(self._process.wait(), timeout=STOP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Process '%s' did not terminate, sending SIGKILL", self.name)
            self._process.kill()
            await self._process.wait()

        # Wait for reader tasks to drain, then cancel the wait task
        for task in self._read_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._read_tasks.clear()

        if self._wait_task:
            self._wait_task.cancel()
            try:
                await self._wait_task
            except asyncio.CancelledError:
                pass
            self._wait_task = None

    def clear_buffer(self) -> None:
        """Clear the output buffer."""
        self.output_buffer.clear()

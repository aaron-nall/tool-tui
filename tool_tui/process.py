# Copyright (c) 2026
"""Async subprocess management for Tool TUI."""

import asyncio
import atexit
import logging
import os
import shlex
import signal
import threading
import time
from dataclasses import dataclass, field

import psutil

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


class ProcessManager:
    """Thread-safe registry for all spawned subprocesses.

    Tracks every process spawned via spawn() and ensures full process tree
    cleanup on shutdown using psutil. Registers atexit and signal handlers
    to guarantee cleanup even on unexpected exits.

    Attributes:
        timeout: Seconds to wait after SIGTERM before sending SIGKILL.
    """

    def __init__(self, timeout: float = STOP_TIMEOUT) -> None:
        """Initialize the ProcessManager.

        Args:
            timeout: Seconds to wait for graceful shutdown before SIGKILL.
        """
        self.timeout = timeout
        self._processes: dict[int, asyncio.subprocess.Process] = {}
        self._lock = threading.Lock()
        self._shutdown_called = False
        self._prev_sigterm = None
        self._prev_sigint = None
        self._install_handlers()

    def _install_handlers(self) -> None:
        """Register atexit hook and chain signal handlers for SIGTERM/SIGINT."""
        atexit.register(self.shutdown)

        self._prev_sigterm = signal.getsignal(signal.SIGTERM)
        self._prev_sigint = signal.getsignal(signal.SIGINT)

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle SIGTERM/SIGINT by running shutdown then chaining to previous handler."""
        self.shutdown()

        prev = self._prev_sigterm if signum == signal.SIGTERM else self._prev_sigint
        if callable(prev):
            prev(signum, frame)
        elif prev == signal.SIG_DFL:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

    def register(self, process: asyncio.subprocess.Process) -> None:
        """Add a process to the registry.

        Args:
            process: The asyncio subprocess to track.
        """
        with self._lock:
            self._prune()
            self._processes[process.pid] = process

    def unregister(self, process: asyncio.subprocess.Process) -> None:
        """Remove a process from the registry.

        Args:
            process: The asyncio subprocess to remove.
        """
        with self._lock:
            self._processes.pop(process.pid, None)

    def _prune(self) -> None:
        """Remove dead processes from the registry. Must be called under lock."""
        dead = [pid for pid, p in self._processes.items() if p.returncode is not None]
        for pid in dead:
            del self._processes[pid]

    async def spawn(
        self,
        *args: str,
        cwd: str | None = None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    ) -> asyncio.subprocess.Process:
        """Spawn a subprocess and register it for tracking.

        All processes are started in a new session (start_new_session=True)
        so the entire process tree can be reliably killed.

        Args:
            *args: Command and arguments to execute.
            cwd: Working directory for the subprocess.
            stdout: Stdout pipe configuration.
            stderr: Stderr pipe configuration.

        Returns:
            The spawned asyncio subprocess.
        """
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            start_new_session=True,
        )
        self.register(process)
        logger.debug("Spawned process pid=%d: %s", process.pid, args)
        return process

    @staticmethod
    def kill_tree(pid: int, sig: int = signal.SIGTERM) -> list[int]:
        """Send a signal to a process and all its descendants.

        Args:
            pid: The root process ID.
            sig: The signal to send.

        Returns:
            List of PIDs that were signalled.
        """
        signalled = []
        try:
            parent = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return signalled

        children = []
        try:
            children = parent.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Signal children first (leaves to root), then parent
        for child in reversed(children):
            try:
                child.send_signal(sig)
                signalled.append(child.pid)
                logger.debug("Sent signal %d to child pid=%d", sig, child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        try:
            parent.send_signal(sig)
            signalled.append(parent.pid)
            logger.debug("Sent signal %d to pid=%d", sig, pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return signalled

    def shutdown(self, timeout: float | None = None) -> None:
        """Synchronous shutdown: SIGTERM all trees, wait, then SIGKILL survivors.

        Safe to call from atexit or signal handlers. Idempotent.

        Args:
            timeout: Override the default timeout for graceful shutdown.
        """
        with self._lock:
            if self._shutdown_called:
                return
            self._shutdown_called = True
            pids = list(self._processes.keys())
            self._processes.clear()

        if not pids:
            return

        timeout = timeout if timeout is not None else self.timeout

        logger.debug("ProcessManager shutdown: sending SIGTERM to %d process tree(s)", len(pids))
        for pid in pids:
            self.kill_tree(pid, signal.SIGTERM)

        # Wait for graceful exit
        deadline = time.monotonic() + timeout
        alive = set(pids)
        while alive and time.monotonic() < deadline:
            still_alive = set()
            for pid in alive:
                try:
                    p = psutil.Process(pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        still_alive.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            alive = still_alive
            if alive:
                time.sleep(0.1)

        if alive:
            logger.debug("ProcessManager shutdown: sending SIGKILL to %d survivor(s)", len(alive))
            for pid in alive:
                self.kill_tree(pid, signal.SIGKILL)

    async def async_shutdown(self, timeout: float | None = None) -> None:
        """Async shutdown: SIGTERM all trees, wait, then SIGKILL survivors.

        Preferred when called from an async context (e.g., app quit).

        Args:
            timeout: Override the default timeout for graceful shutdown.
        """
        with self._lock:
            if self._shutdown_called:
                return
            self._shutdown_called = True
            pids = list(self._processes.keys())
            self._processes.clear()

        if not pids:
            return

        timeout = timeout if timeout is not None else self.timeout

        logger.debug("ProcessManager async shutdown: SIGTERM to %d tree(s)", len(pids))
        for pid in pids:
            self.kill_tree(pid, signal.SIGTERM)

        deadline = time.monotonic() + timeout
        alive = set(pids)
        while alive and time.monotonic() < deadline:
            still_alive = set()
            for pid in alive:
                try:
                    p = psutil.Process(pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        still_alive.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            alive = still_alive
            if alive:
                await asyncio.sleep(0.1)

        if alive:
            logger.debug("ProcessManager async shutdown: SIGKILL to %d survivor(s)", len(alive))
            for pid in alive:
                self.kill_tree(pid, signal.SIGKILL)


# Module-level singleton
process_manager = ProcessManager()


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

        self._process = await process_manager.spawn(*args, cwd=self.working_dir)

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
            process_manager.unregister(self._process)

    async def stop(self) -> None:
        """Stop the subprocess gracefully using psutil tree kill."""
        if not self.is_running:
            return

        logger.info("Stopping process '%s' (pid=%d)", self.name, self._process.pid)
        pid = self._process.pid

        # SIGTERM the whole tree
        ProcessManager.kill_tree(pid, signal.SIGTERM)

        try:
            await asyncio.wait_for(self._process.wait(), timeout=STOP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Process '%s' did not terminate, sending SIGKILL to tree", self.name)
            ProcessManager.kill_tree(pid, signal.SIGKILL)
            await self._process.wait()

        process_manager.unregister(self._process)

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

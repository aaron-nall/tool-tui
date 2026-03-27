# Copyright (c) 2026
"""Tests for ProcessManager: spawn, kill_tree, shutdown ordering, SIGKILL fallback."""

import asyncio
import os
import signal

import psutil
import pytest

from tool_tui.process import ProcessManager


@pytest.fixture()
def manager():
    """Create a fresh ProcessManager for each test (no global signal handler side effects)."""
    mgr = ProcessManager(timeout=5)
    yield mgr
    # Ensure cleanup even if test fails
    mgr._shutdown_called = False
    mgr.shutdown(timeout=1)


@pytest.mark.asyncio
async def test_spawn_registers_process(manager):
    """spawn() should register the process and it should be tracked."""
    proc = await manager.spawn("sleep", "60")
    assert proc.pid in manager._processes
    # Cleanup
    proc.kill()
    await proc.wait()


@pytest.mark.asyncio
async def test_spawn_uses_new_session(manager):
    """Spawned processes should run in their own session (pgid != parent pgid)."""
    proc = await manager.spawn("sleep", "60")
    try:
        ps = psutil.Process(proc.pid)
        # Process should be its own session leader
        assert ps.pid == os.getpgid(proc.pid)
    finally:
        proc.kill()
        await proc.wait()


@pytest.mark.asyncio
async def test_spawn_tracks_stdout(manager):
    """spawn() should pipe stdout correctly."""
    proc = await manager.spawn("echo", "hello")
    stdout, _ = await proc.communicate()
    assert b"hello" in stdout


@pytest.mark.asyncio
async def test_unregister_removes_process(manager):
    """unregister() should remove the process from tracking."""
    proc = await manager.spawn("sleep", "60")
    manager.unregister(proc)
    assert proc.pid not in manager._processes
    proc.kill()
    await proc.wait()


@pytest.mark.asyncio
async def test_kill_tree_terminates_children(manager):
    """kill_tree() should terminate a process and its children."""
    # Spawn a shell that spawns a child
    proc = await manager.spawn("sh", "-c", "sleep 300 & sleep 300")
    await asyncio.sleep(0.3)  # Let children spawn

    ps_parent = psutil.Process(proc.pid)
    children = ps_parent.children(recursive=True)
    all_pids = [proc.pid] + [c.pid for c in children]
    assert len(children) >= 1, "Expected at least one child process"

    ProcessManager.kill_tree(proc.pid, signal.SIGKILL)
    await asyncio.sleep(0.5)

    for pid in all_pids:
        assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
async def test_kill_tree_nonexistent_pid():
    """kill_tree() should handle non-existent PIDs gracefully."""
    result = ProcessManager.kill_tree(999999999, signal.SIGTERM)
    assert result == []


@pytest.mark.asyncio
async def test_shutdown_sigterm_then_sigkill(manager):
    """shutdown() should SIGTERM first, then SIGKILL after timeout."""
    # Spawn a process that ignores SIGTERM
    proc = await manager.spawn("sh", "-c", "trap '' TERM; sleep 300")
    await asyncio.sleep(0.3)
    pid = proc.pid

    # Short timeout so SIGKILL fires quickly
    manager.timeout = 1
    manager.shutdown(timeout=1)

    await asyncio.sleep(0.5)
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
async def test_shutdown_graceful_exit(manager):
    """shutdown() should cleanly terminate processes that handle SIGTERM."""
    proc = await manager.spawn("sleep", "300")
    pid = proc.pid

    manager.shutdown(timeout=5)
    await asyncio.sleep(0.5)

    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
async def test_shutdown_idempotent(manager):
    """Calling shutdown() multiple times should be safe."""
    proc = await manager.spawn("sleep", "60")
    proc.kill()
    await proc.wait()

    manager.shutdown()
    manager.shutdown()  # Should not raise


@pytest.mark.asyncio
async def test_async_shutdown(manager):
    """async_shutdown() should clean up all tracked processes."""
    proc = await manager.spawn("sleep", "300")
    pid = proc.pid

    await manager.async_shutdown(timeout=5)
    await asyncio.sleep(0.5)

    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
async def test_prune_removes_dead_processes(manager):
    """Dead processes should be pruned from registry on next register."""
    proc = await manager.spawn("true")
    await proc.wait()  # Let it exit

    # Spawn another to trigger prune
    proc2 = await manager.spawn("sleep", "60")
    assert proc.pid not in manager._processes
    proc2.kill()
    await proc2.wait()

"""Tests for process_utils module."""
import asyncio
import os
import signal
import time

import pytest

from server.process_utils import kill_process, kill_process_group, kill_process_safely


@pytest.mark.asyncio
async def test_kill_process_already_terminated() -> None:
    """Test that killing an already-terminated process is safe (idempotent)."""
    # Create a process that exits immediately
    proc = await asyncio.create_subprocess_exec("true")
    await proc.wait()
    assert proc.returncode == 0

    # Should not raise an error
    await kill_process(proc, timeout=1.0)


@pytest.mark.asyncio
async def test_kill_process_group_already_terminated() -> None:
    """Test that killing an already-terminated process group is safe."""
    proc = await asyncio.create_subprocess_exec("true")
    await proc.wait()
    assert proc.returncode == 0

    # Should not raise an error
    await kill_process_group(proc, timeout=1.0)


@pytest.mark.asyncio
async def test_kill_process_safely_already_terminated() -> None:
    """Test that kill_process_safely is idempotent for terminated processes."""
    proc = await asyncio.create_subprocess_exec("true")
    await proc.wait()

    # Should not raise an error
    await kill_process_safely(proc, use_process_group=True, timeout=1.0)


@pytest.mark.asyncio
async def test_kill_process_actually_kills() -> None:
    """Test that kill_process actually terminates a running process."""
    # Create a process that sleeps for a long time
    proc = await asyncio.create_subprocess_exec("sleep", "60")

    try:
        # Kill it
        await kill_process(proc, timeout=2.0)

        # Process should be terminated
        assert proc.returncode is not None
        assert proc.returncode != 0  # Killed processes typically have non-zero return code
    finally:
        # Cleanup in case test fails
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_kill_process_group_actually_kills() -> None:
    """Test that kill_process_group terminates a process group."""
    # Create a process that creates a process group (using setsid via shell)
    # Note: We use sh -c to create a process that will be in its own process group
    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        "sleep 60",
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )

    try:
        # Kill it
        await kill_process_group(proc, timeout=2.0)

        # Process should be terminated
        assert proc.returncode is not None
        assert proc.returncode != 0
    finally:
        # Cleanup in case test fails
        if proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                await proc.wait()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_kill_process_safely_with_process_group() -> None:
    """Test kill_process_safely with use_process_group=True."""
    proc = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        "sleep 60",
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )

    try:
        await kill_process_safely(proc, use_process_group=True, timeout=2.0)
        assert proc.returncode is not None
    finally:
        if proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                await proc.wait()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_kill_process_safely_without_process_group() -> None:
    """Test kill_process_safely with use_process_group=False."""
    proc = await asyncio.create_subprocess_exec("sleep", "60")

    try:
        await kill_process_safely(proc, use_process_group=False, timeout=2.0)
        assert proc.returncode is not None
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_kill_process_timeout() -> None:
    """Test that kill_process respects timeout."""
    # This test is hard to make deterministic, but we can at least verify
    # the function doesn't hang forever
    proc = await asyncio.create_subprocess_exec("sleep", "60")

    start_time = time.time()
    try:
        # Use a short timeout
        await kill_process(proc, timeout=0.1)
        elapsed = time.time() - start_time

        # Should complete quickly (though process might not be fully killed)
        assert elapsed < 2.0
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_kill_process_safely_idempotent() -> None:
    """Test that kill_process_safely is idempotent (safe to call multiple times)."""
    proc = await asyncio.create_subprocess_exec("sleep", "60")

    try:
        # Call multiple times
        await kill_process_safely(proc, use_process_group=False, timeout=2.0)
        await kill_process_safely(proc, use_process_group=False, timeout=2.0)
        await kill_process_safely(proc, use_process_group=False, timeout=2.0)

        # Should not raise errors and process should be killed
        assert proc.returncode is not None
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass



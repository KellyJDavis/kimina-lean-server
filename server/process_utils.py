"""
Process management utilities for reliable process termination.

This module provides functions for safely killing processes and process groups,
which is essential for handling timeouts in REPL and AST export operations.
"""
import asyncio
import os
import signal
from asyncio.subprocess import Process
from typing import Any

from loguru import logger


async def kill_process_group(
    proc: Process,
    timeout: float = 5.0,
    logger_instance: Any | None = None,
) -> None:
    """
    Kill a process and its entire process group using SIGKILL.

    This is more reliable than proc.kill() because it kills child processes
    (e.g., when using 'lake env', the lake process and its repl child).

    Args:
        proc: The asyncio subprocess Process to kill
        timeout: Maximum time to wait for process termination (seconds)
        logger_instance: Optional logger instance for logging operations

    Raises:
        ProcessLookupError: If process is already dead (this is handled gracefully)
        PermissionError: If we don't have permission to kill the process group
    """
    log = logger_instance if logger_instance is not None else logger

    if proc.returncode is not None:
        log.debug(f"Process {proc.pid} already terminated (returncode={proc.returncode})")
        return

    try:
        pgid = os.getpgid(proc.pid)
        log.debug(f"Killing process group {pgid} (process {proc.pid})")
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        # Process already dead
        log.debug(f"Process {proc.pid} not found, may already be terminated")
        return
    except PermissionError:
        log.warning(
            f"Permission denied killing process group for {proc.pid}, "
            "falling back to process kill"
        )
        # Fall back to killing just the process
        try:
            proc.kill()
        except ProcessLookupError:
            log.debug(f"Process {proc.pid} not found during fallback kill")
            return
        except Exception as e:
            log.error(f"Error during fallback process kill: {e}")
            raise

    # Wait for process termination with timeout
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        log.debug(f"Process {proc.pid} terminated successfully")
    except asyncio.TimeoutError:
        log.warning(f"Process {proc.pid} did not terminate within {timeout}s after SIGKILL")
    except ProcessLookupError:
        # Process already terminated
        log.debug(f"Process {proc.pid} already terminated")
    except Exception as e:
        log.error(f"Error waiting for process {proc.pid} termination: {e}")


async def kill_process(
    proc: Process,
    timeout: float = 5.0,
    logger_instance: Any | None = None,
) -> None:
    """
    Kill a single process using SIGKILL (does not kill process group).

    This is a fallback for processes that don't have process groups or
    when process group kill fails.

    Args:
        proc: The asyncio subprocess Process to kill
        timeout: Maximum time to wait for process termination (seconds)
        logger_instance: Optional logger instance for logging operations
    """
    log = logger_instance if logger_instance is not None else logger

    if proc.returncode is not None:
        log.debug(f"Process {proc.pid} already terminated (returncode={proc.returncode})")
        return

    try:
        log.debug(f"Killing process {proc.pid}")
        proc.kill()
    except ProcessLookupError:
        # Process already dead
        log.debug(f"Process {proc.pid} not found, may already be terminated")
        return
    except Exception as e:
        log.error(f"Error killing process {proc.pid}: {e}")
        raise

    # Wait for process termination with timeout
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        log.debug(f"Process {proc.pid} terminated successfully")
    except asyncio.TimeoutError:
        log.warning(f"Process {proc.pid} did not terminate within {timeout}s after SIGKILL")
    except ProcessLookupError:
        # Process already terminated
        log.debug(f"Process {proc.pid} already terminated")
    except Exception as e:
        log.error(f"Error waiting for process {proc.pid} termination: {e}")


async def kill_process_safely(
    proc: Process,
    use_process_group: bool = True,
    timeout: float = 5.0,
    logger_instance: Any | None = None,
) -> None:
    """
    Safely kill a process, trying process group kill first, then falling back to process kill.

    This is the recommended function to use for killing processes, as it handles
    both process groups (like REPL processes using 'lake env') and single processes.

    Args:
        proc: The asyncio subprocess Process to kill
        use_process_group: If True, try to kill process group first (default: True)
        timeout: Maximum time to wait for process termination (seconds)
        logger_instance: Optional logger instance for logging operations

    This function is idempotent - safe to call multiple times.
    """
    if proc.returncode is not None:
        # Process already terminated
        return

    if use_process_group:
        try:
            await kill_process_group(proc, timeout=timeout, logger_instance=logger_instance)
            return
        except Exception as e:
            log = logger_instance if logger_instance is not None else logger
            log.warning(
                f"Process group kill failed for {proc.pid}, "
                f"falling back to process kill: {e}"
            )
            # Fall through to process kill

    # Fallback to single process kill
    await kill_process(proc, timeout=timeout, logger_instance=logger_instance)



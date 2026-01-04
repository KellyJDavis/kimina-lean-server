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


def _get_safe_process_group(proc: Process, logger_instance: Any | None = None) -> int | None:
    """
    Safely get the process group ID for a process, with verification.

    This function verifies that:
    1. The process group exists
    2. The process group is not the parent process group (to avoid killing test runners/shells)
    3. The process is actually in that process group

    Returns the process group ID if safe to kill, None otherwise.

    Args:
        proc: The asyncio subprocess Process
        logger_instance: Optional logger instance for logging operations

    Returns:
        Process group ID if safe to kill, None if we should fall back to process kill
    """
    log = logger_instance if logger_instance is not None else logger

    try:
        # Get the process group ID
        pgid = os.getpgid(proc.pid)

        # Safety check: Don't kill the parent process group
        # The parent process group is typically the shell/test runner
        # REPL processes use os.setsid() to create a new process group,
        # so their pgid should equal their pid (they're the group leader)
        parent_pgid = os.getpgid(os.getppid())
        if pgid == parent_pgid:
            log.warning(
                f"Process {proc.pid} is in parent process group {pgid}. "
                "This would kill the parent process. Falling back to process kill."
            )
            return None

        # Additional safety: On Unix systems, if the process is the group leader,
        # its pgid should equal its pid. If not, be cautious.
        # However, we allow killing if pgid != pid because the process might
        # have been started in a different group intentionally.
        # The key check is that we don't kill the parent group.

        log.debug(f"Process group {pgid} verified safe to kill (process {proc.pid})")
        return pgid

    except ProcessLookupError:
        # Process already dead
        log.debug(f"Process {proc.pid} not found, may already be terminated")
        return None
    except OSError as e:
        log.warning(
            f"Error getting process group for {proc.pid}: {e}. "
            "Falling back to process kill."
        )
        return None


async def kill_process_group(
    proc: Process,
    timeout: float = 5.0,
    logger_instance: Any | None = None,
) -> None:
    """
    Kill a process and its entire process group using SIGKILL.

    This is more reliable than proc.kill() because it kills child processes
    (e.g., when using 'lake env', the lake process and its repl child).

    This function includes safety checks to ensure we don't accidentally kill
    the parent process group (which could kill test runners or shells).

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

    # Get the process group ID with safety checks
    pgid = _get_safe_process_group(proc, logger_instance)
    
    if pgid is None:
        # Safety checks failed, fall back to process kill
        log.debug(
            f"Process group kill not safe for {proc.pid}, "
            "falling back to process kill"
        )
        try:
            proc.kill()
        except ProcessLookupError:
            log.debug(f"Process {proc.pid} not found during fallback kill")
            return
        except Exception as e:
            log.error(f"Error during fallback process kill: {e}")
            raise
    else:
        # Safe to kill the process group
        try:
            log.debug(f"Killing process group {pgid} (process {proc.pid})")
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            # Process group already dead
            log.debug(f"Process group {pgid} not found, may already be terminated")
            return
        except PermissionError:
            log.warning(
                f"Permission denied killing process group {pgid} for {proc.pid}, "
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



"""Tests for Manager handling of killed REPLs."""
import asyncio
import pytest

from server.manager import Manager


@pytest.mark.asyncio
async def test_manager_release_killed_repl_destroys_instead() -> None:
    """Test that releasing a killed REPL destroys it instead of adding to free pool."""
    manager = Manager(max_repls=2, max_repl_uses=1, max_repl_mem=8192, init_repls={})

    try:
        # Create and start a REPL
        repl = await manager.start_new("")
        await manager.prep(repl, "test", timeout=10.0, debug=False)

        # Mark it as busy (simulate it being used)
        async with manager._cond:
            manager._busy.add(repl)

        # Kill the REPL
        await repl.kill_immediately()
        assert not repl.is_running

        # Release it - should destroy instead of releasing
        await manager.release_repl(repl)

        # REPL should not be in free pool
        async with manager._cond:
            assert repl not in manager._free
            assert repl not in manager._busy

        # Wait a bit for cleanup
        await asyncio.sleep(0.5)
    finally:
        await manager.cleanup()


@pytest.mark.asyncio
async def test_manager_get_repl_skips_killed_repls() -> None:
    """Test that get_repl skips killed REPLs when looking for reusable ones."""
    manager = Manager(max_repls=2, max_repl_uses=1, max_repl_mem=8192, init_repls={})

    try:
        # Create and start a REPL
        repl = await manager.start_new("")
        await manager.prep(repl, "test", timeout=10.0, debug=False)

        # Release it to free pool
        async with manager._cond:
            manager._busy.remove(repl)
            manager._free.append(repl)

        # Kill the REPL
        await repl.kill_immediately()
        assert not repl.is_running

        # Try to get a REPL - should create a new one, not reuse the killed one
        new_repl = await manager.get_repl("", "test2", timeout=10.0, reuse=True)

        # Should be a different REPL (and not killed)
        assert new_repl.uuid != repl.uuid
        assert not new_repl.is_killed

        # Wait a bit for cleanup
        await asyncio.sleep(0.5)
    finally:
        await manager.cleanup()


@pytest.mark.asyncio
async def test_manager_destroy_repl_handles_killed_repl() -> None:
    """Test that destroy_repl handles already-killed REPLs gracefully."""
    manager = Manager(max_repls=2, max_repl_uses=1, max_repl_mem=8192, init_repls={})

    try:
        # Create and start a REPL
        repl = await manager.start_new("")
        await manager.prep(repl, "test", timeout=10.0, debug=False)

        # Mark as busy
        async with manager._cond:
            manager._busy.add(repl)

        # Kill it
        await repl.kill_immediately()

        # destroy_repl should not raise errors
        await manager.destroy_repl(repl)

        # REPL should be removed from both sets
        async with manager._cond:
            assert repl not in manager._free
            assert repl not in manager._busy

        # Wait for cleanup
        await asyncio.sleep(0.5)
    finally:
        await manager.cleanup()


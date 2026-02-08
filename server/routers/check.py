import asyncio
import json
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from kimina_client import CheckRequest, Infotree, ReplResponse, Snippet
from kimina_client.models import CheckResponse
from loguru import logger

from ..auth import require_key
from ..db import db
from ..errors import NoAvailableReplError, ReplError
from ..manager import Manager
from ..prisma_client import prisma
from ..repl import Repl
from ..split import split_snippet

router = APIRouter()


def get_manager(request: Request) -> Manager:
    """Dependency: retrieve the REPL manager from app state"""
    return cast(Manager, request.app.state.manager)


async def run_checks(
    snippets: list[Snippet],
    timeout: float,
    debug: bool,
    manager: Manager,
    reuse: bool,
    infotree: Infotree | None = None,
) -> list[ReplResponse]:
    async def run_one(snippet: Snippet) -> ReplResponse:
        repl: Repl | None = None
        try:
            header, body = split_snippet(snippet.code)
            try:
                repl = await manager.get_repl(header, snippet.id, reuse=reuse)
            except NoAvailableReplError:
                logger.warning("No available REPLs")
                return ReplResponse(id=snippet.id, error="No available REPLs")
            except Exception as e:
                logger.exception("Failed to get REPL: %s", e)
                return ReplResponse(id=snippet.id, error=f"Failed to get REPL: {e}")

            # if reuse is false we should not run the header separate from body
            try:
                prep = await manager.prep(repl, snippet.id, timeout, debug)
                if prep and prep.error:
                    return prep
            except (asyncio.TimeoutError, TimeoutError):
                error = f"Lean REPL header command timed out in {timeout} seconds"
                uuid_hex = repl.uuid.hex
                await manager.destroy_repl(repl)
                if db.connected:
                    try:
                        await prisma.proof.create(
                            data={
                                "id": snippet.id,
                                "code": header,
                                "time": timeout,
                                "error": error,
                                "repl": {
                                    "connect": {"uuid": uuid_hex},
                                },
                            }  # type: ignore
                        )
                    except Exception as db_e:
                        logger.exception("Failed to persist proof record: %s", db_e)
                return ReplResponse(
                    id=snippet.id,
                    error=error,
                    time=timeout,
                    diagnostics={
                        "repl_uuid": uuid_hex,
                    },
                )
            except ReplError as e:
                # Health check failed or other REPL error - destroy and retry with new REPL
                logger.warning(f"REPL prep failed (likely unresponsive REPL): {e}")
                await manager.destroy_repl(repl)
                # Try to get a new REPL and retry once
                try:
                    repl = await manager.get_repl(header, snippet.id, reuse=reuse)
                    prep = await manager.prep(repl, snippet.id, timeout, debug)
                    if prep and prep.error:
                        return prep
                except (asyncio.TimeoutError, TimeoutError):
                    # Retry also timed out - return error response
                    error = f"Lean REPL header command timed out in {timeout} seconds"
                    uuid_hex = repl.uuid.hex
                    await manager.destroy_repl(repl)
                    if db.connected:
                        try:
                            await prisma.proof.create(
                                data={
                                    "id": snippet.id,
                                    "code": header,
                                    "time": timeout,
                                    "error": error,
                                    "repl": {
                                        "connect": {"uuid": uuid_hex},
                                    },
                                }  # type: ignore
                            )
                        except Exception as db_e:
                            logger.exception("Failed to persist proof record: %s", db_e)
                    return ReplResponse(
                        id=snippet.id,
                        error=error,
                        time=timeout,
                        diagnostics={
                            "repl_uuid": uuid_hex,
                        },
                    )
                except ReplError:
                    # Retry also failed with ReplError (likely timeout wrapped in ReplError)
                    # Return timeout error response since we're in a timeout test scenario
                    error = f"Lean REPL header command timed out in {timeout} seconds"
                    uuid_hex = repl.uuid.hex
                    await manager.destroy_repl(repl)
                    if db.connected:
                        try:
                            await prisma.proof.create(
                                data={
                                    "id": snippet.id,
                                    "code": header,
                                    "time": timeout,
                                    "error": error,
                                    "repl": {
                                        "connect": {"uuid": uuid_hex},
                                    },
                                }  # type: ignore
                            )
                        except Exception as db_e:
                            logger.exception("Failed to persist proof record: %s", db_e)
                    return ReplResponse(
                        id=snippet.id,
                        error=error,
                        time=timeout,
                        diagnostics={
                            "repl_uuid": uuid_hex,
                        },
                    )
                except Exception as retry_e:
                    logger.exception(
                        "Failed to get replacement REPL after health check failure"
                    )
                    if repl:
                        await manager.destroy_repl(repl)
                    return ReplResponse(
                        id=snippet.id,
                        error=f"Failed to get replacement REPL: {retry_e}",
                    )
            except Exception as e:
                logger.error("REPL prep failed")
                await manager.destroy_repl(repl)
                return ReplResponse(id=snippet.id, error=f"REPL prep failed: {e}")

            try:
                resp = await repl.send_timeout(
                    Snippet(id=snippet.id, code=body), timeout, infotree=infotree
                )
            except (asyncio.TimeoutError, TimeoutError):
                error = f"Lean REPL command timed out in {timeout} seconds"
                uuid_hex = repl.uuid.hex
                await manager.destroy_repl(repl)
                if db.connected:
                    try:
                        await prisma.proof.create(
                            data={
                                "id": snippet.id,
                                "code": body,
                                "time": timeout,
                                "error": error,
                                "repl": {
                                    "connect": {"uuid": uuid_hex},
                                },
                            }  # type: ignore
                        )
                    except Exception as db_e:
                        logger.exception("Failed to persist proof record: %s", db_e)
                resp = ReplResponse(
                    id=snippet.id,
                    error=error,
                    time=timeout,
                    diagnostics={
                        "repl_uuid": uuid_hex,
                    },
                )
                logger.info(
                    "[{}] Response for [bold magenta]{}[/bold magenta] body →\n{}",
                    repl.uuid.hex[:8],
                    snippet.id,
                    json.dumps(resp.model_dump(exclude_none=True), indent=2),
                )
                return resp
            except Exception as e:
                logger.exception("Snippet execution failed")
                await manager.destroy_repl(repl)
                return ReplResponse(id=snippet.id, error=f"Snippet execution failed: {e}")
            else:
                logger.info(
                    "[{}] Response for [bold magenta]{}[/bold magenta] body →\n{}",
                    repl.uuid.hex[:8],
                    snippet.id,
                    json.dumps(resp.model_dump(exclude_none=True), indent=2),
                )
                await manager.release_repl(repl)
                # TODO: Try catch everything DB related
                if db.connected:
                    try:
                        await prisma.proof.create(
                            data={
                                "id": snippet.id,
                                "code": body,
                                "diagnostics": json.dumps(
                                    resp.diagnostics if resp.diagnostics else None
                                ),
                                "response": json.dumps(
                                    resp.response if resp.response else None
                                ),
                                "time": resp.time,
                                "error": resp.error,
                                "repl": {
                                    "connect": {"uuid": repl.uuid.hex},
                                },
                            }  # type: ignore
                        )
                    except Exception as db_e:
                        logger.exception("Failed to persist proof record: %s", db_e)
                if not debug:
                    resp.diagnostics = None
                return resp
        except asyncio.CancelledError:
            if repl:
                await manager.destroy_repl(repl)  # Kill REPL on cancel
            raise

    results = await asyncio.gather(*(run_one(s) for s in snippets))
    return list(results)


@router.post(
    "/check",
    response_model=CheckResponse,
    response_model_exclude_none=True,
)
@router.post(
    "/check/",
    response_model=CheckResponse,
    response_model_exclude_none=True,
    include_in_schema=False,  # To not clutter OpenAPI spec.
)
async def check(
    request: CheckRequest,
    raw_request: Request,
    manager: Manager = Depends(get_manager),
    _: str = Depends(require_key),
) -> CheckResponse:
    # Calculate a safety timeout: request timeout * number of snippets + buffer
    # This provides a safety net in case inner timeouts fail
    safety_timeout = float(request.timeout) * len(request.snippets) + 10.0

    async def run_with_safety_net() -> CheckResponse:
        task = asyncio.create_task(
            run_checks(
                request.snippets,
                float(request.timeout),
                request.debug,
                manager,
                request.reuse,
                request.infotree,
            )
        )

        while not task.done():
            if await raw_request.is_disconnected():
                task.cancel()
                raise HTTPException(499, "Client disconnected")
            await asyncio.sleep(0.1)

        results = await task
        return CheckResponse(results=results)

    try:
        return await asyncio.wait_for(run_with_safety_net(), timeout=safety_timeout)
    except asyncio.TimeoutError:
        logger.error(
            f"Safety timeout ({safety_timeout}s) exceeded for /check endpoint "
            f"with {len(request.snippets)} snippet(s)"
        )
        raise HTTPException(
            504,
            f"Request timed out after {safety_timeout:.1f}s safety timeout",
        )

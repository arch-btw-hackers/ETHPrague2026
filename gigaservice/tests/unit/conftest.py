"""
Unit-test-specific fixtures for storage/swarm.py tests.

Provides a real httpx.AsyncClient as the global swarm client so the
swarm functions can make (respx-intercepted) HTTP calls without touching
a real Bee node.
"""
import pytest
import httpx
import storage.swarm as swarm_mod


@pytest.fixture(autouse=True)
async def swarm_http_client():
    """
    Set up a real AsyncClient as the global swarm HTTP client.
    respx.mock (used per-test) intercepts all requests at the transport level,
    so this client never actually dials out.
    """
    async with httpx.AsyncClient() as client:
        swarm_mod.set_http_client(client)
        yield client
    swarm_mod._http_client = None

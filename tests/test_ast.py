import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client",
    [
        {"database_url": None},
    ],
    indirect=True,
)
async def test_ast_module_mathlib(client: TestClient) -> None:
    resp = client.post(
        "ast",
        json={
            "modules": ["Mathlib"],
            "one": True,
            "timeout": 60,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data and len(data["results"]) == 1
    assert data["results"][0]["module"] == "Mathlib"
    assert data["results"][0].get("error") is None
    assert isinstance(data["results"][0].get("ast"), dict)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client",
    [
        {"database_url": None},
    ],
    indirect=True,
)
async def test_ast_code_simple(client: TestClient) -> None:
    resp = client.post(
        "ast_code",
        json={
            "code": "import Mathlib\n#check Nat",
            "module": "User.Code",
            "timeout": 60,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data and len(data["results"]) == 1
    assert data["results"][0]["module"] == "User.Code"
    assert data["results"][0].get("error") is None
    assert isinstance(data["results"][0].get("ast"), dict)



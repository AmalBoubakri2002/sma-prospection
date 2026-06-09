import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "amal@example.com",
        "password": "secret123",
        "full_name": "Amal B.",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "amal@example.com"
    assert data["role"] == "commercial"
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "secret123"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "amal@example.com",
        "password": "secret123",
    })
    resp = await client.post("/api/v1/auth/token", data={
        "username": "amal@example.com",
        "password": "secret123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "amal@example.com",
        "password": "secret123",
    })
    resp = await client.post("/api/v1/auth/token", data={
        "username": "amal@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    resp = await client.post("/api/v1/auth/token", data={
        "username": "nobody@example.com",
        "password": "whatever",
    })
    assert resp.status_code == 401


async def test_get_me(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "amal@example.com",
        "password": "secret123",
        "full_name": "Amal B.",
    })
    token_resp = await client.post("/api/v1/auth/token", data={
        "username": "amal@example.com",
        "password": "secret123",
    })
    token = token_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "amal@example.com"
    assert data["full_name"] == "Amal B."


async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401

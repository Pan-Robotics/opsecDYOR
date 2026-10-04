"""Access-token verification for the CryptoOpsec Accounts cookie (offline, ES256)."""

import time
from typing import Annotated

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from dyor.api import auth as auth_mod
from dyor.config import get_settings


class _Key:
    def __init__(self, key):
        self.key = key


class _FakeJwks:
    def __init__(self, pub, kid):
        self.pub, self.kid = pub, kid

    def get_signing_key_from_jwt(self, token):
        if jwt.get_unverified_header(token).get("kid") != self.kid:
            raise jwt.PyJWKClientError("unknown kid")
        return _Key(self.pub)


@pytest.fixture
def signer(monkeypatch):
    priv = ec.generate_private_key(ec.SECP256R1())
    fake = _FakeJwks(priv.public_key(), "k1")
    monkeypatch.setattr(auth_mod, "_jwks_client", lambda fresh=False: fake)
    s = get_settings()

    def sign(**over):
        now = int(time.time())
        claims = {"iss": s.accounts_issuer, "aud": s.accounts_audience, "sub": "u-1", "sid": "s-1",
                  "hdl": "satoshi", "plan": "free", "feat": [], "iat": now, "exp": now + 600}
        claims.update(over)
        return jwt.encode(claims, priv, algorithm="ES256", headers={"kid": over.pop("kid", "k1")})
    return sign


def test_valid_token_yields_principal(signer):
    p = auth_mod.principal_from_claims(auth_mod.decode_token(signer()))
    assert p.id == "u-1" and p.handle == "satoshi" and p.plan == "free" and not p.has("mcp")
    pro = auth_mod.principal_from_claims(auth_mod.decode_token(signer(plan="pro", feat=["mcp", "api_keys"])))
    assert pro.has("mcp")


def test_expired_wrong_audience_wrong_issuer_rejected(signer):
    with pytest.raises(jwt.ExpiredSignatureError):
        auth_mod.decode_token(signer(exp=int(time.time()) - 120))
    with pytest.raises(jwt.PyJWTError):
        auth_mod.decode_token(signer(aud="someone-else"))
    with pytest.raises(jwt.PyJWTError):
        auth_mod.decode_token(signer(iss="https://evil.example"))


def test_api_me_reads_cookie_and_bearer(signer):
    from dyor.api.app import app
    client = TestClient(app)
    s = get_settings()
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json()["detail"]["reason"] == "missing"
    r = client.get("/api/me", headers={"Cookie": f"{s.accounts_cookie}={signer()}"})
    assert r.status_code == 200 and r.json()["user"]["handle"] == "satoshi"
    r = client.get("/api/me", headers={"Authorization": f"Bearer {signer(hdl='vitalik')}"})
    assert r.status_code == 200 and r.json()["user"]["handle"] == "vitalik"
    r = client.get("/api/me", headers={"Cookie": f"{s.accounts_cookie}={signer(exp=int(time.time()) - 120)}"})
    assert r.status_code == 401 and r.json()["detail"]["reason"] == "expired"
    r = client.get("/api/me", headers={"Cookie": f"{s.accounts_cookie}=garbage"})
    assert r.status_code == 401 and r.json()["detail"]["reason"] == "invalid"


def test_require_feature_gates_by_plan(signer):
    from fastapi import Depends, FastAPI
    gated = FastAPI()

    needs_mcp = auth_mod.require_feature("mcp")

    @gated.get("/pro")
    def pro(user: Annotated[auth_mod.Principal, Depends(needs_mcp)]):
        return {"ok": True, "handle": user.handle}

    c = TestClient(gated)
    s = get_settings()
    assert c.get("/pro").status_code == 401
    assert c.get("/pro", headers={"Cookie": f"{s.accounts_cookie}={signer()}"}).status_code == 402
    assert c.get("/pro", headers={"Cookie": f"{s.accounts_cookie}={signer(plan='pro', feat=['mcp'])}"}).json()["ok"] is True

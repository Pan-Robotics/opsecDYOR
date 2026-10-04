"""Who is calling: verification of the CryptoOpsec Accounts access token.

accounts.cryptoopsec.com signs a short-lived ES256 JWT into the ``__Secure-cos_at``
cookie for ``.cryptoopsec.com``; API clients may also send it as a bearer token.
Verification is offline against the service's published JWKS (cached, refetched
when a token names a key we do not hold, which is what a rotation looks like).

Dependencies:
  optional_user   -> Principal | None   (anonymous is fine; most of DYOR is free)
  require_user    -> Principal          (401 otherwise)
  require_feature -> Principal          (402 unless the plan unlocks the feature)

Nothing here is wired to gate the free surface. The paid tier will put
``Depends(require_feature("mcp"))`` (and friends) on the endpoints it covers.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request

from dyor.config import get_settings

ALGORITHMS = ["ES256"]


@dataclass(frozen=True)
class Principal:
    id: str
    session: str
    handle: str
    plan: str
    features: tuple[str, ...] = ()
    claims: dict[str, Any] = field(default_factory=dict, repr=False)

    def has(self, feature: str) -> bool:
        return feature in self.features

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "handle": self.handle, "plan": self.plan, "features": list(self.features)}


_lock = threading.Lock()
_client: jwt.PyJWKClient | None = None


def _jwks_client(fresh: bool = False) -> jwt.PyJWKClient:
    global _client
    with _lock:
        if _client is None or fresh:
            s = get_settings()
            _client = jwt.PyJWKClient(f"{s.accounts_issuer}/.well-known/jwks.json", cache_keys=True, lifespan=600)
        return _client


def decode_token(token: str) -> dict[str, Any]:
    """Verified claims, or a PyJWTError. A key we do not know triggers one JWKS refetch."""
    s = get_settings()
    try:
        key = _jwks_client().get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError:
        key = _jwks_client(fresh=True).get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=ALGORITHMS, audience=s.accounts_audience, issuer=s.accounts_issuer, leeway=30)


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    feats = claims.get("feat") or []
    return Principal(
        id=str(claims["sub"]), session=str(claims.get("sid", "")), handle=str(claims.get("hdl", "")),
        plan=str(claims.get("plan", "free")), features=tuple(str(f) for f in feats), claims=claims,
    )


def token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(get_settings().accounts_cookie)


def classify(request: Request) -> tuple[Principal | None, str]:
    """(principal, reason) where reason is ok | missing | expired | invalid."""
    token = token_from_request(request)
    if not token:
        return None, "missing"
    try:
        return principal_from_claims(decode_token(token)), "ok"
    except jwt.ExpiredSignatureError:
        return None, "expired"
    except (jwt.PyJWTError, KeyError, ValueError):
        return None, "invalid"


async def optional_user(request: Request) -> Principal | None:
    user, _ = classify(request)
    return user


async def require_user(request: Request) -> Principal:
    user, reason = classify(request)
    if user is None:
        raise HTTPException(status_code=401, detail={"error": "sign in required", "reason": reason,
                                                     "login": f"{get_settings().accounts_issuer}/login"})
    return user


def require_feature(name: str):
    async def dep(user: Annotated[Principal, Depends(require_user)]) -> Principal:
        if not user.has(name):
            raise HTTPException(status_code=402, detail={"error": f"the {name} feature needs a paid plan", "plan": user.plan})
        return user
    return dep

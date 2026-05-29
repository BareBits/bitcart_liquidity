"""Verify that every wallet-debug + log-export endpoint is gated on
the same `server_management` scope as the rest of the plugin.

The plugin's dashboard Vue page is gated client-side on
$auth.user.is_superuser (admin/.../pages/index.vue:1316). But the
client-side gate is UX, not security — anyone who knows the endpoint
URLs could hit them directly. These tests pin the SERVER-side gate
so a refactor that drops the Security dependency from one of the
routes triggers a red test instead of silently shipping a leak.

Two layers of coverage:

  1. Static introspection (test_routes_declare_server_management_scope):
     walks every route on both routers and asserts a Security
     dependency carrying the "server_management" scope is attached.
     Catches "forgot to add `dependencies=deps`" regressions
     immediately at collection time without needing to round-trip
     through HTTP.

  2. Live TestClient (the per-endpoint tests below): mounts the
     routers behind a stub auth_dependency that mimics Bitcart's
     real AuthDependency behavior (401 on no token / unknown token,
     403 on insufficient scope or non-superuser, 200 on superuser
     with the right scope). Hits every endpoint with each scenario
     and pins the rejection status. Catches "Security present but
     wrong scope" or "scope present but dep wired incorrectly"
     regressions that pure introspection would miss.

NOT exercised here:
  - Bitcart's own AuthDependency internals (token decoding, DB
    lookup, hook firing). Those belong with bitcart_fork, not the
    plugin.
  - The Vue client-side gate. Verified separately via the audit;
    no clean way to integration-test a Nuxt page guard from pytest
    without spinning up the whole admin server.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.params import Security
from fastapi.security import SecurityScopes
from fastapi.testclient import TestClient

from bitcart_plugin import log_export, wallet_debug


# ---------------------------------------------------------------------------
# Stub auth dependency — mimics Bitcart's AuthDependency behavior
# ---------------------------------------------------------------------------

# Token registry the stub uses to decide which response to return.
# Keys are the bearer-token strings the tests pass in the
# Authorization header; values describe the resulting auth state.
#
# This intentionally mirrors the four real branches in
# bitcart_fork/api/services/auth.py::check_permissions:
#   - "no token"        → 401 (unauthenticated)
#   - "unknown token"   → 401 (token not in DB)
#   - "user, no scope"  → 403 (token lacks server_management permission)
#   - "non-su, w/scope" → 403 (token has perm but user is not superuser;
#                              in production tokens.py strips this
#                              combo on token creation, so this is
#                              belt-and-suspenders)
#   - "su w/scope"      → 200 (the only path that should reach the body)
_TOKENS = {
    "user-no-scope": {"is_superuser": False, "permissions": set()},
    "user-with-scope-but-not-su": {
        "is_superuser": False,
        "permissions": {"server_management"},
    },
    "admin-token": {
        "is_superuser": True,
        "permissions": {"server_management"},
    },
}


class StubAuthDependency:
    """Drop-in replacement for bitcart's AuthDependency in tests.

    The real one decodes the bearer token, looks the user up in the
    DB, and runs the full permission/superuser/disabled checks.
    Here we short-circuit to a lookup table so the test stays
    self-contained (no DB, no Bitcart DI container, no real users).
    """

    async def __call__(
        self,
        request: Request,
        security_scopes: SecurityScopes,
    ) -> dict:
        # The real AuthDependency raises 401 (not 403) when the
        # Authorization header is missing. Mirror that — see
        # services/auth.py:54-60 (HTTPException 401, detail "Could
        # not validate credentials").
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        token_str = auth.split(" ", 1)[1].strip()
        token = _TOKENS.get(token_str)
        # Unknown token → 401 (same as missing). Real impl: find_by_token
        # returns None → exc (401). services/auth.py:62.
        if token is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        # Permission check: token must have the scope OR full_control.
        # services/auth.py:83-90.
        for s in security_scopes.scopes:
            if s not in token["permissions"] and "full_control" not in token["permissions"]:
                raise HTTPException(status_code=403, detail="Not enough permissions")
        # server_management ALSO requires is_superuser.
        # services/auth.py:91-93. Belt-and-suspenders vs the token
        # creation strip, defends against forged/leaked tokens.
        if "server_management" in security_scopes.scopes and not token["is_superuser"]:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return {"is_superuser": token["is_superuser"]}


# ---------------------------------------------------------------------------
# Static introspection — proves every route declares the gate
# ---------------------------------------------------------------------------

def _security_scopes_on_route(route) -> set[str]:
    """Collect every scope declared via Security() on the route's
    direct `dependencies` list. The plugin's gate-wiring pattern
    is `Security(auth_dep, scopes=["server_management"])` passed
    through `dependencies=deps`, so reading `route.dependencies`
    is sufficient — no need to walk the nested dependant tree."""
    found: set[str] = set()
    for dep in getattr(route, "dependencies", []) or []:
        if isinstance(dep, Security):
            for scope in dep.scopes or []:
                found.add(scope)
    return found


@pytest.mark.parametrize(
    "router_builder, expected_paths",
    [
        (
            wallet_debug.build_wallet_debug_router,
            {
                "/plugins/liquidityhelper/wallet_debug/wallets",
                "/plugins/liquidityhelper/wallet_debug/wallet/{wallet_id}/csv",
                "/plugins/liquidityhelper/wallet_debug/wallet/{wallet_id}/backup",
            },
        ),
        (
            log_export.build_log_export_router,
            {
                "/plugins/liquidityhelper/wallet_debug/logs/engine",
                "/plugins/liquidityhelper/wallet_debug/logs/all",
            },
        ),
    ],
    ids=["wallet_debug", "log_export"],
)
def test_routes_declare_server_management_scope(router_builder, expected_paths):
    """Every endpoint on the wallet_debug + log_export routers must
    declare a Security dependency carrying the "server_management"
    scope. Pins the gate at collection time."""
    router = router_builder(StubAuthDependency())
    seen_paths: set[str] = set()
    for route in router.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        seen_paths.add(path)
        scopes = _security_scopes_on_route(route)
        assert "server_management" in scopes, (
            f"route {path} is missing server_management scope; "
            f"found scopes: {scopes or '(none)'}. Adding a new "
            f"wallet-debug endpoint? It MUST go through `deps` so "
            f"non-admins can't reach it."
        )
    # Sanity check: we actually saw the routes we expected to audit.
    # A regression that REMOVES one of these endpoints needs a
    # deliberate test update, not a silent drop.
    assert seen_paths == expected_paths, (
        f"route set drift — expected {expected_paths} got {seen_paths}. "
        f"Update the parametrize block to match the intended surface."
    )


# ---------------------------------------------------------------------------
# Live TestClient — proves the gate actually rejects
# ---------------------------------------------------------------------------

# Every endpoint with the canonical URL we'll hit. Both routers are
# mounted onto the same app so we exercise all 5 surfaces with the
# same scenarios. Path-parametrized routes use a placeholder ID;
# the auth check fires BEFORE the route body, so we never need a
# real wallet (or real logs) to assert the rejection.
_ENDPOINTS = [
    # wallet_debug
    "/api/plugins/liquidityhelper/wallet_debug/wallets",
    "/api/plugins/liquidityhelper/wallet_debug/wallet/test-wallet/csv",
    "/api/plugins/liquidityhelper/wallet_debug/wallet/test-wallet/backup",
    # log_export
    "/api/plugins/liquidityhelper/wallet_debug/logs/engine",
    "/api/plugins/liquidityhelper/wallet_debug/logs/all",
]


@pytest.fixture
def auth_test_client() -> TestClient:
    """Mount both routers behind the stub auth on a real FastAPI app.
    `root_path="/api"` mirrors production (bitcart's app has
    root_path=/api and the routers' prefixes deliberately omit it
    — see dashboard_tests for the same pattern)."""
    auth_dep = StubAuthDependency()
    app = FastAPI(root_path="/api")
    app.include_router(wallet_debug.build_wallet_debug_router(auth_dep))
    app.include_router(log_export.build_log_export_router(auth_dep))
    return TestClient(app)


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_endpoint_rejects_unauthenticated_request(auth_test_client, path):
    """No Authorization header → 401. Mirrors the real auth flow
    where a missing bearer token short-circuits before any
    DB/permission lookup."""
    resp = auth_test_client.get(path)
    assert resp.status_code == 401, (
        f"{path} accepted an unauthenticated request (got {resp.status_code}); "
        f"the endpoint is leaking. Body: {resp.text[:200]}"
    )


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_endpoint_rejects_unknown_token(auth_test_client, path):
    """Random bearer token not in the registry → 401. In production
    this is "token not in the tokens table"; same rejection class
    as no token at all."""
    resp = auth_test_client.get(
        path, headers={"Authorization": "Bearer this-token-does-not-exist"}
    )
    assert resp.status_code == 401, (
        f"{path} accepted an unknown token (got {resp.status_code}); "
        f"the endpoint is leaking."
    )


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_endpoint_rejects_non_admin_without_scope(auth_test_client, path):
    """Valid user token but no server_management permission → 403.
    This is the most common "regular user trying to peek" scenario."""
    resp = auth_test_client.get(
        path, headers={"Authorization": "Bearer user-no-scope"}
    )
    assert resp.status_code == 403, (
        f"{path} accepted a non-admin token (got {resp.status_code}); "
        f"the endpoint is leaking."
    )


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_endpoint_rejects_non_superuser_even_with_scope(auth_test_client, path):
    """Token has server_management permission in its scope list, but
    the underlying user is NOT a superuser → 403. In production,
    tokens.py strips server_management from non-superuser tokens at
    creation time, so this combo shouldn't occur naturally; the
    server check is belt-and-suspenders against a forged or
    out-of-date token. We pin it here to ensure that second layer
    keeps working."""
    resp = auth_test_client.get(
        path, headers={"Authorization": "Bearer user-with-scope-but-not-su"}
    )
    assert resp.status_code == 403, (
        f"{path} accepted a non-superuser despite the scope-only gate "
        f"(got {resp.status_code}); the superuser cross-check is broken."
    )


@pytest.mark.parametrize("path", _ENDPOINTS)
def test_endpoint_accepts_admin_token(auth_test_client, path):
    """Superuser with server_management permission reaches the route
    body. The body itself may 4xx/5xx because we haven't wired in a
    fake API / fake logs — that's fine; the test passes as long as
    the response is NOT 401/403 (so the auth gate let it through).

    Pins the POSITIVE case so a too-aggressive auth tightening that
    accidentally blocks superusers gets caught here, not in
    production."""
    resp = auth_test_client.get(
        path, headers={"Authorization": "Bearer admin-token"}
    )
    assert resp.status_code not in (401, 403), (
        f"{path} REJECTED an admin token (got {resp.status_code}); the "
        f"auth gate is over-tightened — superusers can't reach the body. "
        f"Body: {resp.text[:200]}"
    )

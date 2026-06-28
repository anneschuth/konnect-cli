"""Konnect ouderportaal API client.

The ``*.ouderportaal.nl`` portals are white-label tenants of the KidsKonnect /
Konnect childcare platform. Which tenant you talk to is set by the *portal*
(the subdomain), e.g. ``kindencoludens`` for
``https://kindencoludens.ouderportaal.nl``. The portal can be overridden via the
``KONNECT_PORTAL`` environment variable or the ``--portal`` option.

Authentication goes through ``/auth-api/token`` and yields a Bearer token; the
data API lives under ``/restservices-parent``. Login is done headlessly via httpx
(no browser needed). Tokens are stored locally and refreshed automatically.

Note: the exact login handshake (JSON body vs HTTP Basic) was reverse-engineered
from the live portal. ``KonnectAuth.login`` tries a JSON body first and falls back
to HTTP Basic; adjust here if the portal changes.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

# Default tenant; overridable via KONNECT_PORTAL or --portal.
DEFAULT_PORTAL = "kindencoludens"
PORTAL_DOMAIN = "ouderportaal.nl"

# Token storage
CONFIG_DIR = Path("~/.config/konnect").expanduser()
TOKEN_PATH = CONFIG_DIR / "tokens.json"

# Browser-like User-Agent; some Konnect endpoints are picky about this.
USER_AGENT = "Mozilla/5.0 (Macintosh) konnect-cli"


def resolve_portal(portal: str | None = None) -> str:
    """Return the active portal subdomain.

    Precedence: explicit argument, then ``KONNECT_PORTAL`` env var, then the
    default tenant.
    """
    return portal or os.environ.get("KONNECT_PORTAL") or DEFAULT_PORTAL


def base_url(portal: str | None = None) -> str:
    return f"https://{resolve_portal(portal)}.{PORTAL_DOMAIN}"


def _save_tokens(data: dict[str, Any]) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data, indent=2))
    TOKEN_PATH.chmod(0o600)


def _load_tokens() -> dict[str, Any] | None:
    if TOKEN_PATH.exists():
        try:
            return json.loads(TOKEN_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _unwrap(data: Any) -> Any:
    """Unwrap the Konnect ``{result, payload, messages}`` envelope.

    Most ``/auth-api`` and some ``/restservices-parent`` responses wrap their
    real content in a ``payload`` key. Returns ``payload`` when present,
    otherwise the data unchanged.
    """
    if (
        isinstance(data, dict)
        and "payload" in data
        and set(data) <= {"result", "payload", "messages"}
    ):
        return data["payload"]
    return data


def _extract_token(payload: Any) -> str | None:
    """Find a Bearer/access token in a token-endpoint response."""
    if isinstance(payload, str):
        return payload or None
    if isinstance(payload, dict):
        for key in ("token", "accessToken", "access_token", "bearer", "jwt"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
    return None


class KonnectAuth:
    """Handle authentication for a Konnect ouderportaal tenant."""

    @staticmethod
    def login(
        username: str | None = None,
        password: str | None = None,
        portal: str | None = None,
    ) -> dict[str, Any]:
        """Log in and obtain a token via ``PUT /auth-api/token``.

        Tries a JSON body ``{username, password}`` first; if that is rejected,
        retries with HTTP Basic auth. The resulting token (and any refresh
        material), plus the active portal, is saved to :data:`TOKEN_PATH`.
        """
        portal = resolve_portal(portal)
        auth_api = f"{base_url(portal)}/auth-api"

        if not username:
            username = input("E-mailadres: ")
        if not password:
            password = getpass.getpass("Wachtwoord: ")

        with httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            # Establish auth-service context (sets cookies, mirrors the SPA boot).
            try:
                client.get(f"{auth_api}/customerdomainname")
                client.get(f"{auth_api}/sso/settings")
            except httpx.HTTPError:
                pass

            # Attempt 1: JSON body with English field names.
            resp = client.put(
                f"{auth_api}/token",
                json={"username": username, "password": password},
            )

            # Attempt 2: HTTP Basic auth.
            if resp.status_code in (400, 401, 415):
                resp = client.put(
                    f"{auth_api}/token",
                    auth=httpx.BasicAuth(username, password),
                )

            if resp.status_code in (400, 401, 403):
                raise RuntimeError(
                    f"Login mislukt: onjuist e-mailadres of wachtwoord (HTTP {resp.status_code})."
                )
            resp.raise_for_status()

            try:
                body = resp.json()
            except json.JSONDecodeError:
                body = {}
            payload = _unwrap(body)
            token = _extract_token(payload)

            # Some deployments return the token only in a response header.
            if not token:
                header = resp.headers.get("authorization", "")
                if header.lower().startswith("bearer "):
                    token = header.split(" ", 1)[1]

            if not token:
                raise RuntimeError(
                    "Login leek te slagen maar er kwam geen token terug. "
                    "De auth-flow is mogelijk veranderd."
                )

            tokens: dict[str, Any] = {"token": token, "portal": portal}
            if isinstance(payload, dict):
                for key in ("refreshToken", "refresh_token", "expiresIn", "expires_in"):
                    if key in payload:
                        tokens[key] = payload[key]
            _save_tokens(tokens)
            return tokens

    @staticmethod
    def refresh(portal: str | None = None) -> dict[str, Any] | None:
        """Refresh the token via the cookie-backed ``PUT /auth-api/token``.

        Returns the new token dict, or ``None`` when refresh is not possible.
        """
        portal = resolve_portal(portal)
        with httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            try:
                resp = client.put(f"{base_url(portal)}/auth-api/token")
            except httpx.HTTPError:
                return None
            if resp.status_code != 200:
                return None
            try:
                payload = _unwrap(resp.json())
            except json.JSONDecodeError:
                return None
            token = _extract_token(payload)
            if not token:
                return None
            tokens = {"token": token, "portal": portal}
            _save_tokens(tokens)
            return tokens

    @staticmethod
    def get_token() -> tuple[str, str] | None:
        """Return a valid ``(token, portal)``, refreshing if needed.

        The portal is read from the stored token file (falling back to the
        resolved default), so data commands talk to the tenant you logged in to.
        """
        tokens = _load_tokens()
        if not tokens:
            return None

        portal = tokens.get("portal") or resolve_portal()
        token = tokens.get("token", "")
        if token and _token_works(token, portal):
            return token, portal

        refreshed = KonnectAuth.refresh(portal)
        if refreshed:
            return refreshed["token"], portal
        return None


def _token_works(token: str, portal: str) -> bool:
    """Cheap validity check against an authenticated endpoint."""
    try:
        resp = httpx.get(
            f"{base_url(portal)}/restservices-parent/parent",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


class KonnectClient:
    """Synchronous client for a Konnect ouderportaal data API."""

    def __init__(self, token: str | None = None, portal: str | None = None):
        self.token = token
        self.portal = resolve_portal(portal) if (token or portal) else None
        self._client: httpx.Client | None = None

    def __enter__(self) -> KonnectClient:
        if not self.token:
            resolved = KonnectAuth.get_token()
            if not resolved:
                raise RuntimeError("Niet ingelogd. Run eerst `konnect login`.")
            self.token, self.portal = resolved
        if not self.portal:
            self.portal = resolve_portal()
        self._client = httpx.Client(
            base_url=f"{base_url(self.portal)}/restservices-parent",
            timeout=30,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            self._client.close()

    def _get(self, path: str, **params: Any) -> Any:
        assert self._client is not None
        resp = self._client.get(path, params=params or None)
        resp.raise_for_status()
        return _unwrap(resp.json())

    def _items(self, path: str, **params: Any) -> list[dict[str, Any]]:
        data = self._get(path, **params)
        if isinstance(data, dict):
            for key in ("items", "cards", "notifications", "children", "content"):
                if isinstance(data.get(key), list):
                    return data[key]
            return []
        return data if isinstance(data, list) else []

    def get_parent(self) -> dict[str, Any]:
        return self._get("/parent")

    def get_children(self) -> list[dict[str, Any]]:
        return self._items("/children/")

    def get_customer_info(self) -> dict[str, Any]:
        return self._get("/customer/info")

    def get_timeline(self, page: int = 0) -> list[dict[str, Any]]:
        return self._items(f"/timeline/cards/v2/{page}")

    def get_notifications(self) -> list[dict[str, Any]]:
        return self._items("/notification/notifications")

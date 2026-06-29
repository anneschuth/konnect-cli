"""Konnect ouderportaal API client.

The ``*.ouderportaal.nl`` portals are white-label tenants of the KidsKonnect /
Konnect childcare platform. Which tenant you talk to is set by the *portal*
(the subdomain), e.g. ``kindencoludens`` for
``https://kindencoludens.ouderportaal.nl``. The portal can be overridden via the
``KONNECT_PORTAL`` environment variable or the ``--portal`` option.

The parent login sets an HttpOnly session cookie on the ``/auth/`` page;
``GET /auth-api/token`` then exchanges that cookie for a JWT, which is the Bearer
token for ``/restservices-parent``. There is no replayable username/password API,
so login is browser-backed via Playwright (see :mod:`konnect.browser_auth`); a
persistent profile keeps the session alive so refreshes run headless. Tokens are
stored locally and refreshed automatically.
"""

from __future__ import annotations

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
        for key in ("authToken", "token", "accessToken", "access_token", "bearer", "jwt"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _store_minted(body: dict[str, Any], portal: str) -> dict[str, Any]:
    """Persist a minted token body and return the stored token dict."""
    token = _extract_token(body)
    if not token:
        raise RuntimeError(
            "Inloggen lukte, maar er kwam geen token terug. De auth-flow is mogelijk veranderd."
        )
    tokens: dict[str, Any] = {"token": token, "portal": portal}
    for key in ("refreshToken", "expiration", "domainServerName"):
        if body.get(key) is not None:
            tokens[key] = body[key]
    _save_tokens(tokens)
    return tokens


class KonnectAuth:
    """Handle authentication for a Konnect ouderportaal tenant.

    Login is browser-backed (Playwright): the parent login sets a session
    cookie, and ``GET /auth-api/token`` exchanges it for a JWT. A persistent
    browser profile per portal keeps the session alive, so token refreshes run
    headless without re-login. Requires the ``browser`` extra.
    """

    @staticmethod
    def login(
        username: str | None = None,
        password: str | None = None,
        portal: str | None = None,
        interactive: bool = True,
    ) -> dict[str, Any]:
        """Log in via the browser and store the resulting JWT.

        When *username*/*password* are given they are filled and submitted
        headless, with no visible window. A window opens only when a human is
        needed: no credentials, or an extra step such as a captcha. The token,
        plus the active portal, is saved to :data:`TOKEN_PATH`.
        """
        portal = resolve_portal(portal)
        body = _mint(portal, username=username, password=password, interactive=interactive)
        if not body:
            raise RuntimeError(
                "Login mislukt: kon geen sessie opzetten in de browser. "
                "Controleer je inloggegevens en probeer opnieuw."
            )
        return _store_minted(body, portal)

    @staticmethod
    def refresh(portal: str | None = None) -> dict[str, Any] | None:
        """Mint a fresh JWT from the persistent browser session (headless).

        Returns the new token dict, or ``None`` when the session has expired and
        interactive re-login is needed.
        """
        portal = resolve_portal(portal)
        try:
            body = _mint(portal, interactive=False)
        except RuntimeError:
            return None
        if not body:
            return None
        return _store_minted(body, portal)

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


def _mint(
    portal: str,
    username: str | None = None,
    password: str | None = None,
    interactive: bool = True,
) -> dict[str, Any] | None:
    """Mint a JWT via the browser, with a clear error if Playwright is missing."""
    try:
        from .browser_auth import mint_token
    except ImportError as e:
        raise RuntimeError(
            "Browser-login vereist de 'browser' extra. "
            "Installeer met: uv tool install --editable '.[cli,browser]' "
            "en draai: uv run playwright install chromium"
        ) from e
    return mint_token(
        portal,
        base_url(portal),
        username=username,
        password=password,
        interactive=interactive,
    )


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
            for key in ("items", "cards", "activeChildren", "notifications", "content"):
                if isinstance(data.get(key), list):
                    return data[key]
            return []
        return data if isinstance(data, list) else []

    def get_parent(self) -> dict[str, Any]:
        return self._get("/parent")

    def get_children(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        """Return children. The API splits them into active and inactive lists."""
        data = self._get("/children/")
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []
        children = list(data.get("activeChildren") or [])
        if include_inactive:
            children += list(data.get("inactiveChildren") or [])
        return children

    def get_customer_info(self) -> dict[str, Any]:
        return self._get("/customer/info")

    def get_timeline(self, page: int = 0) -> list[dict[str, Any]]:
        return self._items(f"/timeline/cards/v2/{page}")

    def get_notifications(self) -> dict[str, Any]:
        """Return unread counts ``{nrOfNewMessages, nrOfNewNewsItems, ...}``."""
        data = self._get("/notification/notifications")
        return data if isinstance(data, dict) else {}

    def get_messages(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        """Return logbook messages (the mailbox) in the ``YYYYMMDD`` window.

        Each item carries the full ``message`` (HTML), ``subject``, ``date``
        (epoch ms), ``lastWritten`` (author), ``unread`` and ``lastFromParent``.
        """
        data = self._get("/logbook/overview", **{"from": date_from, "to": date_to})
        return data if isinstance(data, list) else []

    def get_newsletters(self, index: int = 0) -> list[dict[str, Any]]:
        """Return newsletters: ``{mailSubject, contentSnippet, sendDate, unread}``."""
        data = self._get("/newsletter", index=index)
        if isinstance(data, dict) and isinstance(data.get("newsletterItems"), list):
            return data["newsletterItems"]
        return []

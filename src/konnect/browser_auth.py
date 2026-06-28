"""Browser-backed authentication for Konnect ouderportaal.

The parent login establishes an HttpOnly session cookie on the ``/auth/`` page;
``GET /auth-api/token`` then exchanges that cookie for a JWT, which is the Bearer
token for ``/restservices-parent``. There is no replayable username/password API
endpoint, so we drive a real browser (Playwright) to log in, then mint the JWT
from the resulting session. A persistent profile per portal keeps the session
alive, so refreshes run headless without re-login.

This module is only imported when the ``browser`` extra is installed.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

PROFILES_DIR = Path("~/.config/konnect/browser-profiles").expanduser()

# In-page script: mint a JWT from the session cookie via GET /auth-api/token.
_MINT_JS = """
async () => {
    const r = await fetch('/auth-api/token', {
        method: 'GET',
        credentials: 'include',
        headers: {'Accept': 'application/json'},
    });
    if (r.status !== 200) return {error: 'status ' + r.status};
    try { return {body: await r.json()}; }
    catch (e) { return {error: 'non-json'}; }
}
"""


def _profile_dir(portal: str) -> Path:
    return PROFILES_DIR / portal


def _fill_login(page, username: str | None, password: str | None) -> None:
    """Best-effort fill of the login form when credentials are provided.

    Selectors are intentionally loose; the Konnect login is a standard
    e-mail/password form. If anything does not match, we silently fall back to
    interactive login (the user types into the open window).
    """
    if not (username and password):
        return
    try:
        email_sel = (
            "input[type=email], input[autocomplete=username], "
            "input[name*=mail i], input[id*=mail i], input[formcontrolname*=mail i]"
        )
        pass_sel = "input[type=password], input[autocomplete=current-password]"
        page.wait_for_selector(email_sel, timeout=15000)
        page.fill(email_sel, username)
        page.fill(pass_sel, password)
        page.click(
            "button[type=submit], button:has-text('Inloggen'), "
            "button:has-text('Aanmelden'), [type=submit]"
        )
    except Exception:  # noqa: BLE001 — Playwright raises broad Error types
        # Form shape changed or extra step (e.g. captcha); let the user finish.
        pass


def mint_token(
    portal: str,
    base: str,
    username: str | None = None,
    password: str | None = None,
    interactive: bool = True,
) -> dict[str, Any] | None:
    """Drive a browser to obtain a JWT for ``portal``.

    Returns the ``GET /auth-api/token`` body (``{authToken, expiration,
    refreshToken, domainServerName}``) or ``None`` on failure. When a valid
    session already exists in the profile this runs headless; otherwise it opens
    a window for login (filling credentials when given).
    """
    from playwright.sync_api import sync_playwright

    profile = _profile_dir(portal)
    profile.mkdir(parents=True, exist_ok=True)
    has_session = (profile / "Default" / "Cookies").exists()
    login_url = f"{base}/auth/login"
    app_url = f"{base}/parent/"

    def _settle(page) -> None:
        # networkidle is flaky on this SPA (it polls), so suppress the timeout.
        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(1000)

    with sync_playwright() as p:

        def launch(headless: bool):
            return p.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
            )

        context = launch(headless=has_session)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(login_url, timeout=30000, wait_until="domcontentloaded")
        _settle(page)

        needs_login = "/auth/" in page.url and "/parent" not in page.url

        if needs_login and has_session:
            # Stored session expired: relaunch headed for interactive login.
            context.close()
            context = launch(headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(login_url, timeout=30000, wait_until="domcontentloaded")
            _settle(page)
            needs_login = "/auth/" in page.url and "/parent" not in page.url

        if needs_login:
            if not interactive and not (username and password):
                context.close()
                return None
            _fill_login(page, username, password)
            try:
                page.wait_for_url("**/parent/**", timeout=300000)
            except Exception:  # noqa: BLE001
                context.close()
                return None
            _settle(page)
        elif "/parent" not in page.url:
            page.goto(app_url, timeout=30000, wait_until="domcontentloaded")
            _settle(page)

        result = page.evaluate(_MINT_JS)
        context.close()

    if isinstance(result, dict) and isinstance(result.get("body"), dict):
        return result["body"]
    return None

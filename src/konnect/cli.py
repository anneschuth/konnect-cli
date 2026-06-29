"""Konnect CLI: toegang tot je ouderportaal vanuit de terminal.

Usage:
    konnect login                # Inloggen via een browservenster
    konnect logout               # Token verwijderen
    konnect account              # Account- en opvanginfo
    konnect children [--all]     # Kinderen tonen
    konnect timeline [--limit N] # Tijdlijn (foto's, berichten, dagritme)
    konnect messages [N]         # Berichten van de opvang (lijst, of N volledig)
    konnect newsletters          # Nieuwsbrieven
    konnect notifications        # Ongelezen aantallen
    konnect completion SHELL     # Shell completion script
"""

from __future__ import annotations

__version__ = "0.3.0"

import json
import sys
from typing import Any

import click
import httpx
from rich.console import Console
from rich.panel import Panel

from .client import KonnectAuth, KonnectClient, resolve_portal
from .helpers import child_name, first_str, fmt_date, html_to_text

console = Console()


def _dump(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _default_window() -> tuple[str, str]:
    """Return a ``(from, to)`` ``YYYYMMDD`` window covering roughly the last year."""
    from datetime import date, timedelta

    today = date.today()
    return (today - timedelta(days=400)).strftime("%Y%m%d"), today.strftime("%Y%m%d")


@click.group()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output als JSON")
@click.version_option(version=__version__, prog_name="konnect")
@click.pass_context
def cli(ctx: click.Context, as_json: bool) -> None:
    """Konnect CLI - je ouderportaal vanuit de terminal."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json


@cli.command()
@click.option("-u", "--username", default=None, help="E-mailadres (of KONNECT_USERNAME env)")
@click.option("-p", "--password", default=None, help="Wachtwoord (of KONNECT_PASSWORD env)")
@click.option(
    "--portal",
    default=None,
    help="Portaal-subdomein, bijv. kindencoludens (of KONNECT_PORTAL env)",
)
@click.option(
    "--store", is_flag=True, default=False, help="Credentials opslaan in ~/.config/konnect/.env"
)
def login(username: str | None, password: str | None, portal: str | None, store: bool) -> None:
    """Inloggen bij je ouderportaal.

    Met -u/-p (of env) gebeurt het inloggen headless op de achtergrond. Alleen
    als er geen gegevens zijn (of bij bijv. een captcha) opent er een venster
    waarin je zelf inlogt. De sessie blijft daarna bewaard, dus volgende keren
    verloopt het token stilletjes op de achtergrond.
    """
    import os

    from dotenv import load_dotenv

    from .client import CONFIG_DIR

    # Load .env files: ~/.config/konnect/.env first, then local .env
    env_path = CONFIG_DIR / ".env"
    load_dotenv(env_path)
    load_dotenv()  # local .env

    username = username or os.environ.get("KONNECT_USERNAME", "")
    password = password or os.environ.get("KONNECT_PASSWORD", "")
    active_portal = resolve_portal(portal)

    try:
        if username and password:
            console.print("[dim]Inloggen op de achtergrond…[/]")
        else:
            console.print("[dim]Browser wordt geopend voor login…[/]")
        KonnectAuth.login(
            username=username or None,
            password=password or None,
            portal=active_portal,
        )
        console.print(f"[green]Login geslaagd![/] [dim]({active_portal})[/]")

        if store and username and password:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            lines = f"KONNECT_USERNAME={username}\nKONNECT_PASSWORD={password}\n"
            if portal:
                lines += f"KONNECT_PORTAL={active_portal}\n"
            env_path.write_text(lines)
            env_path.chmod(0o600)
            console.print(f"  [dim]Credentials opgeslagen in {env_path}[/]")
    except Exception as e:
        console.print(f"[red]Login mislukt: {e}[/]")
        sys.exit(1)


@cli.command()
def logout() -> None:
    """Uitloggen (tokens verwijderen)."""
    from .client import TOKEN_PATH

    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        console.print("[green]Uitgelogd.[/]")
    else:
        console.print("[dim]Je was al uitgelogd.[/]")


@cli.command()
@click.pass_context
def account(ctx: click.Context) -> None:
    """Account- en locatie-info tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        parent = client.get_parent()
        customer = client.get_customer_info()

        if as_json:
            _dump({"parent": parent, "customer": customer})
            return

        name = first_str(parent, "fullname", "fullName", "firstName", default="(onbekend)")
        email = first_str(parent, "emailAddress", "email")
        customer_name = first_str(customer, "customerName", "name")
        console.print(
            Panel(
                f"Naam: {name}\nE-mail: {email}\nOpvang: {customer_name}",
                title="[bold]Account[/]",
                border_style="blue",
            )
        )


@cli.command()
@click.option("--all", "show_all", is_flag=True, default=False, help="Ook inactieve kinderen")
@click.pass_context
def children(ctx: click.Context, show_all: bool) -> None:
    """Kinderen tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        items = client.get_children(include_inactive=show_all)

        if as_json:
            _dump(items)
            return

        if not items:
            console.print("[dim]Geen kinderen gevonden[/]")
            return

        for child in items:
            name = child_name(child)
            cid = child.get("id", child.get("childId", ""))
            groups = child.get("activeGroups") or child.get("groups") or []
            group = first_str(groups[0], "name") if groups else ""
            suffix = f" [cyan]{group}[/cyan]" if group else ""
            console.print(f"  [bold]{name}[/]{suffix} [dim](ID: {cid})[/]")


@cli.command()
@click.option("--limit", default=20, type=int, help="Maximum aantal kaarten")
@click.option("--page", default=0, type=int, help="Pagina (0 = nieuwste)")
@click.pass_context
def timeline(ctx: click.Context, limit: int, page: int) -> None:
    """Tijdlijn tonen (foto's, berichten, dagritme)."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        items = client.get_timeline(page=page)

        if as_json:
            _dump(items[:limit])
            return

        if not items:
            console.print("[dim]Geen tijdlijn-items gevonden[/]")
            return

        for card in items[:limit]:
            ctype = first_str(card, "type", default="kaart")
            when = fmt_date(card.get("date"))

            # The text lives in a sub-object named after the card type
            # (e.g. card["journal"]); photo cards carry a top-level "photos" list.
            sub_raw = card.get(ctype)
            sub: dict[str, Any] = sub_raw if isinstance(sub_raw, dict) else {}
            raw = first_str(sub, "content", "journalContent", "dayRythmContent", "message", "text")
            text = html_to_text(raw)
            written_by = first_str(sub, "writtenByName")
            photos_raw = card.get("photos")
            n_photos = len(photos_raw) if isinstance(photos_raw, list) else 0

            kids = card.get("children") or []
            kid_names = ", ".join(child_name(k) for k in kids if isinstance(k, dict))

            meta_parts = [f"[cyan]{ctype}[/cyan]"]
            if kid_names:
                meta_parts.append(kid_names)
            if when:
                meta_parts.append(when)
            if written_by:
                meta_parts.append(f"door {written_by}")
            if n_photos:
                meta_parts.append(f"{n_photos} foto('s)")
            meta = " | ".join(meta_parts)

            body = meta
            if text:
                body += f"\n\n{text[:500]}"
            console.print(Panel(body, border_style="blue"))
            console.print()


@cli.command()
@click.pass_context
def notifications(ctx: click.Context) -> None:
    """Ongelezen aantallen tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        counts = client.get_notifications()

        if as_json:
            _dump(counts)
            return

        labels = {
            "nrOfNewMessages": "Berichten",
            "nrOfNewNewsItems": "Nieuws",
            "nrOfNewNewsletters": "Nieuwsbrieven",
        }
        rows = [(label, counts.get(key) or 0) for key, label in labels.items()]
        if not any(n for _, n in rows):
            console.print("[dim]Niets ongelezen[/]")
            return

        for label, n in rows:
            mark = f"[bold red]{n}[/]" if n else "[dim]0[/]"
            console.print(f"  {label}: {mark} ongelezen")


@cli.command()
@click.argument("number", type=int, required=False)
@click.option("--from", "date_from", default=None, help="Begindatum YYYYMMDD")
@click.option("--to", "date_to", default=None, help="Einddatum YYYYMMDD")
@click.option("--unread", is_flag=True, default=False, help="Alleen ongelezen")
@click.pass_context
def messages(
    ctx: click.Context,
    number: int | None,
    date_from: str | None,
    date_to: str | None,
    unread: bool,
) -> None:
    """Berichten van de opvang tonen.

    Zonder argument: lijst alle berichten. Met een nummer: toon dat bericht
    volledig (gebruik het nummer uit de lijst).
    """
    as_json = ctx.obj["json"]
    win_from, win_to = _default_window()
    with KonnectClient() as client:
        items = client.get_messages(date_from or win_from, date_to or win_to)

    items.sort(key=lambda m: m.get("date") or 0, reverse=True)
    if unread:
        items = [m for m in items if m.get("unread")]

    if as_json:
        _dump(items if number is None else (items[number - 1] if 0 < number <= len(items) else {}))
        return

    if not items:
        console.print("[dim]Geen berichten gevonden[/]")
        return

    # Detail view: show one full message.
    if number is not None:
        if not (0 < number <= len(items)):
            console.print(f"[red]Nummer {number} bestaat niet. Beschikbaar: 1-{len(items)}[/]")
            sys.exit(1)
        msg = items[number - 1]
        subject = first_str(msg, "subject", default="(geen onderwerp)")
        author = first_str(msg, "lastWritten")
        when = fmt_date(msg.get("date"))
        body = html_to_text(first_str(msg, "message"))
        header = f"{subject}\n[dim]{author} | {when}[/]\n\n{body}"
        console.print(Panel(header, title="[bold]Bericht[/]", border_style="blue"))
        return

    # List view.
    for i, msg in enumerate(items, start=1):
        subject = first_str(msg, "subject", default="(geen onderwerp)")
        author = first_str(msg, "lastWritten")
        when = fmt_date(msg.get("date"))
        snippet = html_to_text(first_str(msg, "message")).replace("\n", " ")[:80]
        mark = "[bold red]●[/]" if msg.get("unread") else "[dim]●[/]"
        console.print(f"{mark} [dim]{i:>2}[/] [bold]{subject}[/] [dim]· {author} · {when}[/]")
        if snippet:
            console.print(f"     [dim]{snippet}[/]")


@cli.command()
@click.pass_context
def newsletters(ctx: click.Context) -> None:
    """Nieuwsbrieven tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        items = client.get_newsletters()

    if as_json:
        _dump(items)
        return

    if not items:
        console.print("[dim]Geen nieuwsbrieven gevonden[/]")
        return

    for n in items:
        subject = first_str(n, "mailSubject", default="(geen onderwerp)")
        when = fmt_date(n.get("sendDate"))
        snippet = html_to_text(first_str(n, "contentSnippet")).replace("\n", " ")[:80]
        mark = "[bold red]●[/]" if n.get("unread") else "[dim]●[/]"
        console.print(f"{mark} [bold]{subject}[/] [dim]· {when}[/]")
        if snippet:
            console.print(f"   [dim]{snippet}[/]")


@cli.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Output shell completion script.

    Add to your shell config to enable tab completion:

    \b
      # bash (~/.bashrc)
      eval "$(konnect completion bash)"

    \b
      # zsh (~/.zshrc)
      eval "$(konnect completion zsh)"

    \b
      # fish (~/.config/fish/completions/konnect.fish)
      konnect completion fish > ~/.config/fish/completions/konnect.fish
    """
    import os

    os.environ["_KONNECT_COMPLETE"] = f"{shell}_source"
    try:
        cli.main(standalone_mode=False)
    except SystemExit:
        pass
    finally:
        del os.environ["_KONNECT_COMPLETE"]


def main() -> None:
    try:
        cli(standalone_mode=True)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            console.print("[red]Sessie verlopen. Run `konnect login` opnieuw.[/]")
        else:
            console.print(f"[red]API fout: {e.response.status_code}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()

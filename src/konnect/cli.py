"""Konnect CLI: toegang tot je ouderportaal vanuit de terminal.

Usage:
    konnect login                # Inloggen met e-mailadres + wachtwoord
    konnect account              # Account- en locatie-info
    konnect children             # Kinderen tonen
    konnect timeline [--limit N] # Tijdlijn (foto's, berichten, dagritme)
    konnect notifications        # Meldingen tonen
    konnect completion SHELL     # Shell completion script
"""

from __future__ import annotations

__version__ = "0.1.0"

import json
import sys
from typing import Any

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import KonnectAuth, KonnectClient, resolve_portal
from .helpers import child_name, first_str, fmt_date

console = Console()


def _dump(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


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

    Opent een browservenster. Met -u/-p (of env) worden je gegevens automatisch
    ingevuld; anders log je zelf in het venster in. De sessie blijft daarna
    bewaard, dus volgende keren verloopt het token stilletjes op de achtergrond.
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

        name = first_str(parent, "displayName", "fullName", "name", default="(onbekend)")
        email = first_str(parent, "email", "emailAddress")
        customer_name = first_str(customer, "name", "displayName")
        console.print(
            Panel(
                f"Naam: {name}\nE-mail: {email}\nOpvang: {customer_name}",
                title="[bold]Account[/]",
                border_style="blue",
            )
        )


@cli.command()
@click.pass_context
def children(ctx: click.Context) -> None:
    """Kinderen tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        items = client.get_children()

        if as_json:
            _dump(items)
            return

        if not items:
            console.print("[dim]Geen kinderen gevonden[/]")
            return

        for child in items:
            name = child_name(child)
            cid = child.get("id", child.get("childId", ""))
            console.print(f"  [bold]{name}[/] (ID: {cid})")


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
            ctype = first_str(card, "type", "cardType", default="kaart")
            when = fmt_date(first_str(card, "date", "createdAt", "publishedAt", "timestamp"))
            text = first_str(card, "text", "message", "description", "content", "title")
            photos = card.get("photos", card.get("images", card.get("media", [])))
            n_photos = len(photos) if isinstance(photos, list) else 0

            meta_parts = [f"[cyan]{ctype}[/cyan]"]
            if when:
                meta_parts.append(when)
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
    """Meldingen tonen."""
    as_json = ctx.obj["json"]
    with KonnectClient() as client:
        items = client.get_notifications()

        if as_json:
            _dump(items)
            return

        if not items:
            console.print("[dim]Geen meldingen gevonden[/]")
            return

        table = Table(title="Meldingen")
        table.add_column("Datum", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Bericht", style="bold")
        table.add_column("Gelezen", style="green")

        for n in items:
            when = fmt_date(first_str(n, "date", "createdAt", "timestamp"))
            ntype = first_str(n, "type", "notificationType")
            text = first_str(n, "text", "message", "title", "description")
            read = n.get("read", n.get("isRead"))
            read_str = "ja" if read else "[red]nee[/red]"
            table.add_row(when, ntype, text[:60], read_str)

        console.print(table)


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

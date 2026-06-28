<h1 align="center">
  🧒 konnect
</h1>

<p align="center">
  <em>A CLI and Python SDK for Konnect ouderportaal childcare portals.</em><br>
  Kinderen, tijdlijn en meldingen bekijken vanuit de terminal, zonder de app te openen.
</p>

<p align="center">
  <a href="https://github.com/anneschuth/konnect-cli/actions"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/anneschuth/konnect-cli/ci.yml?branch=main&label=CI"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/anneschuth/konnect-cli"></a>
</p>

---

## Wat doet het?

De `*.ouderportaal.nl` portalen zijn white-label tenants van het KidsKonnect / Konnect kinderopvang-platform. `konnect` geeft je toegang tot je eigen portaal vanuit de terminal:

- **Kinderen** en accountinfo tonen
- **Tijdlijn** bekijken: foto's, berichten en dagritme-observaties van de opvang
- **Berichten** van de opvang lezen, plus nieuwsbrieven
- **Ongelezen aantallen** ophalen
- **JSON output** voor scripting en automatisering

Je kiest je portaal met het subdomein (bijvoorbeeld `kindencoludens` voor `kindencoludens.ouderportaal.nl`). De login zet een sessie op via een echt browservenster (Playwright). Daarna wordt het token (een JWT) lokaal bewaard en op de achtergrond ververst, zonder dat je opnieuw hoeft in te loggen.

> De portaal-API is niet publiek gedocumenteerd. De client is reverse-engineered op basis van een Konnect ouderportaal en kan breken als de aanbieder iets verandert.

## Installatie

```bash
# CLI + browser-login met uv (aanbevolen)
uv tool install --editable '.[cli,browser]'
uv run playwright install chromium   # eenmalig: browser voor de login

# Alleen SDK (alleen httpx)
pip install .

# Vanuit source, voor ontwikkeling
git clone https://github.com/anneschuth/konnect-cli.git
cd konnect-cli
uv tool install --editable '.[cli,browser]'
uv run playwright install chromium
```

## Snel aan de slag

```bash
# Inloggen (opent een browservenster; log daar in)
konnect login

# Voor een ander portaal dan de standaard
konnect login --portal jouwopvang

# Of met credentials uit env / .env, en opslaan voor later
konnect login --store

# Kinderen tonen
konnect children

# Account- en opvanginfo
konnect account

# Tijdlijn (laatste 20 kaarten)
konnect timeline --limit 20

# Berichten van de opvang (lijst, dan nummer 3 volledig lezen)
konnect messages
konnect messages 3

# Ongelezen aantallen
konnect notifications
```

## Alle commando's

| Commando | Functie |
| --- | --- |
| `konnect login [-u] [-p] [--portal] [--store]` | Inloggen, token opslaan |
| `konnect logout` | Token verwijderen |
| `konnect account` | Account- en opvanginfo |
| `konnect children [--all]` | Kinderen tonen |
| `konnect timeline [--limit N] [--page N]` | Tijdlijn: foto's, berichten, dagritme |
| `konnect messages [N] [--unread] [--from] [--to]` | Berichten van de opvang (lijst, of N volledig) |
| `konnect newsletters` | Nieuwsbrieven |
| `konnect notifications` | Ongelezen aantallen |
| `konnect completion SHELL` | Shell completion (bash/zsh/fish) |

### JSON output

Elke data-opdracht accepteert `--json` voor machine-leesbare output:

```bash
konnect --json children | jq '.[].displayName'
konnect --json timeline --limit 5 > tijdlijn.json
```

## Configuratie

### Portaal

Welk portaal je benadert wordt bepaald door het subdomein, in volgorde:

1. `--portal` bij `konnect login`
2. de `KONNECT_PORTAL` environment variabele
3. de standaard (`kindencoludens`)

Het gekozen portaal wordt bij je token opgeslagen, dus latere commando's praten met dezelfde tenant.

### Credentials

`konnect login` opent een browservenster op de loginpagina. Geef je gegevens mee om het formulier automatisch te laten invullen, of log handmatig in het venster in:

```bash
# 1. Command-line opties (vult het formulier automatisch in)
konnect login -u je@email.nl -p geheim

# 2. Environment variabelen of .env bestand
#    (lokale ./.env of ~/.config/konnect/.env)
export KONNECT_USERNAME=je@email.nl
export KONNECT_PASSWORD=geheim
export KONNECT_PORTAL=jouwopvang
konnect login

# 3. Zonder gegevens: log zelf in het geopende venster in
konnect login
```

Zie [.env.example](.env.example) voor het formaat. Met `--store` worden je credentials in `~/.config/konnect/.env` bewaard (mode `0600`).

### Sessie en tokens

De browsersessie blijft bewaard in een profiel per portaal onder `~/.config/konnect/browser-profiles/`. Het token (een JWT) staat in `~/.config/konnect/tokens.json` (mode `0600`) en wordt automatisch en headless ververst zolang de sessie geldig is. Pas als de sessie verloopt opent `konnect` weer een venster om opnieuw in te loggen.

## Shell completion

```bash
# bash, toevoegen aan ~/.bashrc
eval "$(konnect completion bash)"

# zsh, toevoegen aan ~/.zshrc
eval "$(konnect completion zsh)"

# fish
konnect completion fish > ~/.config/fish/completions/konnect.fish
```

## SDK gebruik

Het `konnect` package werkt ook als Python SDK, zonder CLI-afhankelijkheden:

```python
from konnect import KonnectAuth, KonnectClient, child_name

# Inloggen (eenmalig)
KonnectAuth.login("je@email.nl", "geheim", portal="kindencoludens")

# API gebruiken
with KonnectClient() as client:
    for child in client.get_children():
        print(child_name(child))

    for card in client.get_timeline():
        print(card.get("type"), card.get("text", ""))
```

## Development

```bash
git clone https://github.com/anneschuth/konnect-cli.git
cd konnect-cli
uv sync --extra dev
uv run pre-commit install
uv run pytest
uv run konnect --help
```

Zie [CONTRIBUTING.md](CONTRIBUTING.md) voor meer details.

## Licentie

MIT, zie [LICENSE](LICENSE).

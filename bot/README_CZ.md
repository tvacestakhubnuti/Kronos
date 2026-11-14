# Kronos trading bot – návod

Bot jednou za svíčku (výchozí: 1× denně) stáhne ceny z burzy, nechá Kronos předpovědět další vývoj
a podle toho **koupí, prodá, nebo nic nedělá** (jen spot: žádná páka, žádné shorty).
Všechno hlásí na Telegram a dá se ovládat z mobilu.

> ⚠️ **Backtest zatím neprokázal, že Kronos vydělává víc než prosté držení.**
> Používej režim PAPER, dokud nemáš vlastní důkaz, že strategie funguje.
> Do režimu LIVE dávej jen peníze, jejichž ztrátu uneseš.

## Režimy

| Režim | Peníze | Potřebuje API klíče |
|---|---|---|
| `PAPER` (výchozí) | virtuální, skutečné ceny | ne |
| `TESTNET` | virtuální na testovací burze Binance | ano (testnet) |
| `LIVE` | **skutečné** | ano + `I_UNDERSTAND_LIVE_TRADING_RISK=true` |

## 1. Telegram (5 minut)

1. V Telegramu napiš **@BotFather** → `/newbot` → zadej jméno → dostaneš **token** (`123456:ABC...`).
2. Napiš svému novému botovi libovolnou zprávu (např. „ahoj“).
3. Napiš **@userinfobot** → odpoví ti tvé **ID** (číslo) – to je `TELEGRAM_CHAT_ID`.

Bot poslouchá jen tvoje ID, nikoho jiného.

## 2. Server (VPS)

Doporučení: **Hetzner Cloud CX22** (2 CPU, 4 GB RAM, ~5 €/měsíc), lokace **Německo nebo Finsko**,
systém **Ubuntu 24.04**. (Funguje i DigitalOcean, Vultr apod. – hlavně ne USA kvůli Binance.)

Po vytvoření se připoj (na Windows přes PowerShell, na Macu přes Terminál):

```bash
ssh root@IP_ADRESA_SERVERU
```

Nainstaluj Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Instalace bota

```bash
git clone -b trading-bot https://github.com/tvacestakhubnuti/Kronos.git
cd Kronos
cp .env.example .env
nano .env
```

V `.env` vyplň aspoň `TELEGRAM_TOKEN` a `TELEGRAM_CHAT_ID` (ulož: `Ctrl+O`, `Enter`, `Ctrl+X`).

Spuštění (první sestavení trvá ~5 minut):

```bash
mkdir -p state && chown -R 1000:1000 state
docker compose up -d --build
```

Složka `state` musí patřit uživateli s ID 1000, pod kterým bot v kontejneru běží
(jinak skončí chybou `PermissionError: ... /app/state/hf-cache`).

Do minuty ti na Telegram přijde zpráva „🤖 Bot spuštěn“. Bot se sám spustí i po restartu serveru.

## 4. Ovládání z Telegramu

| Příkaz | Co dělá |
|---|---|
| `/status` | cena, zůstatek, zisk/ztráta od startu, poslední rozhodnutí |
| `/pause` | pozastaví obchodování (pozice zůstávají) |
| `/resume` | obnoví obchodování |
| `/sellall` | prodá vše do hotovosti a pozastaví bota |

Bot se sám pozastaví, když ztráta od startu překročí `MAX_DRAWDOWN` (výchozí 20 %).

## 5. Užitečné příkazy na serveru

```bash
cd ~/Kronos
docker compose logs -f --tail 50     # živý výpis (ukončíš Ctrl+C)
docker compose restart               # restart po změně .env
docker compose down                  # zastavení
git pull && docker compose up -d --build   # aktualizace
```

Všechny obchody se zapisují do `state/trades.csv` (hodí se k daňovému přiznání).

## 6. Přechod na TESTNET / LIVE

**TESTNET:** na https://testnet.binance.vision se přihlas přes GitHub → *Generate HMAC_SHA256 Key*.
Do `.env` dej `MODE=TESTNET`, `API_KEY`, `API_SECRET` a `docker compose restart`.

**LIVE** (až po dostatečném testování):
1. Na Binance vytvoř API klíč: **povol jen „Enable Spot & Margin Trading“, NIKDY „Enable Withdrawals“**,
   a v nastavení klíče ho **omez na IP adresu serveru**.
2. V `.env`: `MODE=LIVE`, klíče, `I_UNDERSTAND_LIVE_TRADING_RISK=true`.
3. Smaž starý papírový stav, ať se zisk počítá od nuly: `rm -f state/state.json state/paper_balance.json`
4. `docker compose up -d`

## Nastavení strategie (`.env`)

| Proměnná | Význam |
|---|---|
| `SYMBOL` | trh, např. `BTC/USDT`, `ETH/USDT` |
| `TIMEFRAME` / `HORIZON` | `1d`/`1` = rozhodnutí denně; `4h`/`6` = předpověď na den dopředu ze 4h svíček |
| `THRESHOLD` | kupuj, jen když model čeká růst větší než tato hodnota (`0.01` = 1 %) |
| `POSITION_FRACTION` | kolik hotovosti použít na nákup (`0.5` = polovinu) |
| `MAX_DRAWDOWN` | automatické pozastavení při ztrátě (`0.2` = 20 %) |

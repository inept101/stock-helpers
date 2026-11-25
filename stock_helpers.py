"""Local data collection and portfolio arithmetic for the dashboard and skill."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import ssl
import sys
import webbrowser
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from getpass import getpass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / ".stock-helpers"
IST = ZoneInfo("Asia/Kolkata")
NSE_FEED = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
KITE_API = "https://api.kite.trade"
KITE_LOCAL_CALLBACK = "http://127.0.0.1:8765/"
KITE_READ_APIS = {
    "holdings": ("/portfolio/holdings", "Long-term equity holdings", list),
    "positions": ("/portfolio/positions", "Net and day trading positions", dict),
    "funds": ("/user/margins/equity", "Equity funds and margin breakdown", dict),
    "orders": ("/orders", "Orders for the current trading day", list),
    "trades": ("/trades", "Executed fills for the current trading day", list),
    "mutual-funds": ("/mf/holdings", "Demat mutual fund holdings", list),
}
MAX_FEED_BYTES = 4 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(name, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(name, value):
    write_text(name, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def write_text(name, value):
    target = DATA / name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    replace_text(target, value)


def replace_text(target, value):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(value)
            output.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def publish_brief(brief):
    brief = brief.strip()
    if not brief:
        raise ValueError("Supply a nonempty Markdown brief.")
    current = DATA / "decision-brief.md"
    previous = current.read_text(encoding="utf-8").strip() if current.exists() else ""
    if previous and previous != brief:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        write_text(f"brief-history/{stamp}.md", previous + "\n")
    write_text("decision-brief.md", brief + "\n")
    print("Saved the dashboard decision brief.")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def verified_tls_context():
    paths = ssl.get_default_verify_paths()
    macos_bundle = Path("/etc/ssl/cert.pem")
    if (sys.platform == "darwin" and not (paths.cafile or paths.capath)
            and "SSL_CERT_FILE" not in os.environ and "SSL_CERT_DIR" not in os.environ
            and macos_bundle.is_file()):
        return ssl.create_default_context(cafile=str(macos_bundle))
    return ssl.create_default_context()


def kite_settings(names):
    try:
        lines = (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        lines = []
    credentials = {}
    for line in lines:
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        canonical = names.get(name.strip().lower())
        if not separator or canonical is None or os.environ.get(canonical):
            continue
        try:
            parts = shlex.split(value, comments=True)
            if len(parts) > 1:
                raise ValueError
        except ValueError:
            raise ValueError(f"Malformed .env value for {canonical}. Use one value per line.") from None
        credentials[canonical] = parts[0] if parts else ""
    return {name: os.environ.get(name) or credentials.get(name) for name in names.values()}


def kite_credentials():
    settings = kite_settings({
        "kite_api_key": "KITE_API_KEY", "zerodha_api_key": "KITE_API_KEY",
        "kite_api_secret": "KITE_API_SECRET", "zerodha_api_secret": "KITE_API_SECRET",
    })
    return settings["KITE_API_KEY"], settings["KITE_API_SECRET"]


def kite_request(path, *, data=None, token=None):
    headers = {"X-Kite-Version": "3"}
    if token is not None:
        headers["Authorization"] = f"token {token}"
    request = Request(KITE_API + path, data=data, headers=headers)
    try:
        opener = build_opener(NoRedirect(), HTTPSHandler(context=verified_tls_context()))
        with opener.open(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("Kite authorization failed. Check the app credentials and sign in again.") from None
        raise ValueError(f"Kite returned HTTP {error.code}.") from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            raise ValueError("Kite TLS certificate verification failed. Check Python's CA bundle or SSL_CERT_FILE.") from None
        raise
    if payload.get("status") != "success":
        raise ValueError("Kite returned an unsuccessful response.")
    return payload["data"]


def get_access_token(api_key, secret):
    token = kite_settings({"kite_access_token": "KITE_ACCESS_TOKEN"})["KITE_ACCESS_TOKEN"]
    if token:
        return token
    if not sys.stdin.isatty():
        raise ValueError("Run sync-kite in your terminal to sign in, or inject KITE_ACCESS_TOKEN for this session.")
    secret = secret or getpass("Kite API secret: ")
    return exchange_kite_token(api_key, secret, prompt_kite_redirect(kite_login_url(api_key)))


def kite_login_url(api_key, state=None):
    params = {"v": "3", "api_key": api_key}
    if state is not None:
        params["redirect_params"] = urlencode({"state": state})
    return f"https://kite.zerodha.com/connect/login?{urlencode(params)}"


def prompt_kite_redirect(login_url=None):
    if login_url:
        print(f"Open {login_url} in your browser.")
    return getpass("Paste the redirect URL or its request_token: ").strip()


def exchange_kite_token(api_key, secret, redirected):
    if not secret:
        raise ValueError("A Kite API secret is required for sign-in.")
    request_token = (
        parse_qs(urlsplit(redirected).query).get("request_token", [""])[0]
        if "://" in redirected else redirected
    )
    if not request_token:
        raise ValueError("No request_token found in the Kite redirect.")
    checksum = hashlib.sha256(f"{api_key}{request_token}{secret}".encode()).hexdigest()
    body = urlencode({"api_key": api_key, "request_token": request_token, "checksum": checksum})
    return kite_request("/session/token", data=body.encode())["access_token"]


def wait_for_kite_redirect(callback, api_key):
    state = secrets.token_urlsafe(32)
    redirect = None
    callback_paths = {"/", callback.path}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def do_GET(self):
            nonlocal redirect
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            if url.path not in callback_paths or query.get("state") != [state]:
                self.send_error(404)
                return
            redirect = f"http://{callback.netloc}{self.path}"
            message = b"Callback received. Return to your terminal to check the sign-in result."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    with HTTPServer(("127.0.0.1", callback.port or 80), CallbackHandler) as server:
        login_url = kite_login_url(api_key, state)
        print("Opening Kite Connect. Complete sign-in in your browser.", flush=True)
        if not webbrowser.open(login_url):
            print(f"Open {login_url} in your browser.", flush=True)
        deadline = monotonic() + 120
        while redirect is None and (remaining := deadline - monotonic()) > 0:
            server.timeout = remaining
            server.handle_request()
    return redirect


def login_kite(manual=False):
    if not sys.stdin.isatty():
        raise ValueError("Run kite-login in an interactive terminal.")
    api_key, secret = kite_credentials()
    if not api_key or not secret:
        raise ValueError("Set the Kite API key and secret in .env before signing in.")
    callback_url = kite_settings({"callback_url": "CALLBACK_URL"})["CALLBACK_URL"]
    callback = urlsplit(callback_url or KITE_LOCAL_CALLBACK)
    redirect = None
    if (not manual and callback.scheme == "http"
            and callback.hostname in ("127.0.0.1", "localhost")):
        try:
            redirect = wait_for_kite_redirect(callback, api_key)
        except OSError as error:
            print(f"Couldn't listen for the local callback ({error}). Using manual sign-in.")
        else:
            if redirect is None:
                print("No local callback reached the terminal. Using manual sign-in.")
    if redirect is None:
        login_url = kite_login_url(api_key)
        webbrowser.open(login_url)
        redirect = prompt_kite_redirect(login_url)
    if parse_qs(urlsplit(redirect).query).get("status") == ["error"]:
        raise ValueError("Kite sign-in was unsuccessful. Run kite-login to try again.")
    token = exchange_kite_token(api_key, secret, redirect)
    if not isinstance(token, str) or not token or any(c in token for c in "\n\r\0"):
        raise ValueError("Kite returned an invalid access token.")

    env_path = ROOT / ".env"
    try:
        env_text = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        env_text = ""
    setting = f"KITE_ACCESS_TOKEN={shlex.quote(token)}"
    env_text, matches = re.subn(
        r"(?im)^([ \t\ufeff]*(?:export[ \t]+)?)[ \t]*KITE_ACCESS_TOKEN[ \t]*=[^\n]*",
        lambda match: match[1] + setting,
        env_text,
    )
    if not matches:
        separator = "\n" if env_text and not env_text.endswith("\n") else ""
        env_text += separator + setting + "\n"
    replace_text(env_path, env_text)
    print("Saved KITE_ACCESS_TOKEN in .env.")


def save_kite_holdings(holdings, as_of):
    fields = ("tradingsymbol", "exchange", "isin", "quantity", "t1_quantity", "used_quantity",
              "average_price", "last_price", "pnl", "discrepancy", "collateral_quantity", "mtf")
    rows = [{key: row[key] for key in fields if key in row} for row in holdings]
    snapshot = {"source": "Zerodha Kite", "as_of": as_of, "holdings": rows}
    view = portfolio_summary(snapshot)
    day = datetime.fromisoformat(snapshot["as_of"]).astimezone(IST).date()
    write_json(f"snapshots/{day}.json", snapshot)
    write_json("holdings.json", snapshot)
    print(f"Saved {len(rows)} holdings at {snapshot['as_of']} ({view['unpriced_count']} without usable marks).")


def sync_kite(resources=("holdings",)):
    endpoints = [(name, KITE_READ_APIS[name]) for name in dict.fromkeys(resources)]
    api_key, secret = kite_credentials()
    if not api_key and sys.stdin.isatty():
        api_key = getpass("Kite API key: ").strip()
    if not api_key:
        raise ValueError("KITE_API_KEY is required.")
    token = f"{api_key}:{get_access_token(api_key, secret)}"
    for name, (path, _, response_type) in endpoints:
        try:
            data = kite_request(path, token=token)
            if not isinstance(data, response_type):
                raise ValueError("Kite returned an unexpected response format.")
        except (ValueError, URLError, TimeoutError) as error:
            raise ValueError(f"{name}: {error}") from None
        as_of = now()
        if name == "holdings":
            save_kite_holdings(data, as_of)
        else:
            filename = f"kite/{name}.json"
            write_json(filename, {"source": "Zerodha Kite", "as_of": as_of, "data": data})
            print(f"Saved {name} at {as_of} to {DATA.name}/{filename}.")


def portfolio_summary(snapshot):
    rows = []
    for raw in snapshot["holdings"]:
        settled = raw["quantity"]
        pending = raw.get("t1_quantity", 0)
        sold = raw.get("used_quantity", 0)
        # Kite already reduces quantity for executed CNC sells.
        units = settled + pending
        if units <= 0 and not ((raw.get("mtf") or {}).get("quantity") or raw.get("discrepancy")):
            continue
        price = money(raw["last_price"]) if raw.get("last_price") is not None else None
        needs_review = bool(raw.get("discrepancy") or (raw.get("mtf") or {}).get("quantity"))
        value = units * price if price and units > 0 and not needs_review else None
        pnl = raw.get("pnl") if not needs_review and value is not None else None
        rows.append({
            "exchange": raw["exchange"], "symbol": raw["tradingsymbol"], "isin": raw.get("isin"),
            "settled": settled, "pending": pending, "sold": sold, "units": units,
            "collateral": raw.get("collateral_quantity", 0), "review": needs_review,
            "price": float(price) if price else None, "value_inr": float(value) if value is not None else None,
            "broker_pnl_inr": pnl,
        })
    marked = [row for row in rows if row["value_inr"] is not None]
    total = sum(Decimal(str(row["value_inr"])) for row in marked)
    for row in rows:
        row["weight_pct"] = (
            round(float(Decimal(str(row["value_inr"])) / total * 100), 2)
            if row["value_inr"] is not None and total else None
        )
    rows.sort(key=lambda row: row["value_inr"] or 0, reverse=True)
    return {
        "source": snapshot["source"], "as_of": snapshot["as_of"], "marked_value_inr": float(total),
        "unpriced_count": len(rows) - len(marked), "holdings": rows,
    }


def https_url(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def date_from_feed(value):
    if not value:
        return None
    for parse in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            date = parse(value)
            if date.tzinfo is not None:
                return date.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def parse_feed(body, source):
    root = ElementTree.fromstring(body)
    if root.tag not in {"rss", "{http://www.w3.org/2005/Atom}feed"}:
        raise ValueError("Expected an RSS or Atom feed.")
    for item in root.findall("./channel/item") + root.findall("{*}entry"):
        link_element = next((node for node in item.findall("{*}link")
                             if node.get("rel", "alternate") == "alternate"), None)
        if link_element is None:
            continue
        link = (link_element.get("href") or link_element.text or "").strip()
        title = " ".join((item.findtext("{*}title") or "").split())
        date = item.findtext("{*}pubDate") or item.findtext("{*}published") or item.findtext("{*}updated")
        if title and https_url(link):
            yield {"title": title, "url": link, "source": source, "published_at": date_from_feed(date)}


def sync_news(feeds):
    entries = (read_json("news.json") or {}).get("items", [])
    by_title = {re.sub(r"\W+", " ", item["title"].casefold()).strip(): item for item in entries}
    refreshed = []
    errors = []
    for feed in dict.fromkeys([NSE_FEED, *feeds]):
        if not https_url(feed):
            raise ValueError("Use HTTPS RSS or Atom feed URLs.")
        source = urlsplit(feed).hostname
        try:
            request = Request(feed, headers={"User-Agent": "StockHelpers/1.0"})
            with urlopen(request, timeout=15, context=verified_tls_context()) as response:
                body = response.read(MAX_FEED_BYTES + 1)
            if len(body) > MAX_FEED_BYTES:
                raise ValueError("Feed exceeds the size limit.")
            for item in parse_feed(body, source):
                key = re.sub(r"\W+", " ", item["title"].casefold()).strip()
                previous = by_title.get(key)
                if previous is None or (item["published_at"] or "") > (previous["published_at"] or ""):
                    by_title[key] = item
            refreshed.append(source)
        except (OSError, ValueError, ElementTree.ParseError) as error:
            errors.append(source)
            detail = f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__
            print(f"Could not refresh {source} ({detail}).", file=sys.stderr)
    if not refreshed:
        raise ValueError("News refresh failed. Any previous digest has been preserved.")
    items = sorted(by_title.values(), key=lambda item: item["published_at"] or "", reverse=True)[:300]
    write_json("news.json", {"as_of": now(), "items": items, "refreshed": refreshed, "failed": errors})
    print(f"Saved {len(items)} headlines. Refreshed {', '.join(refreshed)}.")


def money(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("All sizing and portfolio inputs must be numbers.") from None
    if not number.is_finite() or number < 0:
        raise ValueError("Amounts must be finite and non-negative.")
    return number


def size_position(values):
    entry, invalidation, equity, cash, stock, sector, exposure, sector_limit, risk, cost = map(money, values)
    if not 0 < invalidation < entry or equity <= 0:
        raise ValueError("Require positive equity and an invalidation price between zero and the entry price.")
    if not all(0 < limit <= 100 for limit in (exposure, sector_limit, risk)):
        raise ValueError("Exposure, sector and risk limits must be percentages in (0, 100].")
    if stock > sector or sector > equity:
        raise ValueError("Require existing stock value ≤ sector value ≤ portfolio equity.")
    per_share_loss = entry - invalidation + cost
    limits = {
        "cash": int(cash // (entry + cost)),
        "issuer exposure": int(max(0, equity * exposure / 100 - stock) // entry),
        "sector exposure": int(max(0, equity * sector_limit / 100 - sector) // entry),
        "scenario loss": int((equity * risk / 100) // per_share_loss),
    }
    shares = min(limits.values())
    return {"max_shares": shares, "cash_required_inr": str(shares * (entry + cost)),
            "exposure_added_inr": str(shares * entry), "modeled_loss_inr": str(shares * per_share_loss),
            "binding_limits": [label for label, limit in limits.items() if limit == shares]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("kite-apis", help="List available read-only Kite endpoints.")
    login = commands.add_parser("kite-login", help="Open Kite Connect and save the session token in .env.")
    login.add_argument("--manual", action="store_true", help="Paste the redirect URL instead of listening locally.")
    kite = commands.add_parser("sync-kite", help="Fetch one or more Kite snapshots after one sign-in.")
    kite.add_argument("resources", nargs="*", metavar="RESOURCE",
                      help="Endpoint names from kite-apis. Defaults to holdings.")
    commands.add_parser("summary", help="Print holdings metrics for the latest snapshot.")
    brief = commands.add_parser("publish-brief", help="Publish a decision brief and archive the previous one.")
    brief.add_argument("file", type=Path, nargs="?", help="Markdown file. Defaults to standard input.")
    news = commands.add_parser("sync-news", help="Refresh NSE announcements and optional RSS/Atom feeds.")
    news.add_argument("--feed", action="append", default=[], help="Additional HTTPS feed URL. Repeat as needed.")
    size = commands.add_parser("size", help="Calculate the whole-share ceiling for an entry scenario.")
    for name in ("entry", "invalidation", "equity", "cash", "stock-value", "sector-value",
                 "issuer-limit-pct", "sector-limit-pct", "risk-pct", "cost-per-share"):
        size.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    if args.command == "sync-kite" and any(name not in KITE_READ_APIS for name in args.resources):
        parser.error("Unknown Kite resource. Run kite-apis for available names.")
    try:
        if args.command == "kite-apis":
            for name, (path, description, _) in KITE_READ_APIS.items():
                print(f"{name:14} GET {path:23} {description}")
        elif args.command == "kite-login":
            login_kite(manual=args.manual)
        elif args.command == "sync-kite":
            sync_kite(args.resources or ("holdings",))
        elif args.command == "publish-brief":
            publish_brief(args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read())
        elif args.command == "summary":
            snapshot = read_json("holdings.json")
            if snapshot is None:
                raise ValueError("No Kite holdings snapshot yet. Run sync-kite.")
            print(json.dumps(portfolio_summary(snapshot), indent=2))
        elif args.command == "sync-news":
            sync_news(args.feed)
        elif args.command == "size":
            values = (args.entry, args.invalidation, args.equity, args.cash, args.stock_value,
                      args.sector_value, args.issuer_limit_pct, args.sector_limit_pct,
                      args.risk_pct, args.cost_per_share)
            print(json.dumps(size_position(values), indent=2))
    except (KeyboardInterrupt, EOFError):
        parser.exit(1, "Cancelled.\n")
    except (ValueError, KeyError, TypeError, InvalidOperation, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

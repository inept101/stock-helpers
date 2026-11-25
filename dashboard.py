"""Serve the portfolio dashboard on this computer."""

import argparse
import csv
import re
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import backtest
from stock_helpers import DATA, IST, https_url, portfolio_summary, read_json, write_text

SAMPLE = {
    "source": "Demo · fictional holdings", "as_of": "Sample snapshot",
    "holdings": [
        {"exchange": "NSE", "tradingsymbol": "DEMOALPHA", "quantity": 100, "last_price": 1540, "pnl": 11800},
        {"exchange": "NSE", "tradingsymbol": "DEMOBETA", "quantity": 80, "last_price": 910, "pnl": -2800},
        {"exchange": "BSE", "tradingsymbol": "DEMOGAMMA", "quantity": 70, "last_price": 690, "pnl": 3200},
    ],
}

CSS = """
:root {
    color-scheme: dark;
    --bg: #0e151e;
    --surface: #15202e;
    --raised: #1b2938;
    --border: #354759;
    --control-border: #63798c;
    --text: #edf3f8;
    --muted: #adbfce;
    --accent: #91e3c3;
    --positive: #91e3c3;
    --negative: #ffb5ad;
    --warning: #f3cf8f;
    --radius: 12px;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 1rem/1.55 system-ui, sans-serif; }
::selection { color: var(--bg); background: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
a { color: var(--accent); text-underline-offset: 4px; }
a:hover { color: var(--text); }
p { margin: 0; }
h1, h2, h3, h4 { margin: 0; line-height: 1.2; font-weight: 650; }
h1 { font-size: 2rem; letter-spacing: -.035em; }
h2 { font-size: 1.25rem; letter-spacing: -.022em; }
h3 { font-size: 1.125rem; letter-spacing: -.016em; }
h4 { font-size: 1rem; }
small, .muted, dt { color: var(--muted); }
small, dt { font-size: .875rem; }
.skip-link { position: fixed; z-index: 2; top: 12px; left: 12px; padding: 8px 14px; background: var(--surface); }
.skip-link:not(:focus) { clip-path: inset(50%); }
.masthead { position: sticky; top: 0; z-index: 1; background: var(--bg); border-bottom: 1px solid var(--border); }
.toolbar, main { width: min(100%, 1250px); margin-inline: auto; padding-inline: 32px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.brand { font-weight: 720; color: var(--text); text-decoration: none; white-space: nowrap; }
nav { display: flex; gap: 20px; min-width: 0; overflow-x: auto; }
nav a { display: flex; align-items: center; min-height: 56px; color: var(--muted); text-decoration: none;
    white-space: nowrap; font-size: .875rem; border-bottom: 2px solid transparent; }
nav a:hover, nav a:focus-visible { color: var(--text); border-color: var(--accent); }
nav a:focus-visible { outline-offset: -4px; }
main { padding-block: 30px 56px; }
.intro, .section-head, .run-heading { display: flex; justify-content: space-between; align-items: baseline;
    gap: 12px 24px; flex-wrap: wrap; }
.intro { margin-bottom: 18px; }
.intro p { font-size: .875rem; }
.panel { scroll-margin-top: 80px; margin-top: 22px; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--radius); min-width: 0; }
.panel:target { border-color: var(--accent); }
.section-head { padding: 20px 22px 14px; }
.section-body { padding: 0 22px 20px; }
.section-head .muted { font-size: .875rem; }
.metrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); margin: 0;
    border-block: 1px solid var(--border); }
.metrics div { min-width: 0; padding: 12px 16px; }
.metrics div + div { border-inline-start: 1px solid var(--border); }
.metrics dd { margin: 3px 0 0; font-size: 1.25rem; font-weight: 660; }
.metrics dd, .num { font-variant-numeric: tabular-nums; }
.holdings-stats { background: var(--raised); }
.table { overflow: auto; scrollbar-color: var(--border) var(--surface); }
.table:focus-visible { outline-offset: -3px; }
table { width: 100%; border-collapse: collapse; min-width: 620px; }
th, td { padding: 11px 14px; text-align: start; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-size: .875rem; font-weight: 620; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: var(--raised); }
td:first-child, th:first-child { padding-inline-start: 22px; }
td:last-child, th:last-child { padding-inline-end: 22px; }
.num { text-align: end; white-space: nowrap; }
.up { color: var(--positive); }
.down { color: var(--negative); }
.warning { color: var(--warning); }
.holding-symbol small { display: block; }
progress { display: inline-block; width: 52px; height: 5px; margin-inline-start: 8px;
    accent-color: var(--accent); vertical-align: middle; }
.brief { overflow-wrap: anywhere; }
.brief p { max-width: 72ch; margin-block: 10px; }
.brief h4 { margin-block: 22px 8px; }
.brief .table { margin-block: 14px; border-block: 1px solid var(--border); }
.brief th, .brief td { vertical-align: top; }
.brief td:nth-child(-n+3) { min-width: 90px; }
.brief td:last-child { min-width: 280px; }
.brief td:first-child, .brief th:first-child { padding-inline-start: 10px; }
details { border-top: 1px solid var(--border); margin-top: 12px; }
details + details { margin-top: 0; }
summary { cursor: pointer; padding: 10px 0; min-height: 44px; font-weight: 620; }
summary:hover { color: var(--accent); }
ul { padding-left: 22px; margin-block: 8px; }
li { margin-block: 7px; }
.news-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 0 24px; list-style: none;
    padding: 0; margin-block: 10px; }
.news-list li { padding-block: 12px; border-top: 1px solid var(--border); margin: 0; }
.news-list a { font-weight: 600; }
.news-list p + p { margin-top: 4px; }
.run-heading { margin-block: 16px 8px; }
.run-context { margin-top: 8px; font-size: .875rem; }
.test-stats { margin-top: 12px; grid-template-columns: repeat(6,minmax(0,1fr)); }
.chart { margin: 16px 0; padding: 12px 15px; background: var(--bg); border-radius: var(--radius); }
.chart figcaption { font-weight: 620; }
.axis { display: flex; justify-content: space-between; gap: 12px; }
.plot { display: grid; grid-template-columns: max-content minmax(0,1fr); align-items: stretch; gap: 12px; margin-top: 9px; }
.scale { display: flex; flex-direction: column; justify-content: space-between; height: 126px;
    font-variant-numeric: tabular-nums; }
.bars { display: flex; align-items: end; gap: 1px; height: 126px; border-bottom: 1px solid var(--border); }
.bars span { flex: 1; min-width: 0; background: var(--accent); opacity: .82; }
.run-form { background: var(--raised); padding-inline: 14px; border: 1px solid var(--border); border-radius: var(--radius); }
.test-form { display: grid; grid-template-columns: repeat(auto-fit,minmax(170px,1fr)); gap: 12px; padding-block: 7px 14px; }
.test-form .file-field { grid-column: span 2; }
.file-field small { display: block; margin-top: 5px; }
label { display: grid; gap: 5px; align-content: start; min-width: 0; font-size: .875rem; color: var(--muted); }
input, button { min-width: 0; min-height: 42px; padding: 7px 10px; border: 1px solid var(--control-border);
    border-radius: 8px; color: var(--text); background: var(--bg); font: inherit; }
input:hover { border-color: var(--muted); }
input::placeholder { color: var(--muted); }
input::file-selector-button { font: inherit; color: var(--text); background: var(--raised);
    border: 1px solid var(--control-border); border-radius: 5px; margin-inline-end: 8px; padding: 2px 6px; }
button { color: var(--bg); background: var(--accent); border-color: var(--accent); cursor: pointer; font-weight: 700; }
button:hover { background: var(--text); border-color: var(--text); }
button:active { background: var(--positive); }
.form-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; padding-bottom: 14px; }
.error { margin-top: 8px; padding: 9px 12px; border: 1px solid var(--negative); border-radius: 8px; }
.empty { padding-block: 14px; }
code { overflow-wrap: anywhere; }
@media (min-width: 761px) and (max-width: 1020px) {
    .test-stats { grid-template-columns: repeat(3,minmax(0,1fr)); }
    .test-stats div:nth-child(4) { border-inline-start: 0; }
    .test-stats div:nth-child(n+4) { border-top: 1px solid var(--border); }
}
@media (max-width: 760px) {
    .toolbar, main { padding-inline: 16px; }
    .masthead { position: static; }
    .toolbar { display: block; }
    .brand { display: inline-block; padding-top: 8px; }
    nav { gap: 0 16px; flex-wrap: wrap; }
    nav a { min-height: 44px; }
    main { padding-top: 22px; }
    .panel { scroll-margin-top: 12px; }
    .section-head, .section-body { padding-inline: 14px; }
    .metrics { grid-template-columns: repeat(3,minmax(0,1fr)); }
    .metrics dd { font-size: 1rem; }
    .metrics div { padding: 9px; }
    .test-stats { grid-template-columns: repeat(2,minmax(0,1fr)); }
    .test-stats div:nth-child(odd) { border-inline-start: 0; }
    .test-stats div:nth-child(n+3) { border-top: 1px solid var(--border); }
    .news-list { grid-template-columns: 1fr; }
    .test-form .file-field { grid-column: 1 / -1; }
}
@media (max-width: 420px) {
    .holdings-stats { grid-template-columns: 1fr 1fr; }
    .holdings-stats div:first-child { grid-column: 1 / -1; border-bottom: 1px solid var(--border); }
    .holdings-stats div:nth-child(2) { border-inline-start: 0; }
    .plot { gap: 8px; }
    .bars, .scale { height: 90px; }
}
"""


def inr(value):
    if value is None:
        return "—"
    sign = "−" if value < 0 else ""
    whole, fraction = f"{abs(value):.2f}".split(".")
    prefix, suffix = whole[:-3], whole[-3:]
    pairs = []
    while prefix:
        pairs.insert(0, prefix[-2:])
        prefix = prefix[:-2]
    return f"{sign}₹{','.join([*pairs, suffix])}.{fraction}"


def holdings_html(summary):
    rows = []
    for item in summary["holdings"]:
        weight = item["weight_pct"]
        weight_cell = ("—" if weight is None else
                       f'{weight:.2f}% <progress aria-hidden="true" value="{weight}" max="100"></progress>')
        pnl = item["broker_pnl_inr"]
        pnl_class = "down" if pnl is not None and pnl < 0 else "up"
        notes = []
        if item["review"]:
            notes.append("Needs reconciliation")
        if item["pending"]:
            notes.append(f'{item["pending"]} pending')
        if item["collateral"]:
            notes.append(f'{item["collateral"]} collateral')
        label = f'<small>{escape(" · ".join(notes))}</small>' if notes else ""
        price = inr(item["price"])
        mark = item.get("market_mark")
        if mark is not None:
            price = (f'<a href="{escape(mark["url"])}" rel="noreferrer">{price}</a>'
                     f'<br><small>{escape(local_date(mark["as_of"]))}</small>')
        rows.append(
            f'<tr><td class="holding-symbol"><strong>{escape(item["symbol"])}</strong>'
            f'<small>{escape(item["exchange"])}</small>{label}</td>'
            f'<td class="num">{item["units"]}</td><td class="num">{price}</td>'
            f'<td class="num">{inr(item["value_inr"])}</td>'
            f'<td class="num {pnl_class}">{inr(pnl)}</td><td class="num">{weight_cell}</td></tr>'
        )
    if not rows:
        return '<p class="section-body muted">No open holdings in this snapshot.</p>'
    return (
        '<div class="table" role="region" aria-label="Holdings table" tabindex="0">'
        '<table aria-label="Equity holdings"><thead><tr><th scope="col">Holding</th>'
        '<th scope="col" class="num">Units</th><th scope="col" class="num">Last price</th>'
        '<th scope="col" class="num">Marked value</th><th scope="col" class="num">Kite P&amp;L at sync</th>'
        '<th scope="col" class="num">Weight of marked holdings</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table></div>"
    )


def local_date(value):
    if not value:
        return "Publication time unavailable"
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    if timestamp.tzinfo is None:
        return timestamp.strftime("%d %b %Y")
    return timestamp.astimezone(IST).strftime("%d %b %Y · %H:%M IST")


def marked_holdings(snapshot, market_quotes):
    synced_at = datetime.fromisoformat(snapshot["as_of"])
    marks = {
        (item["exchange"], item["symbol"]): item for item in market_quotes
        if https_url(item["url"]) and item["price"] > 0
        and datetime.fromisoformat(item["as_of"]) > synced_at
    }
    rows = []
    for row in snapshot["holdings"]:
        mark = marks.get((row["exchange"], row["tradingsymbol"]))
        rows.append({**row, "last_price": mark["price"]} if mark else row)
    summary = portfolio_summary({**snapshot, "holdings": rows})
    for row in summary["holdings"]:
        mark = marks.get((row["exchange"], row["symbol"]))
        if mark is not None and row["value_inr"] is not None:
            row["market_mark"] = mark
    return summary


INLINE = re.compile(r"\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`")


def inline_html(value):
    parts = []
    end = 0
    for match in INLINE.finditer(value):
        parts.append(escape(value[end:match.start()]))
        label, url, bold, code = match.groups()
        if url and https_url(url):
            parts.append(f'<a href="{escape(url)}" rel="noreferrer">{escape(label)}</a>')
        elif bold:
            parts.append(f"<strong>{escape(bold)}</strong>")
        elif code:
            parts.append(f"<code>{escape(code)}</code>")
        else:
            parts.append(escape(match.group()))
        end = match.end()
    parts.append(escape(value[end:]))
    return "".join(parts)


def brief_html(markdown):
    blocks = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if line.startswith("|"):
            rows = [line]
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            if len(rows) < 2 or not re.fullmatch(r"[|:\- ]+", rows[1]):
                blocks.extend(f"<p>{inline_html(row)}</p>" for row in rows)
                continue
            header = "".join(f'<th scope="col">{inline_html(cell.strip())}</th>'
                             for cell in rows[0].strip("|").split("|"))
            body = []
            for row in rows[2:]:
                cells = "".join(f"<td>{inline_html(cell.strip())}</td>" for cell in row.strip("|").split("|"))
                body.append(f"<tr>{cells}</tr>")
            blocks.append(f'<div class="table" role="region" aria-label="Decision table" tabindex="0">'
                          f'<table><thead><tr>{header}</tr></thead>'
                          f'<tbody>{"".join(body)}</tbody></table></div>')
        elif line.startswith("## "):
            blocks.append(f"<h4>{inline_html(line[3:])}</h4>")
        elif line.startswith("- "):
            items = [f"<li>{inline_html(line[2:])}</li>"]
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(f"<li>{inline_html(lines[index].strip()[2:])}</li>")
                index += 1
            blocks.append(f'<ul>{"".join(items)}</ul>')
        elif line:
            blocks.append(f"<p>{inline_html(line)}</p>")
    return '<div class="brief">' + "".join(blocks) + "</div>"


def load_briefs():
    current = DATA / "decision-brief.md"
    archives = sorted((DATA / "brief-history").glob("*.md"), reverse=True)
    briefs = {}
    for path in [current, *archives]:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8").strip()
        for section in re.split(r"(?m)(?=^# )", content):
            title, _, body = section.strip().partition("\n")
            if title.startswith("# "):
                briefs.setdefault((title[2:], body.strip()), None)
            elif title:
                briefs.setdefault(("Portfolio decision brief", section.strip()), None)
    return list(briefs)


def news_html(news, coverage):
    featured = []
    for item in coverage.get("items", []):
        if https_url(item["url"]):
            featured.append(
                f'<li><small>{escape(item["symbol"])} · {escape(local_date(item["published_at"]))}</small>'
                f'<p><a href="{escape(item["url"])}" rel="noreferrer">{escape(item["title"])}</a></p>'
                f'<p class="muted">{escape(item["summary"])}</p></li>'
            )
    result = ""
    if featured:
        result = (f'<p class="muted">Company filings reviewed {escape(local_date(coverage["as_of"]))}</p>'
                  f'<ul class="news-list">{"".join(featured)}</ul>')
    if news is None:
        return result + ('<p class="muted">Market feed has no saved refresh. Run '
                         '<code>python3 stock_helpers.py sync-news</code> to collect headlines.</p>')
    items = []
    for item in news["items"][:12]:
        link = item["url"]
        if https_url(link):
            date = local_date(item["published_at"])
            items.append(
                f'<li><a href="{escape(link)}" rel="noreferrer">{escape(item["title"])}</a>'
                f'<br><small>{escape(item["source"])} · {escape(date)}</small></li>'
            )
    metadata = f'<p class="muted">Last feed refresh {escape(local_date(news["as_of"]))}</p>'
    if news["failed"]:
        metadata += f'<p class="muted">Refresh unavailable for {escape(", ".join(news["failed"]))}.</p>'
    listing = "<ul>" + "".join(items) + "</ul>" if items else "<p>No headlines collected.</p>"
    return result + f"<details><summary>Market feed</summary>{metadata}{listing}</details>"


def equity_chart(curve):
    values = [point["equity"] for point in curve]
    low, high = min(values), max(values)
    sample_size = min(100, len(values))
    sample = [values[i * (len(values) - 1) // max(1, sample_size - 1)] for i in range(sample_size)]
    bars = "".join(f'<span style="height:{max(1, 100 * (value - low) / (high - low)) if high > low else 50:.2f}%"></span>'
                   for value in sample)
    return (f'<figure class="chart"><figcaption>Strategy equity</figcaption><div class="plot">'
            f'<div class="scale"><small>{inr(high)}</small><small>{inr(low)}</small></div>'
            f'<div><div class="bars" aria-hidden="true">{bars}</div><div class="axis">'
            f'<small>{escape(curve[0]["date"])}</small><small>{escape(curve[-1]["date"])}</small></div></div></div></figure>')


def backtest_form(result, error, options):
    settings = result["settings"] if result else vars(backtest.Settings())
    fields = (
        ("capital", "Paper capital (₹)", 10000, 100000000, 1),
        ("risk", "Risk per trade (₹)", 1, 10000, 1),
        ("reward", "Reward target (R)", 1, 20, .1),
        ("fee_bps", "Fees per side (bps)", 0, 500, .1),
        ("slip_bps", "Slippage per side (bps)", 0, 500, .1),
    )
    numeric = "".join(
        f'<label>{label}<input name="{name}" type="number" min="{minimum}" max="{maximum}" '
        f'step="{step}" value="{escape(str(options.get(name, settings[name])))}" required></label>'
        for name, label, minimum, maximum, step in fields
    )
    problem = ('<p class="down error" role="alert">'
               f'{escape(error)} If you used a CSV, select it again before submitting.</p>') if error else ""
    expanded = " open" if error or result is None else ""
    return f"""<details class="run-form"{expanded}><summary>Run a backtest</summary>
{problem}<form action="/backtest#backtest" method="post" enctype="multipart/form-data">
<div class="test-form">
<div class="file-field"><label>Daily OHLC CSV<input name="candles" type="file" accept=".csv,text/csv" aria-describedby="candle-help"></label>
<small id="candle-help">Leave empty to use synthetic data. CSV columns: date, open, high, low, close.</small></div>
<label>Symbol or data label<input name="symbol" maxlength="50" placeholder="NIFTYBEES" value="{escape(options.get("symbol", ""))}"></label>
{numeric}
<label>Test start<input name="start" type="date" value="{escape(options.get("start", ""))}"></label>
<label>Test end<input name="end" type="date" value="{escape(options.get("end", ""))}"></label>
</div><div class="form-actions"><button type="submit">Run simulation</button></div></form></details>"""


def backtest_html(result, interactive, error="", options=None):
    form = ""
    if interactive:
        form = backtest_form(result, error, options or {})
    elif not result:
        form = '<p class="muted">Open the local dashboard to run a simulation.</p>'
    setup = ('<p class="muted">Buy the next session after a 20-session breakout above the 50-day average. '
             'The model uses a 2 ATR stop, a reward target, and a ₹10,000 strategy drawdown halt.</p>'
             '<details><summary>How to read the results</summary><p>Profit factor compares total net gains '
             'on winning trades with total net losses on losing trades. Average win/loss compares the size '
             'of a typical win with a typical loss. Win rate is the percentage of trades that made money. '
             'The drawdown halt is measured from the prior peak in strategy equity. A gap can exceed it.</p></details>')
    if not result:
        return form + '<p class="muted empty">No simulation results saved yet.</p>' + setup
    metrics = result["metrics"]
    settings = result["settings"]
    labels = ("Net P&L", "Max drawdown", "Profit factor", "Avg. win / loss", "Win rate", "Closed trades")
    values = (
        inr(metrics["net_pnl"]), inr(metrics["max_drawdown"]),
        f'{metrics["profit_factor"]:.2f}×' if metrics["profit_factor"] is not None else "—",
        f'{metrics["payoff"]:.2f}×' if metrics["payoff"] is not None else "—",
        f'{metrics["win_rate"]:.1f}%' if metrics["win_rate"] is not None else "—", metrics["trades"],
    )
    pnl_class = "down" if metrics["net_pnl"] < 0 else "up" if metrics["net_pnl"] > 0 else ""
    stats = "".join(f'<div><dt>{escape(label)}</dt><dd class="{pnl_class if i == 0 else ""}">{value}</dd></div>'
                    for i, (label, value) in enumerate(zip(labels, values)))
    status = "Drawdown limit not reached"
    if metrics["halted_on"]:
        status = f'Halted on {metrics["halted_on"]} · Overshoot {inr(metrics["limit_overshoot"])}'
    source = result["source"]
    disclosure = "Synthetic demo data. These figures illustrate the simulator."
    if source != "Synthetic demo":
        disclosure = f'Imported CSV · SHA-256 {source.split()[-1][:12]}'
    rows = "".join(
        f'<tr><td>{escape(t["entry_date"])}</td><td>{escape(t["exit_date"])}</td><td>{t["shares"]}</td>'
        f'<td>{inr(t["entry"])}</td><td>{inr(t["exit"])}</td><td class="num">{inr(t["pnl"])}</td>'
        f'<td class="num">{t["r"]:.2f}R</td><td>{escape(t["reason"])}</td></tr>'
        for t in reversed(result["trade_log"])
    )
    risk_class = "warning" if metrics["halted_on"] else "muted"
    return (form
            + f'<div class="run-heading"><h3>{escape(result["instrument"])} · {escape(result["strategy"])}</h3>'
            + f'<small>{escape(disclosure)}</small></div><dl class="metrics test-stats">{stats}</dl>'
            + f'<p class="run-context"><span class="{risk_class}">{escape(status)}</span> · '
              f'Capital {inr(settings["capital"])} · Risk/trade {inr(settings["risk"])}'
            + f' · Target {settings["reward"]:g}R</p>'
            + f'<p class="muted">Buy-and-hold P&amp;L {inr(metrics.get("buy_and_hold_pnl"))} · '
              f'Average trade {inr(metrics["avg_pnl"])} · Fees {settings["fee_bps"]:g} bps and '
              f'slippage {settings["slip_bps"]:g} bps per side</p>'
            + equity_chart(result["curve"])
            + '<details><summary>Trade log</summary><div class="table" role="region" '
              'aria-label="Trade log table" tabindex="0"><table><thead><tr>'
              '<th scope="col">Entry date</th><th scope="col">Exit date</th><th scope="col">Shares</th>'
              '<th scope="col">Entry</th><th scope="col">Exit</th><th scope="col">Net P&amp;L</th>'
              '<th scope="col">Result</th><th scope="col">Exit rule</th></tr></thead>'
            + f'<tbody>{rows or "<tr><td colspan=8>No closed trades</td></tr>"}</tbody></table></div></details>' + setup)


def render(demo, *, interactive=False, error="", options=None):
    snapshot = SAMPLE if demo else read_json("holdings.json")
    news = None if demo else read_json("news.json")
    coverage = {} if demo else read_json("research-news.json", {})
    test_result = None if demo else read_json("backtest.json")
    briefs = [] if demo else load_briefs()
    report = '<p class="muted">Run the Zerodha Portfolio skill to generate a decision brief.</p>'
    if briefs:
        title, body = briefs[0]
        report = f"<h3>{inline_html(title)}</h3>{brief_html(body)}"
    history = "".join(
        f"<details><summary>{inline_html(title)}</summary>{brief_html(body)}</details>"
        for title, body in briefs[1:]
    ) or '<p class="muted">Past briefs will appear here after a new one is published.</p>'
    status = "No saved Kite snapshot"
    portfolio = ('<p class="section-body muted">Run '
                 '<code>python3 stock_helpers.py sync-kite</code> to load your portfolio.</p>')
    if snapshot is not None:
        summary = (portfolio_summary(snapshot) if demo else
                   marked_holdings(snapshot, read_json("holdings-market-quotes.json", [])))
        status = f'{summary["source"]} snapshot · {local_date(summary["as_of"])}'
        labels = ("Marked holdings value", "Holdings", "Unpriced or unreconciled")
        values = (inr(summary["marked_value_inr"]), len(summary["holdings"]), summary["unpriced_count"])
        metrics = "".join(
            f'<div><dt>{label}</dt><dd>{value}</dd></div>'
            for label, value in zip(labels, values)
        )
        marked = sum("market_mark" in row for row in summary["holdings"])
        price_note = ""
        if marked:
            total = len(summary["holdings"])
            price_note = (f'<p class="section-body muted">Market quotes applied to {marked} of {total} holdings. '
                          'Quantities and Kite P&amp;L are from the last broker sync.</p>')
        portfolio = f'{price_note}<dl class="metrics holdings-stats">{metrics}</dl>{holdings_html(summary)}'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="same-origin"><title>Your Portfolio · Stock Helpers</title><style>{CSS}</style></head>
<body><a class="skip-link" href="#main">Skip to portfolio</a>
<header class="masthead"><div class="toolbar"><a class="brand" href="#main">Stock Helpers</a>
<nav aria-label="Dashboard sections"><a href="#holdings">Holdings</a><a href="#backtest">Backtesting</a>
<a href="#brief">Recommendations</a><a href="#history">History</a><a href="#news">News</a></nav></div></header>
<main id="main" tabindex="-1"><div class="intro"><h1>Your portfolio</h1><p class="muted">{escape(status)}</p></div>
<section class="panel" id="holdings" aria-labelledby="holdings-title">
<div class="section-head"><h2 id="holdings-title">Holdings</h2></div>{portfolio}</section>
<section class="panel" id="backtest" aria-labelledby="backtest-title">
<div class="section-head"><h2 id="backtest-title">Strategy backtest</h2><p class="muted">Paper trading</p></div>
<div class="section-body">{backtest_html(test_result, interactive, error, options)}</div></section>
<section class="panel" id="brief" aria-labelledby="brief-title"><div class="section-head">
<h2 id="brief-title">Latest recommendations</h2></div><div class="section-body">{report}</div></section>
<section class="panel" id="history" aria-labelledby="history-title"><div class="section-head">
<h2 id="history-title">Recommendation history</h2></div><div class="section-body">{history}</div></section>
<section class="panel" id="news" aria-labelledby="news-title"><div class="section-head">
<h2 id="news-title">News and filings</h2></div><div class="section-body">{news_html(news, coverage)}</div></section>
</main></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    demo = False

    def log_message(self, format, *args):
        # Kite redirect URLs can contain request tokens.
        return

    def do_GET(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        path = urlsplit(self.path).path
        if path == "/":
            body = render(self.demo, interactive=not self.demo).encode()
            content_type = "text/html; charset=utf-8"
        elif path == "/kite-callback" and not self.demo:
            body = b"Copy this URL into the running sync-kite command, then close this tab."
            content_type = "text/plain; charset=utf-8"
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_page(body, content_type)

    def do_POST(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host or self.headers.get("Origin") != f"http://{host}":
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.demo or urlsplit(self.path).path != "/backtest":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        options = {}
        try:
            count = int(self.headers.get("Content-Length", "0"))
            if not 0 < count <= backtest.MAX_BYTES + 8192:
                raise ValueError("Upload a candle CSV up to 2 MB.")
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data;") or "\n" in content_type or "\r" in content_type:
                raise ValueError("Use the dashboard's backtest form.")
            body = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\n\r\n".encode() + self.rfile.read(count)
            )
            fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                      for part in body.iter_parts()}
            options = {name: fields[name].decode().strip()
                       for name in ("symbol", "start", "end", "capital", "risk", "reward", "fee_bps", "slip_bps")}
            raw = fields.get("candles") or None
            settings = backtest.Settings(*(float(options[name])
                                          for name in ("capital", "risk", "reward", "fee_bps", "slip_bps")))
            name = options["symbol"][:50] or ("Imported equity" if raw is not None else "Fictional equity")
            backtest.save(backtest.run(raw, name, settings, options["start"], options["end"]))
        except (ValueError, OSError, KeyError, AttributeError, csv.Error) as error:
            body = render(False, interactive=True, error=str(error), options=options).encode()
            self.send_page(body, "text/html; charset=utf-8", HTTPStatus.BAD_REQUEST)
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/#backtest")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_page(self, body, content_type, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    preview = parser.add_mutually_exclusive_group()
    preview.add_argument("--demo", action="store_true", help="Show fictional holdings without reading personal data.")
    preview.add_argument("--demo-html", action="store_true", help="Print a standalone fictional preview.")
    preview.add_argument("--export", action="store_true", help="Save a private HTML snapshot in the data folder.")
    args = parser.parse_args()
    if args.demo_html:
        print(render(demo=True))
        return
    if args.export:
        write_text("dashboard.html", render(demo=False))
        print(f"Saved {DATA / 'dashboard.html'}")
        return
    DashboardHandler.demo = args.demo
    with ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler) as server:
        print(f"Dashboard at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

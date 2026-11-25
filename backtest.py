"""Daily, long-only paper backtesting for the Stock Helpers dashboard."""

import argparse
import csv
import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import StringIO
from math import floor, isfinite
from pathlib import Path
from statistics import mean

from stock_helpers import DATA, now, write_json

MAX_BYTES = 2_000_000
CSV_ALIASES = {
    "date": ("trade date", "timestamp", "traddt"),
    "open": ("open price", "opnpric"),
    "high": ("high price", "hghpric"),
    "low": ("low price", "lwpric"),
    "close": ("close price", "clspric"),
}
LOSS_LIMIT = 10_000
STRATEGY = "20-session breakout"


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Settings:
    capital: float = 500_000
    risk: float = 2_000
    reward: float = 3
    fee_bps: float = 15
    slip_bps: float = 5

    def __post_init__(self):
        bounds = (
            (self.capital, LOSS_LIMIT, 100_000_000), (self.risk, 1, LOSS_LIMIT),
            (self.reward, 1, 20), (self.fee_bps, 0, 500), (self.slip_bps, 0, 500),
        )
        if any(not isfinite(value) or not low <= value <= high for value, low, high in bounds):
            raise ValueError("Use capital ≥ ₹10,000, risk ₹1–₹10,000, reward 1–20R, and costs 0–500 bps each.")


@dataclass
class Position:
    bar: Bar
    shares: int
    entry: float
    cost: float
    stop: float
    target: float
    risk: float
    opened_at: int


def parse_bars(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("Daily candle CSV exceeds 2 MB.")
    rows = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    headers = {name.strip().lower(): name for name in rows.fieldnames or []}
    columns = {
        key: next((headers[alias] for alias in (key, *alternates) if alias in headers), None)
        for key, alternates in CSV_ALIASES.items()
    }
    if any(value is None for value in columns.values()):
        raise ValueError("CSV needs date, open, high, low, and close columns.")
    bars = []
    for line, row in enumerate(rows, start=2):
        try:
            raw_date = row[columns["date"]].strip()
            try:
                session = date.fromisoformat(raw_date)
            except ValueError:
                session = datetime.strptime(raw_date, "%d-%b-%Y").date()
            bar = Bar(session, *(float(row[columns[key]]) for key in ("open", "high", "low", "close")))
            prices = (bar.open, bar.high, bar.low, bar.close)
            if not all(isfinite(p) and 0.000001 <= p <= 10_000_000 for p in prices):
                raise ValueError
            if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f"Invalid daily candle on CSV line {line}.") from None
        bars.append(bar)
    bars.sort(key=lambda bar: bar.date)
    if len(bars) < 52 or len({bar.date for bar in bars}) != len(bars):
        raise ValueError("Supply at least 52 daily candles with unique session dates.")
    return bars


def example_bars():
    rng = random.Random(42)
    day = date(2023, 1, 2)
    previous = 480.0
    bars = []
    for i in range(520):
        opened = previous * (1 + rng.uniform(-0.007, 0.007))
        drift = (0.0035 if i % 170 < 110 else -0.003)
        close = opened * (1 + drift + rng.uniform(-0.013, 0.013))
        high = max(opened, close) * (1 + rng.uniform(0, 0.009))
        low = min(opened, close) * (1 - rng.uniform(0, 0.009))
        bars.append(Bar(day, opened, high, low, close))
        previous = close
        day += timedelta(days=1)
        while day.weekday() > 4:
            day += timedelta(days=1)
    return bars


def signal(bars, index):
    if index < 49:
        return None
    current = bars[index]
    if current.close <= max(bar.high for bar in bars[index - 20:index]):
        return None
    if current.close <= mean(bar.close for bar in bars[index - 49:index + 1]):
        return None
    true_ranges = [
        max(bar.high - bar.low, abs(bar.high - prior.close), abs(bar.low - prior.close))
        for prior, bar in zip(bars[index - 14:index], bars[index - 13:index + 1])
    ]
    return 2 * mean(true_ranges)


def exit_signal(bar, protection, target, time_exit):
    if bar.open <= protection:
        return bar.open, "Gap through protection"
    if bar.open >= target:
        return target, "Target"
    if time_exit:
        return bar.open, "Time exit"
    if bar.low <= protection:
        return protection, "Protection"
    if bar.high >= target:
        return target, "Target"
    return None, ""


def simulate(bars, settings, name, source, end_dates=None):
    fee = settings.fee_bps / 10_000
    slip = settings.slip_bps / 10_000
    buy_factor = (1 + slip) * (1 + fee)
    sell_factor = (1 - slip) * (1 - fee)
    cash = peak = settings.capital
    drawdown = 0.0
    trades, curve = [], []
    queued = position = halted = None
    first_bar = last_bar = None

    for index, bar in enumerate(bars):
        if end_dates and bar.date < end_dates[0]:
            if index == 0 or bars[index - 1].date < end_dates[0]:
                queued = signal(bars, index)
            continue
        if end_dates and bar.date > end_dates[1]:
            break
        if first_bar is None:
            first_bar = bar
        last_bar = bar
        final_bar = index == len(bars) - 1 or (end_dates and bars[index + 1].date > end_dates[1])
        floor_equity = peak - LOSS_LIMIT
        if queued is not None and position is None and not halted and not final_bar:
            stop = bar.open - queued
            if stop > 0:
                per_share = bar.open * buy_factor - stop * sell_factor
                budget = min(settings.risk, cash - floor_equity)
                shares = floor(min(cash / (bar.open * buy_factor), budget / per_share))
                if shares > 0:
                    cost = shares * bar.open * buy_factor
                    target = (bar.open * buy_factor + settings.reward * per_share) / sell_factor
                    position = Position(bar, shares, bar.open * (1 + slip), cost, stop, target,
                                        shares * per_share, index)
                    cash -= cost
        queued = None
        if position is not None:
            kill_price = (floor_equity - cash) / (position.shares * sell_factor)
            trigger = max(position.stop, kill_price)
            price, reason = exit_signal(bar, trigger, position.target, index - position.opened_at >= 20)
            if reason in {"Gap through protection", "Protection"} and price <= kill_price + 1e-8:
                reason = "Gap through drawdown limit" if bar.open < trigger else "Drawdown limit"
            if price is None and final_bar:
                price, reason = bar.close, "End of test"
            if price is not None:
                proceeds = position.shares * price * sell_factor
                pnl = proceeds - position.cost
                trades.append({
                    "entry_date": str(position.bar.date), "exit_date": str(bar.date),
                    "shares": position.shares, "entry": round(position.entry, 4),
                    "exit": round(price * (1 - slip), 4), "pnl": round(pnl, 2),
                    "r": round(pnl / position.risk, 2), "reason": reason,
                })
                cash += proceeds
                position = None
            else:
                drawdown = max(drawdown, peak - cash - position.shares * bar.low * sell_factor)

        equity = cash + (position.shares * bar.close * sell_factor if position else 0)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if equity <= floor_equity + 1e-6 and not halted:
            halted = str(bar.date)
        curve.append({"date": str(bar.date), "equity": round(equity, 2)})
        if position is None and not halted and not final_bar:
            queued = signal(bars, index)

    if first_bar is None:
        raise ValueError("No trading sessions in the requested dates.")
    gains = [trade["pnl"] for trade in trades if trade["pnl"] > 0]
    losses = [-trade["pnl"] for trade in trades if trade["pnl"] < 0]
    final = curve[-1]["equity"]
    benchmark_trade_cost = first_bar.open * buy_factor
    benchmark_shares = floor(settings.capital / benchmark_trade_cost)
    benchmark_pnl = benchmark_shares * (last_bar.close * sell_factor - benchmark_trade_cost)
    return {
        "strategy": STRATEGY, "instrument": name, "source": source, "run_at": now(),
        "settings": {**vars(settings), "loss_limit": LOSS_LIMIT},
        "from": curve[0]["date"], "to": curve[-1]["date"],
        "metrics": {
            "final_equity": final, "net_pnl": round(final - settings.capital, 2),
            "buy_and_hold_pnl": round(benchmark_pnl, 2),
            "max_drawdown": round(drawdown, 2), "limit_overshoot": round(max(0, drawdown - LOSS_LIMIT), 2),
            "halted_on": halted, "trades": len(trades), "winners": len(gains), "losers": len(losses),
            "win_rate": round(100 * len(gains) / len(trades), 1) if trades else None,
            "profit_factor": round(sum(gains) / sum(losses), 2) if losses else None,
            "payoff": round(mean(gains) / mean(losses), 2) if gains and losses else None,
            "avg_pnl": round(mean(t["pnl"] for t in trades), 2) if trades else None,
        },
        "curve": curve, "trade_log": trades,
    }


def run(raw, name, settings, start="", end=""):
    bars = parse_bars(raw) if raw is not None else example_bars()
    requested_start = date.fromisoformat(start) if start else bars[0].date
    to_date = date.fromisoformat(end) if end else bars[-1].date
    if requested_start > to_date:
        raise ValueError("Start date must be on or before end date.")
    from_date = max(requested_start, bars[50].date)
    if from_date > to_date:
        raise ValueError("The requested period ends before the 50-session warm-up completes.")
    source = ("CSV · SHA-256 " + hashlib.sha256(raw).hexdigest()) if raw is not None else "Synthetic demo"
    return simulate(bars, settings, name, source, (from_date, to_date))


def save(result):
    write_json("backtest.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, nargs="?", help="Daily OHLC CSV. Omit for fictional demo data.")
    parser.add_argument("--symbol", default="", help="Ticker or dataset label.")
    parser.add_argument("--start", default="", help="First evaluation date. Earlier bars are used for warm-up.")
    parser.add_argument("--end", default="", help="Last evaluation date.")
    for flag in ("capital", "risk", "reward", "fee_bps", "slip_bps"):
        parser.add_argument("--" + flag.replace("_", "-"), type=float, default=getattr(Settings(), flag))
    args = parser.parse_args()
    try:
        raw = None
        if args.csv:
            with args.csv.open("rb") as source:
                raw = source.read(MAX_BYTES + 1)
        settings = Settings(args.capital, args.risk, args.reward, args.fee_bps, args.slip_bps)
        result = run(raw, args.symbol or (args.csv.stem if args.csv else "Fictional equity"), settings,
                     args.start, args.end)
        save(result)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f"{error}\n")
    m = result["metrics"]
    print(f'{result["instrument"]} · {result["source"]} · {result["from"]}–{result["to"]}')
    print(f'{m["trades"]} trades · P&L ₹{m["net_pnl"]:,.2f} · max drawdown ₹{m["max_drawdown"]:,.2f}')
    print(f"Saved {DATA / 'backtest.json'}")


if __name__ == "__main__":
    main()

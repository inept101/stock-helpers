---
name: zerodha-portfolio
description: Use for the Stock Helpers Zerodha portfolio workspace. Authenticate Kite Connect, refresh holdings and account data, run the dashboard, research NSE/BSE stocks and ETFs, size investment decisions, backtest daily strategies, or handle explicitly requested Kite orders.
---

# Zerodha Portfolio

Run the commands from the Stock Helpers workspace containing `stock_helpers.py`, `dashboard.py`, and `backtest.py`.

## Connect and run the dashboard

1. For first-time setup, create a Kite Connect Personal app and set its Redirect URL to `http://127.0.0.1:8765/`. The postback URL is optional for this workflow. Store the API key and secret in the local `.env` as `zerodha_api_key` and `zerodha_api_secret`. The uppercase `KITE_API_KEY` and `KITE_API_SECRET` names also work. If `callback_url` is configured, keep its origin and path aligned with the registered redirect. [Zerodha developer setup](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/how-do-i-sign-up-for-kite-connect)
2. In the user's terminal, run `python3 stock_helpers.py kite-login`. Complete sign-in in the browser and wait for `Saved KITE_ACCESS_TOKEN in .env.` The command listens on loopback and exchanges the one-time request token. If the callback cannot be captured, use `python3 stock_helpers.py kite-login --manual` and paste the fresh redirect at the hidden terminal prompt. The access token expires at 6 a.m. IST the next day unless invalidated sooner. Renew with the same command. [Kite login flow](https://kite.trade/docs/connect/v3/user/)
3. Run `python3 stock_helpers.py sync-kite holdings` to refresh the portfolio, then `python3 dashboard.py` and open [the local dashboard](http://127.0.0.1:8765/). Login and the default dashboard both use port 8765. Finish login first, stop the dashboard before reauthenticating, or run the dashboard on another port with `python3 dashboard.py --port 8766`.
4. The dashboard reads local snapshots when the page is loaded. Refresh holdings and news with the CLI, then reload the page. Use `python3 dashboard.py --export` to regenerate the private static file at `.stock-helpers/dashboard.html`, or `python3 dashboard.py --demo` for a fictional preview.

## Account data and capabilities

- Run `python3 stock_helpers.py kite-apis` to list the read-only endpoints. Pass only the needed resources to `sync-kite`, for example `python3 stock_helpers.py sync-kite holdings positions funds orders trades mutual-funds`. Use `python3 stock_helpers.py summary` for saved holdings and weights. Holdings are in `.stock-helpers/holdings.json`. Other account snapshots are under `.stock-helpers/kite/`. Read each `as_of` before combining data because a sync can complete only part of a batch.
- Check deployable funds and used margin before allocating capital. Keep delivery holdings and day/net positions distinct. Kite orders and fills cover the current trading day. Use the Console Tradebook for longer history. Keep .env credentials, callback query strings, and personal account data out of transcripts and public research queries.
- Refresh NSE announcements with `python3 stock_helpers.py sync-news`. The command also takes repeatable `--feed` arguments for HTTPS RSS or Atom feeds. The dashboard reads `.stock-helpers/news.json`, sourced company research, and archived recommendation briefs.
- For a local backtest, use the dashboard's daily OHLC upload or run `python3 backtest.py candles.csv --symbol SYMBOL --capital 500000 --risk 2000 --reward 3`. Supply at least 52 distinct daily candles with date, open, high, low, and close. Omitting the CSV runs a synthetic demo. The built-in strategy is a long-only 20-session breakout with a 2 ATR stop and a ₹10,000 peak-to-trough strategy drawdown halt. Gaps can exceed the modeled limit. The report is saved to `.stock-helpers/backtest.json`.
- For live order requests and market-data limits, read [Kite operations](references/kite-operations.md). The CLI and dashboard provide snapshots, research and paper backtests. Broker-side order placement uses Kite or the Kite Connect order endpoints.

## Research and decisions

1. Identify the horizon, available capital, risk limits, and existing exposure. Use the current brief or the user's latest instructions for allocation assumptions. Choose a bounded, named stock universe and use dated prices and source-linked filings. Read [research workflow](references/research.md) for ranking, sentiment, and the `size` command.
2. Give each candidate an enter, watch, hold, trim, exit, or pass decision. State the entry or exit trigger, thesis invalidation, quantity, capital required, and next checkpoint. Explain the trade-offs and leave cash available when the price or evidence is inadequate. Mark paper scenarios and unverified inputs clearly.
3. Check combined capital, costs and post-proposal exposures. Publish the dated Markdown with `python3 stock_helpers.py publish-brief FILE` when updating the dashboard's recommendations. The command archives the previous brief. Re-export the private HTML if it is used.
4. For a focused filing review, populate `.stock-helpers/research-news.json` with `as_of` and an `items` array. Each item has `symbol`, `published_at`, `title`, `summary`, and `url`. Use an ISO date or offset-aware timestamp for `published_at` and link to the company or exchange filing.

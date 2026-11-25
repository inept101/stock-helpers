# Stock Helpers

Stock Helpers is a local dashboard and Codex skill for researching Indian equities, tracking a Zerodha portfolio, and testing daily trading strategies. Try the dashboard with fictional data before connecting a brokerage account.

## What you can do

| Capability | What it provides |
| --- | --- |
| Portfolio tracking | Sync Kite holdings and review quantities, valuation, broker P&L, allocation, and snapshot time. |
| Account checks | Fetch positions, equity funds and margins, mutual funds, and the current trading day's orders and fills. |
| News and filings | Collect NSE announcements and optionally follow other RSS or Atom feeds. Add researched company updates with links to the original filings. |
| Investment research | Use the Codex skill to review holdings, rank NSE or BSE stocks and ETFs, and explain entry, hold, trim, or exit decisions. Size whole-share scenarios using cash, exposure, and modeled risk. |
| Recommendation history | Publish a Markdown decision brief to the dashboard and retain earlier versions. |
| Paper backtesting | Run the built-in daily breakout strategy on an OHLC CSV or use synthetic demo candles. Review returns, drawdown, fills, and sensitivity to fees and slippage. |

## Run it locally

Use Python 3.12. The application uses the Python standard library.

```bash
git clone https://github.com/inept101/stock-helpers.git
cd stock-helpers
python3 dashboard.py --demo
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/). Stop the demo with Ctrl+C before starting the portfolio dashboard on the same port.

### Connect Zerodha

1. Create a Kite Connect Personal app and register `http://127.0.0.1:8765/` as its Redirect URL. The postback URL is optional for this workflow. [Zerodha developer setup](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/how-do-i-sign-up-for-kite-connect)
2. Create a local `.env` file in the project folder with the following settings. Replace the placeholders with your own app credentials.

   ```dotenv
   zerodha_api_key=YOUR_KITE_API_KEY
   zerodha_api_secret=YOUR_KITE_API_SECRET
   ```

3. Run the login command and complete verification in your browser. Wait for `Saved KITE_ACCESS_TOKEN in .env.` before running the sync. If the browser callback fails, rerun with `kite-login --manual` and paste the fresh redirect URL at the hidden terminal prompt. The saved access token normally expires at 6 a.m. IST the next day. [Kite session documentation](https://kite.trade/docs/connect/v3/user/)

   ```bash
   python3 stock_helpers.py kite-login
   python3 stock_helpers.py sync-kite holdings
   python3 dashboard.py
   ```

4. Open [the dashboard](http://127.0.0.1:8765/). Rerun a sync and reload the page to see updated data. The login listener also uses port 8765, so stop the dashboard before renewing the token or run it with `python3 dashboard.py --port 8766`.

### Refresh and publish

```bash
python3 stock_helpers.py kite-apis
python3 stock_helpers.py sync-kite holdings positions funds orders trades mutual-funds
python3 stock_helpers.py summary
python3 stock_helpers.py sync-news
python3 stock_helpers.py publish-brief path/to/brief.md
python3 dashboard.py --export
```

Pass just the account resources you need to `sync-kite`. Repeat `--feed HTTPS_URL` on `sync-news` to add feeds. The HTML export is saved to `.stock-helpers/dashboard.html`. Use the live local server for the interactive backtest form.

### Run a backtest

Upload daily candles in the dashboard or run the CLI. The CSV needs at least 52 unique sessions with `date,open,high,low,close` columns. Use one instrument and data with reliable corporate-action treatment.

```bash
python3 backtest.py
python3 backtest.py candles.csv --symbol EXAMPLE --capital 500000 --risk 2000 --reward 3
python3 -m unittest -q
```

The built-in strategy is a long-only 20-session breakout with a 2 ATR stop, configurable reward-to-risk, and a ₹10,000 strategy drawdown halt. Gaps can exceed the modeled limit. Results are saved to `.stock-helpers/backtest.json`.

## Codex and Kite order workflows

Point Codex at the [Zerodha Portfolio skill](skills/zerodha-portfolio/SKILL.md). For example, ask it to review your holdings and rank up to five candidates using source-linked filings, entry and exit criteria, and whole-share allocations.

The CLI reads account data and the dashboard runs paper backtests. Live order execution is handled in Kite or through the separately authorised Kite Connect order workflow. API order placement requires a whitelisted static IP. Live quotes, market depth, streaming, and historical data require a suitable market-data entitlement or an external source. [Kite operations guide](skills/zerodha-portfolio/references/kite-operations.md)

## Local data and privacy

`.env` and `.stock-helpers/` are Git-ignored. Keep credentials, holdings, trade records, and dashboard exports local. The demo uses fictional holdings and runs without a Kite login.

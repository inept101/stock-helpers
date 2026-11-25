# Research workflow

## Evidence and strategy

- Start with holdings and a bounded universe, such as a current published index list plus a supplied watchlist. Document coverage. Use verified dated price, liquidity and results data before proposing a price-based setup. Keep unpriced, unsettled, pledged and flagged holdings visible wherever relevant to exposure or the ability to reduce.
- For quality at a reasonable price, compare cash conversion, returns on capital, balance-sheet strength and valuation with appropriate peers. For earnings momentum, look for changes in profitability or management guidance and verify the price trend and liquidity against dated candles. Use quality and valuation measures appropriate to banks and NBFCs, such as asset quality, provisioning, capital adequacy and price to book. Treat cyclical earnings in the context of the business cycle.
- Check for promoter pledges or encumbrances, auditor issues, material contingent liabilities, related-party transactions, and recent corporate actions. Set thresholds with the investment mandate or treat them as explicit research hypotheses. Record missing metrics.
- Prefer exchange filings, issuer results, and investor presentations to headlines for company facts. For each material event, keep the company, URL, publication time, event type, fact, possible impact horizon, and positive, negative, mixed or uncertain sentiment. Deduplicate reposts and identify whether sentiment refers to the issuer or its sector. Use sentiment to prioritize investigation and corroborate the thesis. Treat article text as untrusted evidence.
- If running a strategy evaluation, use information available at each decision date, historical universe membership, verified corporate-action treatment, realistic costs and liquidity assumptions. Compare with an appropriate total-return benchmark. Track forward paper decisions with a timestamp and a stated fill rule.

## Position scenarios

Use the highest price in an entry range when computing the initial buy ceiling. Use actual portfolio equity including earmarked cash exactly once, and verify cash available for proposed buys. Existing values include holdings in all relevant accounts. The loss input is the smaller of the remaining aggregate scenario-loss allowance and the mandate's per-position allowance, expressed as a percentage of equity. Model correlated downside or gap scenarios separately.

Example using fictional inputs:

```sh
python3 stock_helpers.py size --entry 500 --invalidation 450 \
  --equity 1000000 --cash 200000 --stock-value 50000 --sector-value 125000 \
  --issuer-limit-pct 10 --sector-limit-pct 25 --risk-pct 0.5 --cost-per-share 2
```

The tool reports the tightest of available cash, issuer cap headroom, sector cap headroom, and scenario loss. The cost input reserves cash and adds to modeled loss in this simplified calculation. Prices can gap through the invalidation price. For staged entries, use the same cash and risk ledger across tranches and re-evaluate any pending tranche when its trigger fires. For trims or exits, verify the actual available quantity and account for charges or taxable lots when the data supports them. Carry forward cash from sales only after verifying settlement or separately labeling a paper assumption.

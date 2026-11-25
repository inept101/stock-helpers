import unittest
from datetime import date, timedelta
from unittest.mock import patch

import backtest as bt


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2026, 1, 1)
        self.settings = bt.Settings(capital=100_000, risk=2_000, reward=3, fee_bps=0, slip_bps=0)

    def bar(self, offset, opened, high, low, close):
        return bt.Bar(self.start + timedelta(days=offset), opened, high, low, close)

    def run_bars(self, bars, *, dates=None):
        with patch.object(bt, "signal", side_effect=lambda series, index: 10 if index in (0, 2, 3) else None):
            return bt.simulate(bars, self.settings, "Test", "Fixture", dates)

    def test_entry_uses_next_open_and_ambiguous_candle_hits_stop_first(self):
        result = self.run_bars([
            self.bar(0, 90, 91, 89, 90),
            self.bar(1, 100, 135, 85, 115),
            self.bar(2, 115, 116, 114, 115),
        ])
        trade, = result["trade_log"]
        self.assertEqual(trade["entry_date"], str(self.start + timedelta(days=1)))
        self.assertEqual((trade["entry"], trade["exit"], trade["pnl"], trade["reason"]),
                         (100, 90, -2000, "Protection"))

    def test_gap_reports_drawdown_overshoot_and_stops_future_entries(self):
        result = self.run_bars([
            self.bar(0, 90, 91, 89, 90),
            self.bar(1, 100, 101, 95, 100),
            self.bar(2, 40, 42, 39, 40),
            self.bar(3, 40, 41, 39, 40),
            self.bar(4, 40, 41, 39, 40),
        ])
        self.assertEqual(result["metrics"]["halted_on"], str(self.start + timedelta(days=2)))
        self.assertEqual(result["metrics"]["max_drawdown"], 12_000)
        self.assertEqual(result["metrics"]["limit_overshoot"], 2_000)
        trade, = result["trade_log"]
        self.assertEqual(trade["reason"], "Gap through drawdown limit")

    def test_buy_and_hold_uses_selected_final_close_and_prior_signal_warms_up(self):
        bars = [self.bar(0, 90, 101, 89, 100), self.bar(1, 100, 110, 98, 105),
                self.bar(2, 105, 125, 104, 120), self.bar(3, 120, 151, 119, 150)]
        result = self.run_bars(bars, dates=(bars[1].date, bars[2].date))
        self.assertEqual(result["metrics"]["buy_and_hold_pnl"], 20_000)
        trade, = result["trade_log"]
        self.assertEqual(trade["entry_date"], str(bars[1].date))
        self.assertEqual((trade["pnl"], trade["reason"]), (4_000, "End of test"))

    def test_exchange_csv_headers_and_unique_dates(self):
        header = b"TradDt,OpnPric,HghPric,LwPric,ClsPric\n"
        rows = [f"{self.start + timedelta(days=i)},100,110,90,105\n".encode() for i in range(52)]
        self.assertEqual(len(bt.parse_bars(header + b"".join(reversed(rows)))), 52)
        with self.assertRaisesRegex(ValueError, "unique"):
            bt.parse_bars(header + b"".join(rows + rows[:1]))


if __name__ == "__main__":
    unittest.main()

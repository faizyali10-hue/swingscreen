"""
Nifty 500 Swing Screener — JSON output for GitHub Actions + GitHub Pages
===========================================================================

Same screening logic as before (daily RSI pullback + weekly RSI confirmation +
trend/liquidity filters), but writes results to docs/results.json instead of
printing/CSV, so a static HTML page (docs/index.html) can read it directly —
no live API calls from the browser, no CORS proxy, no fragility.

This is meant to be run on a schedule by GitHub Actions (see
.github/workflows/screener.yml), which commits the updated JSON back to the
repo automatically. GitHub Pages then serves docs/index.html + docs/results.json
as a normal static site.

Requirements: pip install -r requirements.txt
"""

import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timezone

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("Install dependencies first: pip install -r requirements.txt")

# ----------------------------- CONFIG ---------------------------------
LOOKBACK_PERIOD = "2y"

RSI_PERIOD = 14
RSI_ENTRY_TRIGGER = 45
RSI_OVERSOLD_FLOOR = 20
WEEKLY_RSI_MIN = 60

EMA_TREND = 200
EMA_FAST = 20

MIN_AVG_TURNOVER_CR = 5

TICKER_FILE = "nifty500_tickers.csv"
OUTPUT_JSON = "docs/results.json"

# ------------------------- INDICATOR HELPERS ----------------------------

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def get_weekly_rsi(daily_df: pd.DataFrame) -> float:
    weekly = daily_df.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
    }).dropna()
    if len(weekly) < RSI_PERIOD + 1:
        return np.nan
    weekly_rsi = compute_rsi(weekly["Close"], RSI_PERIOD)
    return weekly_rsi.iloc[-1]


# --------------------------- SCREENING LOGIC --------------------------------

def screen_stock(symbol: str, df: pd.DataFrame) -> dict | None:
    if df.empty or len(df) < EMA_TREND + 20:
        return None

    df = df.copy()
    df["EMA20"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=EMA_TREND, adjust=False).mean()
    df["RSI"] = compute_rsi(df["Close"], RSI_PERIOD)
    df["AvgTurnoverCr"] = (df["Close"] * df["Volume"]).rolling(20).mean() / 1e7

    latest = df.iloc[-1]
    rsi_window = df["RSI"].tail(5)

    was_oversold = rsi_window.min() < RSI_ENTRY_TRIGGER
    rsi_cross_up = (latest["RSI"] > RSI_ENTRY_TRIGGER) and (df["RSI"].iloc[-2] <= RSI_ENTRY_TRIGGER)
    not_too_weak = rsi_window.min() > RSI_OVERSOLD_FLOOR
    trend_ok = latest["Close"] > latest["EMA200"]
    above_fast_ema = latest["Close"] > latest["EMA20"]
    liquid_enough = latest["AvgTurnoverCr"] > MIN_AVG_TURNOVER_CR

    if not all([was_oversold, rsi_cross_up, not_too_weak, trend_ok, above_fast_ema, liquid_enough]):
        return None

    weekly_rsi = get_weekly_rsi(df)
    if pd.isna(weekly_rsi) or weekly_rsi <= WEEKLY_RSI_MIN:
        return None

    swing_low = df["Low"].tail(10).min()
    stop_loss = round(float(swing_low * 0.995), 2)
    entry_price = round(float(latest["Close"]), 2)
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0:
        return None

    return {
        "symbol": symbol.replace(".NS", ""),
        "close": entry_price,
        "dailyRsi": round(float(latest["RSI"]), 1),
        "weeklyRsi": round(float(weekly_rsi), 1),
        "ema20": round(float(latest["EMA20"]), 2),
        "ema200": round(float(latest["EMA200"]), 2),
        "stopLoss": stop_loss,
        "target3R": round(entry_price + 3 * risk_per_share, 2),
        "avgTurnoverCr": round(float(latest["AvgTurnoverCr"]), 1),
    }


# --------------------------- MAIN --------------------------------

def load_tickers() -> list:
    if os.path.exists(TICKER_FILE):
        return pd.read_csv(TICKER_FILE)["Symbol"].tolist()
    raise FileNotFoundError(
        f"{TICKER_FILE} not found. Create a CSV with a 'Symbol' column of NSE tickers "
        f"(e.g. RELIANCE.NS, TCS.NS ...) for your Nifty 500 universe."
    )


def main():
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    tickers = load_tickers()
    print(f"Scanning {len(tickers)} tickers...")

    results = []
    errors = []
    for idx, symbol in enumerate(tickers):
        try:
            df = yf.download(symbol, period=LOOKBACK_PERIOD, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            hit = screen_stock(symbol, df)
            if hit:
                results.append(hit)
                print(f"  ✓ {hit['symbol']}: DailyRSI={hit['dailyRsi']} WeeklyRSI={hit['weeklyRsi']}")
        except Exception as e:
            errors.append({"symbol": symbol, "error": str(e)})
            print(f"  [skip] {symbol}: {e}")

        if (idx + 1) % 25 == 0:
            print(f"  ...processed {idx + 1}/{len(tickers)}")

    results.sort(key=lambda r: r["weeklyRsi"], reverse=True)

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "config": {
            "rsiEntryTrigger": RSI_ENTRY_TRIGGER,
            "rsiOversoldFloor": RSI_OVERSOLD_FLOOR,
            "weeklyRsiMin": WEEKLY_RSI_MIN,
            "emaTrend": EMA_TREND,
            "emaFast": EMA_FAST,
            "minAvgTurnoverCr": MIN_AVG_TURNOVER_CR,
        },
        "universeSize": len(tickers),
        "resultsCount": len(results),
        "results": results,
        "errorCount": len(errors),
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{len(results)} setups found out of {len(tickers)} scanned.")
    print(f"Saved to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

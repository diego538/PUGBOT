import aiohttp
import csv
import pandas as pd
import numpy as np
from datetime import datetime

# Bybit Futures (USDT Perpetual)
KLINE_URL = "https://api.bybit.com/v5/market/kline?category=linear&symbol={}&interval={}"
ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook?category=linear&symbol={}&limit=50"

# ----------------------
# HTTP
# ----------------------
async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None

async def load_kline(symbol, interval):
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, KLINE_URL.format(symbol, interval))
        if not data or "result" not in data or "list" not in data["result"]:
            return None

        df = pd.DataFrame(data["result"]["list"])
        df.columns = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df

async def load_orderbook(symbol):
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, ORDERBOOK_URL.format(symbol))
        if not data or "result" not in data:
            return None, None, None

        bids = np.array([[float(p), float(q)] for p, q in data["result"]["b"]])
        asks = np.array([[float(p), float(q)] for p, q in data["result"]["a"]])

        bid_liq = bids[:10, 1].sum()
        ask_liq = asks[:10, 1].sum()
        imbalance = (bid_liq - ask_liq) / (bid_liq + ask_liq + 1e-9)

        return bid_liq, ask_liq, imbalance

# ----------------------
# Индикаторы
# ----------------------
def stoch_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    return (rsi - rsi.rolling(period).min()) / (
        rsi.rolling(period).max() - rsi.rolling(period).min() + 1e-9
    )

def mfi(df, period=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]

    pos = mf.where(df["close"] > df["close"].shift(1), 0)
    neg = mf.where(df["close"] < df["close"].shift(1), 0)

    return 100 * pos.rolling(period).sum() / (
        pos.rolling(period).sum() + neg.rolling(period).sum() + 1e-9
    )

# ----------------------
# Анализ
# ----------------------
def analyze(df, bid_liq, ask_liq, df_5min=None):
    if len(df) < 20:
        return None

    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]

    stoch = stoch_rsi(df).iloc[-1]
    mfi_val = mfi(df).iloc[-1]

    score = 0
    reasons = []

    if stoch > 0.8 or mfi_val > 80:
        score += 1
        reasons.append("Перекупленность (Stoch RSI / MFI)")

    if last_close < prev_close:
        score += 1
        reasons.append("Начало снижения цены")

    imbalance = (bid_liq - ask_liq) / (bid_liq + ask_liq + 1e-9)
    if imbalance < -0.2:
        score += 1
        reasons.append("Дисбаланс стакана (ask > bid)")

    if df_5min is not None and len(df_5min) >= 20:
        support = df_5min["low"].rolling(20).min().iloc[-1]
        if last_close < support:
            score += 1
            reasons.append("Пробой поддержки на 5m")

    signal = "SHORT" if score >= 3 else "HOLD"
    strength = min(100, score * 25)

    return {
        "signal": signal,
        "strength": strength,
        "reasons": reasons
    }

# ----------------------
# Логи
# ----------------------
def log_signal(symbol, price, result, file="signals_log.csv"):
    with open(file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now(),
            symbol,
            price,
            result["signal"],
            result["strength"],
            "; ".join(result.get("reasons", []))
        ])

import aiohttp
import csv
import pandas as pd
import numpy as np
from datetime import datetime

KLINE_URL = "https://api.bybit.com/v5/market/kline?category=linear&symbol={}&interval={}"
ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook?category=linear&symbol={}&limit=50"
FUNDING_URL = "https://api.bybit.com/v5/market/funding/history?symbol={}&limit=1"
OI_URL = "https://api.bybit.com/v5/market/open-interest?category=linear&symbol={}&interval=5min"

# ----------------------
async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None

# ----------------------
async def load_kline(symbol, interval):
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, KLINE_URL.format(symbol, interval))
        if not data or "result" not in data:
            return None

        df = pd.DataFrame(data["result"]["list"])
        df.columns = ["ts", "open", "high", "low", "close", "volume", "turnover"]
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
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
async def load_funding_and_oi(symbol):
    async with aiohttp.ClientSession() as session:
        funding_data = await fetch_json(session, FUNDING_URL.format(symbol))
        oi_data = await fetch_json(session, OI_URL.format(symbol))

        funding = None
        oi_change = None

        try:
            funding = float(funding_data["result"]["list"][0]["fundingRate"]) * 100
        except Exception:
            pass

        try:
            oi_list = oi_data["result"]["list"]
            if len(oi_list) >= 2:
                old = float(oi_list[-2]["openInterest"])
                new = float(oi_list[-1]["openInterest"])
                oi_change = (new - old) / old * 100
        except Exception:
            pass

        return funding, oi_change

# ----------------------
def stoch_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / (loss.rolling(period).mean() + 1e-9)
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
def analyze(df, bid_liq, ask_liq, df_5min=None, symbol=None):
    if len(df) < 20:
        return None

    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-2]

    stoch = stoch_rsi(df).iloc[-1]
    mfi_val = mfi(df).iloc[-1]

    score = 0
    reasons = []

    if stoch > 0.8 or mfi_val > 80:
        score += 1
        reasons.append("Перекупленность")

    if last < prev:
        score += 1
        reasons.append("Начало снижения цены")

    imbalance = (bid_liq - ask_liq) / (bid_liq + ask_liq + 1e-9)
    if imbalance < -0.2:
        score += 1
        reasons.append("Ask-дисбаланс")

    if df_5min is not None:
        support = df_5min["low"].rolling(20).min().iloc[-1]
        if last < support:
            score += 1
            reasons.append("Пробой поддержки 5m")

    signal = "SHORT" if score >= 3 else "HOLD"

    # ---- Risk score (инфо)
    risk = 0
    if df["high"].iloc[-1] / df["low"].iloc[-1] > 1.02:
        risk += 1
    if stoch > 0.9:
        risk += 1

    risk_level = ["LOW 🟢", "MEDIUM 🟡", "HIGH 🔴"][min(risk, 2)]

    # ---- Funding / OI (инфо)
    funding, oi_change = None, None
    if symbol:
        funding, oi_change = asyncio.run(load_funding_and_oi(symbol))

    return {
        "signal": signal,
        "strength": min(100, score * 25),
        "reasons": reasons,
        "risk_level": risk_level,
        "funding": funding,
        "oi_change": oi_change
    }

# ----------------------
def log_signal(symbol, price, result, file="signals_log.csv"):
    with open(file, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.now(),
            symbol,
            price,
            result["signal"],
            result["strength"],
            result.get("risk_level"),
            result.get("funding"),
            result.get("oi_change"),
            "; ".join(result.get("reasons", []))
        ])

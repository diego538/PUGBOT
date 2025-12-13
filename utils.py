import requests
import csv
import pandas as pd
import numpy as np
from datetime import datetime

KLINE_URL = "https://api.bybit.com/v5/market/kline?category=spot&symbol={}&interval={}"
ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook?category=spot&symbol={}&limit=50"

# ======================
# 1. Загрузка данных
# ======================
def load_kline(symbol, interval):
    try:
        r = requests.get(KLINE_URL.format(symbol, interval), timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if "result" not in data or "list" not in data["result"]:
            return None
        df = pd.DataFrame(data["result"]["list"])
        df.columns = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df
    except:
        return None

def load_orderbook(symbol):
    try:
        r = requests.get(ORDERBOOK_URL.format(symbol), timeout=10)
        if r.status_code != 200:
            return None, None, None
        data = r.json()
        bids = np.array([[float(p), float(q)] for p, q in data["result"]["b"]])
        asks = np.array([[float(p), float(q)] for p, q in data["result"]["a"]])
        bid_liq = bids[:10, 1].sum()
        ask_liq = asks[:10, 1].sum()
        imbalance = (bid_liq - ask_liq) / (bid_liq + ask_liq + 1e-9)
        return bid_liq, ask_liq, imbalance
    except:
        return None, None, None

# ======================
# 2. Индикаторы
# ======================
def stoch_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    stoch = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min() + 1e-9)
    return stoch

def mfi(df, period=14):
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    money_flow = typical_price * df["volume"]
    positive_flow = money_flow.where(df["close"] > df["close"].shift(1), 0)
    negative_flow = money_flow.where(df["close"] < df["close"].shift(1), 0)
    mfi_val = 100 * positive_flow.rolling(period).sum() / (positive_flow.rolling(period).sum() + negative_flow.rolling(period).sum() + 1e-9)
    return mfi_val

# ======================
# 3. Анализ разворота
# ======================
def analyze(df, bid_liq, ask_liq):
    if len(df) < 15:
        return None

    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]
    last_vol = df["volume"].iloc[-1]
    avg_vol = df["volume"].iloc[-15:-1].mean()

    stoch = stoch_rsi(df).iloc[-1]
    mfi_val = mfi(df).iloc[-1]

    reversal_score = 0

    # объём — спад после пампа
    if 500_000 <= last_vol <= 5_000_000 and last_vol < avg_vol:
        reversal_score += 1

    # перекупленность
    if stoch > 0.8 or mfi_val > 80:
        reversal_score += 1

    # цена начала падать
    if last_close < prev_close:
        reversal_score += 1

    # дисбаланс стакана
    imbalance = (bid_liq - ask_liq) / (bid_liq + ask_liq + 1e-9)
    if imbalance < -0.2:
        reversal_score += 1

    signal = "SHORT" if reversal_score >= 3 else "HOLD"
    strength = min(100, reversal_score * 25)

    return {"signal": signal, "strength": strength}

# ======================
# 4. Логирование
# ======================
def log_signal(symbol, price, result, file="signals_log.csv"):
    with open(file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now(), symbol, price, result["signal"], result["strength"]])

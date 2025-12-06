import requests
import csv
import pandas as pd
from datetime import datetime

KLINE_URL = "https://api.bybit.com/v5/market/kline?category=spot&symbol={}&interval={}"


def load_kline(symbol, interval):
    url = KLINE_URL.format(symbol, interval)
    r = requests.get(url, timeout=10)

    if r.status_code != 200:
        return None

    data = r.json()
    if "result" not in data or "list" not in data["result"]:
        return None

    df = pd.DataFrame(data["result"]["list"])
    df.columns = ["timestamp", "open", "high", "low", "close", "volume", "turnover"]
    df["close"] = df["close"].astype(float)

    return df


def analyze(df):
    # простая проверка — можешь заменить на любую стратегию
    if len(df) < 5:
        return None

    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-2]

    if last > prev:
        return {"signal": "UP", "strength": 75}
    else:
        return {"signal": "DOWN", "strength": 70}


def log_signal(symbol, price, result, file="signals_log.csv"):
    with open(file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now(), symbol, price, result["signal"], result["strength"]])

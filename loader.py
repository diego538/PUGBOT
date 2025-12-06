import numpy as np
import pandas as pd
import time
import telebot
import csv
import requests
from datetime import datetime

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
bot = telebot.TeleBot(BOT_TOKEN)

KLINE_URL = "https://api.bybit.com/v5/market/kline?category=spot&symbol={}&interval={}"

LOG_FILE = "signals_log.csv"

def ema(series, period=20):
    return series.ewm(span=period, adjust=False).mean()

def macd(close):
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    line = ema12 - ema26
    signal = ema(line, 9)
    hist = line - signal
    return line.values, signal.values, hist.values

def stoch_rsi(close, period=14):
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    stoch = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min() + 1e-9)
    return stoch.values

def mfi(df, period=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]

    positive = np.where(tp > tp.shift(1), mf, 0)
    negative = np.where(tp < tp.shift(1), mf, 0)

    pmf = pd.Series(positive).rolling(period).sum()
    nmf = pd.Series(negative).rolling(period).sum()

    return 100 * (pmf / (nmf + 1e-9))

def log_signal(symbol, price, res):
    row = [
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        symbol,
        price,
        res["probability"],
        res["score"],
        ",".join(res["tf_hits"]),
        "; ".join(res["reasons_list"])
    ]

    try:
        file_exists = False
        try:
            with open(LOG_FILE, "r") as f:
                file_exists = True
        except FileNotFoundError:
            file_exists = False

        with open(LOG_FILE, "a", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "symbol", "price", "probability", "score", "tf_hits", "reasons"])
            writer.writerow(row)

    except Exception as e:
        print("Error writing log:", e)

def send_signal(symbol, price, res):
    log_signal(symbol, price, res)

    reasons = "\n".join([f"• {x}" for x in res["reasons_list"]])

    msg = f"""
🚨 <b>REVERSAL SHORT SIGNAL</b>

<b>{symbol}</b>
Price: <b>{price}</b>

<b>Probability:</b> {res['probability']}%  
Score: {res['score']}

<b>Indicators triggered:</b>
{reasons}

<b>TF confirmation:</b> {", ".join(res["tf_hits"])}
""" 

    try:
        bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML")
    except:
        pass

def get_klines(symbol, interval):
    url = KLINE_URL.format(symbol, interval)
    data = requests.get(url).json()
    try:
        df = pd.DataFrame(data["result"]["list"], 
                          columns=["timestamp", "open", "high", "low", "close", "volume"])
    except:
        return None
    return df.astype(float)

def get_low_liq_tokens():
    url = "https://api.bybit.com/v5/market/instruments-info?category=spot"
    data = requests.get(url).json()
    tokens = []

    for coin in data["result"]["list"]:
        if "USDT" in coin["symbol"]:
            vol = float(coin["turnover24h"])
            if vol < 300000:
                tokens.append(coin["symbol"])

    return tokens

def check_reversal(df):
    reasons = []
    score = 0

    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    vol = df["volume"]

    last = len(df) - 1

    ema20 = ema(close, 20)
    macd_line, macd_signal, macd_hist = macd(close)
    stoch_vals = stoch_rsi(close)
    mfi_vals = mfi(df)

    pump_pct = (high.iloc[last] - low.iloc[last - 5]) / low.iloc[last - 5] * 100
    if pump_pct >= 8:
        reasons.append("Pump > 8% in 5 candles")
        score += 20

    avg_vol = vol.iloc[-20:].mean()
    if vol.iloc[last] > avg_vol * 3:
        reasons.append("Volume spike x3")
        score += 15

    range_c = high.iloc[last] - low.iloc[last]
    upper_wick = high.iloc[last] - max(close.iloc[last], open_.iloc[last])
    if range_c and upper_wick / range_c > 0.45:
        reasons.append("Large upper wick >45%")
        score += 12

    if high.iloc[last] > high.iloc[last-1] and close.iloc[last] < high.iloc[last-1]:
        reasons.append("SFP high sweep")
        score += 15

    if close.iloc[last] < ema20.iloc[last]:
        reasons.append("Close < EMA20")
        score += 10

    if macd_line[last] < macd_signal[last] and macd_hist[last] < 0:
        reasons.append("MACD bearish cross")
        score += 10

    if stoch_vals[last] > 0.8 and stoch_vals[last] < stoch_vals[last-1]:
        reasons.append("Stoch RSI down from overbought")
        score += 8

    if mfi_vals.iloc[last] > 75 and mfi_vals.iloc[last] < mfi_vals.iloc[last-1]:
        reasons.append("MFI falling from >75")
        score += 8

    probability = min(95, int(score * 1.2))

    return {
        "score": score,
        "probability": probability,
        "reasons_list": reasons
    }

def main():
    print("Bot started… scanning Bybit low-liq tokens")

    while True:
        try:
            tokens = get_low_liq_tokens()

            for symbol in tokens:
                tf_hits = []
                res_total = {"score": 0, "probability": 0, "reasons_list": []}

                for tf in ["1", "3", "5"]:
                    df = get_klines(symbol, tf)
                    if df is None or len(df) < 50:
                        continue

                    res = check_reversal(df)
                    if res["score"] >= 35:
                        tf_hits.append(tf)
                        res_total["score"] += res["score"]
                        res_total["probability"] += res["probability"]
                        res_total["reasons_list"] += res["reasons_list"]

                if len(tf_hits) >= 2:
                    df15 = get_klines(symbol, "15")
                    if df15 is None or len(df15) < 50:
                        continue

                    ema15 = ema(df15["close"], 20)
                    if df15["close"].iloc[-1] < ema15.iloc[-1]:
                        price = get_klines(symbol, "1")["close"].iloc[-1]

                        res_total["tf_hits"] = tf_hits
                        res_total["probability"] = min(95, int(res_total["probability"] / len(tf_hits)))

                        send_signal(symbol, price, res_total)

                time.sleep(1)

            time.sleep(10)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    main()

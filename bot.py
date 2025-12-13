import time
from loader import bot, CHAT_ID
from utils import load_kline, load_orderbook, analyze, log_signal

SYMBOLS = ["TOKEN1USDT", "TOKEN2USDT"]  # низколиквидные токены
INTERVALS = ["1", "5", "15"]

def send_signal(symbol, price, result, interval):
    text = (
        f"📊 *Сигнал по {symbol} ({interval}m)*\n"
        f"Цена: `{price}`\n"
        f"Сигнал: *{result['signal']}*\n"
        f"Вероятность: {result['strength']}%"
    )
    bot.send_message(CHAT_ID, text, parse_mode="Markdown")

def process():
    for symbol in SYMBOLS:
        bid_liq, ask_liq, imbalance = load_orderbook(symbol)
        if bid_liq is None:
            continue
        # фильтр низколиквидных токенов
        if bid_liq + ask_liq > 500_000:
            continue

        for interval in INTERVALS:
            df = load_kline(symbol, interval)
            if df is None:
                continue

            result = analyze(df, bid_liq, ask_liq)
            if result is None or result["signal"] == "HOLD":
                continue

            price = df["close"].iloc[-1]

            send_signal(symbol, price, result, interval)
            log_signal(symbol, price, result)

            time.sleep(1)
    time.sleep(5)

def main():
    while True:
        try:
            process()
        except Exception as e:
            print("Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    main()

import time
from loader import bot, CHAT_ID
from utils import load_kline, analyze, log_signal

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1", "5", "15"]


def send_signal(symbol, price, result):
    text = (
        f"📊 *Сигнал по {symbol}*\n"
        f"Цена: `{price}`\n"
        f"Сигнал: *{result['signal']}*\n"
        f"Вероятность: {result['strength']}%"
    )
    bot.send_message(CHAT_ID, text, parse_mode="Markdown")


def process():
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            df = load_kline(symbol, interval)
            if df is None:
                continue

            result = analyze(df)
            if result is None:
                continue

            price = df["close"].iloc[-1]

            send_signal(symbol, price, result)
            log_signal(symbol, price, result)

            time.sleep(1)

    time.sleep(10)


def main():
    while True:
        try:
            process()
        except Exception as e:
            print("Error:", e)
            time.sleep(5)


if name == "__main__":
    main()

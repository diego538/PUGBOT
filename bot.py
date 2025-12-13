import asyncio
import time
from loader import bot, CHAT_ID
from utils import load_kline, load_orderbook, analyze, log_signal

SYMBOLS = ["TOKEN1USDT", "TOKEN2USDT"]
INTERVALS = ["1", "5", "15"]

# ----------------------
# Отправка сигнала
# ----------------------
def send_signal(symbol, price, result, interval):
    reasons_text = "\n".join([f"- {r}" for r in result.get("reasons", [])])
    text = (
        f"📊 *Сигнал по {symbol} ({interval}m)*\n"
        f"Цена: `{price}`\n"
        f"Сигнал: *{result['signal']}*\n"
        f"Вероятность: {result['strength']}%\n"
        f"Факторы разворота:\n{reasons_text}"
    )
    bot.send_message(CHAT_ID, text, parse_mode="Markdown")

# ----------------------
# Команда /start
# ----------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "Привет! Я бот для поиска сигналов разворота после пампа.\n\n"
        "Я анализирую следующие параметры:\n"
        "- Спад объёма после пампа\n"
        "- Перекупленность по Stoch RSI и MFI\n"
        "- Начало падения цены\n"
        "- Дисбаланс стакана (ask > bid)\n"
        "- Пробой ближайшего уровня поддержки на 5-минутном таймфрейме\n\n"
        "Если все эти условия выполняются, я отправляю сигнал SHORT с вероятностью разворота."
    )
    bot.send_message(message.chat.id, text)

# ----------------------
# Основной асинхронный процесс
# ----------------------
async def process_symbol(symbol, interval):
    bid_liq, ask_liq, imbalance = await load_orderbook(symbol)
    if bid_liq is None:
        return

    if bid_liq + ask_liq > 500_000:
        return

    df = await load_kline(symbol, interval)
    if df is None:
        return

    df_5min = await load_kline(symbol, "5")

    result = analyze(df, bid_liq, ask_liq, df_5min=df_5min)
    if result is None or result["signal"] == "HOLD":
        return

    price = df["close"].iloc[-1]
    send_signal(symbol, price, result, interval)
    log_signal(symbol, price, result)

async def main_loop():
    while True:
        try:
            tasks = []
            for symbol in SYMBOLS:
                for interval in INTERVALS:
                    tasks.append(process_symbol(symbol, interval))
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)
        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(5)

def main():
    loop = asyncio.get_event_loop()
    loop.create_task(main_loop())
    bot.infinity_polling()

if __name__ == "__main__":
    main()

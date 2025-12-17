import asyncio
from loader import bot, CHAT_ID
from utils import load_kline, load_orderbook, analyze, log_signal

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1", "5", "15"]

# ----------------------
# Отправка сигнала
# ----------------------
def send_signal(symbol, price, result, interval):
    reasons_text = "\n".join([f"- {r}" for r in result.get("reasons", [])])

    risk = result.get("risk_level", "N/A")
    funding = result.get("funding")
    oi = result.get("oi_change")

    extra = ""
    if funding is not None:
        extra += f"\nFunding: `{funding:+.4f}%`"
    if oi is not None:
        extra += f"\nOI change: `{oi:+.2f}%`"

    text = (
        f"📉 *Futures сигнал {symbol} ({interval}m)*\n"
        f"Цена: `{price}`\n"
        f"Сигнал: *{result['signal']}*\n"
        f"Сила: {result['strength']}%\n"
        f"Риск: *{risk}*\n"
        f"{extra}\n\n"
        f"*Факторы:*\n{reasons_text}"
    )

    bot.send_message(CHAT_ID, text, parse_mode="Markdown")

# ----------------------
# Команда /start
# ----------------------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🤖 Бот ищет SHORT-развороты на Bybit Futures.\n\n"
        "Дополнительно показывает:\n"
        "- Risk-score (опасность входа)\n"
        "- Funding Rate (где толпа)\n"
        "- Изменение Open Interest\n\n"
        "⚠️ Эти параметры не фильтруют сигнал, а помогают принять решение."
    )

# ----------------------
async def process_symbol(symbol, interval):
    bid_liq, ask_liq, _ = await load_orderbook(symbol)
    if bid_liq is None:
        return

    df = await load_kline(symbol, interval)
    if df is None:
        return

    df_5min = await load_kline(symbol, "5")

    result = analyze(df, bid_liq, ask_liq, df_5min=df_5min, symbol=symbol)
    if not result or result["signal"] == "HOLD":
        return

    price = df["close"].iloc[-1]
    send_signal(symbol, price, result, interval)
    log_signal(symbol, price, result)

async def main_loop():
    while True:
        try:
            tasks = [
                process_symbol(symbol, interval)
                for symbol in SYMBOLS
                for interval in INTERVALS
            ]
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

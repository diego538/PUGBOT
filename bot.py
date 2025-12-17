import asyncio
from datetime import datetime, timedelta
from loader import bot, CHAT_ID
from utils import load_kline, load_orderbook, analyze, log_signal, load_funding_and_oi

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1", "5", "15"]
MIN_GROWTH = 15  # минимальный рост за 24 часа для сигнала SHORT

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
    explanation = (
        "🤖 Привет! Я бот для поиска SHORT-сигналов на Bybit Futures.\n\n"
        "Вот что я делаю:\n"
        "1️⃣ Загружаю данные по выбранным монетам:\n"
        "   - Книгу ордеров (bid/ask) для оценки дисбаланса стакана\n"
        "   - Свечи разных таймфреймов (1m, 5m, 15m) для анализа цены и объёмов\n"
        "2️⃣ Анализирую сигналы SHORT по следующим условиям:\n"
        "   - Перекупленность (Stoch RSI или MFI > 80)\n"
        "   - Начало снижения цены\n"
        "   - Ask-дисбаланс стакана\n"
        "   ⚠️ Сигнал SHORT выдаётся только если рост цены за последние 24 часа ≥ 15%\n"
        "3️⃣ Вычисляю силу сигнала (strength) и Risk-score (низкий/средний/высокий)\n"
        "4️⃣ Подтягиваю информационные показатели:\n"
        "   - Funding Rate (где толпа)\n"
        "   - Изменение Open Interest (OI) за последние свечи\n"
        "5️⃣ Отправляю Telegram-сообщение с:\n"
        "   - Символом и таймфреймом\n"
        "   - Текущей ценой\n"
        "   - Сигналом SHORT или HOLD\n"
        "   - Силой сигнала, Risk-score, Funding, OI\n"
        "   - Причинами сигнала (факторы)\n\n"
        "Все сигналы логируются в CSV-файл для анализа."
    )
    bot.send_message(message.chat.id, explanation)

# ----------------------
async def process_symbol(symbol, interval):
    bid_liq, ask_liq, _ = await load_orderbook(symbol)
    if bid_liq is None:
        return

    df = await load_kline(symbol, interval)
    if df is None or len(df) < 2:
        return

    df_5min = await load_kline(symbol, "5")

    # --- загрузка Funding и OI ---
    funding, oi_change = await load_funding_and_oi(symbol)

    # --- точная проверка роста за 24 часа (по минутным свечам) ---
    df_1m = await load_kline(symbol, "1")  # 1-мин свечи
    growth_ok = False
    if df_1m is not None and len(df_1m) >= 2:
        now = datetime.utcnow()
        ts_24h_ago = int((now - timedelta(hours=24)).timestamp() * 1000)  # timestamp в ms
        df_24h = df_1m[df_1m["ts"].astype(int) >= ts_24h_ago]

        if not df_24h.empty:
            close_24h_ago = df_24h["close"].iloc[0]
            last_close = df["close"].iloc[-1]
            growth = (last_close - close_24h_ago) / close_24h_ago * 100
            if growth >= MIN_GROWTH:
                growth_ok = True

    # --- анализ сигнала ---
    result = analyze(df, bid_liq, ask_liq, df_5min=df_5min, funding=funding, oi_change=oi_change)

    # --- применяем фильтр роста ---
    if result and result["signal"] == "SHORT" and not growth_ok:
        result["signal"] = "HOLD"
        result["reasons"].append(f"Рост < {MIN_GROWTH}% за последние 24ч — сигнал не активен")

    price = df["close"].iloc[-1]
    send_signal(symbol, price, result, interval)
    log_signal(symbol, price, result)

# ----------------------
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

# ----------------------
def main():
    loop = asyncio.get_event_loop()
    loop.create_task(main_loop())
    bot.infinity_polling()

if __name__ == "__main__":
    main()


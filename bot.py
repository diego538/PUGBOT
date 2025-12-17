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
    bot.send_message(
        message.chat.id,
        "🤖 Бот ищет SHORT-развороты на Bybit Futures.\n\n"
        "Дополнительно показывает:\n"
        "- Risk-score (опасность входа)\n"
        "- Funding Rate (где толпа)\n"
        "- Изменение Open Interest\n"
        "⚠️ Сигналы SHORT активны только если рост за последние 24 часа >= 15%"
    )

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
    result = analyze(df, bid_liq, ask_liq, df_5min=df_5min, funding=funding, oi

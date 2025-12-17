import os
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в переменных окружения")

if not CHAT_ID:
    raise ValueError("❌ CHAT_ID не найден в переменных окружения")

bot = telebot.TeleBot(BOT_TOKEN)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🪙 Crypto Market Bot — Студенческий проект

Простой Telegram-бот для отслеживания криптовалют.
Использует web scraping (без API).

Команды:
    /start  — приветствие
    /help   — справка
    /status — текущие данные рынка

Запуск: python bot.py
"""

import os
import re
import time
from datetime import datetime

import requests
import telebot
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ============================================
# 1. КОНФИГУРАЦИЯ
# ============================================

# Загружаем токен из .env файла
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Создайте файл .env")

# Настройки скрапинга
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15  # секунд

# Простой кэш: {ключ: (значение, время)}
_cache = {}
CACHE_TTL = 60  # секунд


# ============================================
# 2. СКРАПИНГ (Web Scraping)
# ============================================

def fetch_html(url):
    """Загружает HTML страницы."""
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return None


def get_cached(key):
    """Получить из кэша (если не устарело)."""
    if key in _cache:
        value, timestamp = _cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return value
    return None


def set_cached(key, value):
    """Сохранить в кэш."""
    _cache[key] = (value, time.time())


def fetch_btc_price():
    """
    Получает цену BTC через API Blockchain.com.
    URL: https://blockchain.info/ticker
    """
    cached = get_cached("btc_price")
    if cached:
        return cached
    
    # Используем публичное API (возвращает JSON)
    url = "https://blockchain.info/ticker"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        # JSON формат: {"USD": {"last": 90000.0, ...}, ...}
        if "USD" in data and "last" in data["USD"]:
            price = float(data["USD"]["last"])
            if price > 0:
                set_cached("btc_price", price)
                return price
                
    except Exception as e:
        print(f"[ERROR] Blockchain API error: {e}")
    
    return None


def fetch_fear_greed():
    """
    Парсит индекс Fear & Greed.
    URL: https://alternative.me/crypto/fear-and-greed-index/
    """
    cached = get_cached("fear_greed")
    if cached:
        return cached
    
    html = fetch_html("https://alternative.me/crypto/fear-and-greed-index/")
    if not html:
        return None, None
    
    try:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text()
        
        # Ищем число рядом с "Now" или "Fear and Greed Index"
        match = re.search(r"Now[^\d]*(\d{1,3})", text, re.IGNORECASE)
        if not match:
            # Альтернативный паттерн
            match = re.search(r"Index[^\d]*(\d{1,3})", text, re.IGNORECASE)
        
        if match:
            value = int(match.group(1))
            if 0 <= value <= 100:
                # Определяем текстовый label
                if value <= 25:
                    label = "Extreme Fear"
                elif value <= 45:
                    label = "Fear"
                elif value <= 55:
                    label = "Neutral"
                elif value <= 75:
                    label = "Greed"
                else:
                    label = "Extreme Greed"
                
                result = (value, label)
                set_cached("fear_greed", result)
                return result
        
        return None, None
    except Exception as e:
        print(f"[ERROR] Fear&Greed parse: {e}")
        return None, None


def get_market_snapshot():
    """Получает все данные о рынке."""
    btc_price = fetch_btc_price()
    fear_value, fear_label = fetch_fear_greed()
    
    return {
        "btc_price": btc_price,
        "fear_value": fear_value,
        "fear_label": fear_label,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_snapshot(data):
    """Форматирует данные в текст для Telegram."""
    lines = [
        "📊 *Crypto Market Snapshot*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    
    # BTC Price
    btc = data.get("btc_price")
    if btc:
        lines.append(f"💰 BTC: *${btc:,.2f}*")
    else:
        lines.append("💰 BTC: _недоступно_")
    
    # Fear & Greed
    fg_val = data.get("fear_value")
    fg_lbl = data.get("fear_label")
    if fg_val is not None:
        emoji = "😨" if fg_val < 40 else "😐" if fg_val < 60 else "🤑"
        lines.append(f"{emoji} Fear & Greed: *{fg_val}* ({fg_lbl})")
    else:
        lines.append("😱 Fear & Greed: _недоступно_")
    
    # Timestamp
    lines.append(f"⏰ _{data.get('timestamp', 'N/A')}_")
    
    return "\n".join(lines)


# ============================================
# 3. TELEGRAM БОТ
# ============================================

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    """Команда /start — приветствие."""
    text = (
        "👋 *Привет!*\n\n"
        "Я — Crypto Market Bot.\n"
        "Показываю данные о криптовалютах.\n\n"
        "Отправь /status чтобы узнать текущие курсы."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["help"])
def cmd_help(message):
    """Команда /help — справка."""
    text = (
        "📚 *Команды:*\n\n"
        "/start — запуск бота\n"
        "/help — эта справка\n"
        "/status — снимок рынка"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    """Команда /status — данные о рынке."""
    # Показываем "печатает..."
    bot.send_chat_action(message.chat.id, "typing")
    
    # Получаем данные
    data = get_market_snapshot()
    
    # Проверяем, есть ли данные
    if data.get("btc_price") or data.get("fear_value"):
        text = format_snapshot(data)
    else:
        text = "⚠️ Источники временно недоступны. Попробуйте позже."
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ============================================
# 4. ЗАПУСК
# ============================================

def main():
    """Главная функция."""
    print("=" * 40)
    print("🚀 Crypto Market Bot")
    print("=" * 40)
    
    try:
        info = bot.get_me()
        print(f"✅ Бот: @{info.username}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return
    
    print("✨ Запущен! Ctrl+C для остановки.")
    
    # Self-check on startup
    print("🔍 Выполняю проверку источников данных...")
    snapshot = get_market_snapshot()
    if snapshot.get("btc_price"):
        print(f"✅ Данные получены: BTC=${snapshot['btc_price']}")
    else:
        print("⚠️ Ошибка получения данных при запуске!")
    
    # Бесконечный цикл опроса Telegram
    bot.infinity_polling()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Скрипт для настройки Telegram webhook.

Использование:
    python scripts/setup_telegram_webhook.py https://yourdomain.com

Требует:
    - TELEGRAM_BOT_TOKEN в .env
"""

import os
import sys
import requests
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)


def set_webhook(domain: str):
    """Set Telegram webhook for the bot."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')

    if not token or token == 'your_telegram_bot_token_here':
        print("Ошибка: TELEGRAM_BOT_TOKEN не настроен в .env")
        sys.exit(1)

    webhook_url = f"{domain.rstrip('/')}/integrations/telegram/webhook/"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"

    print(f"Устанавливаю webhook: {webhook_url}")

    response = requests.post(api_url, data={'url': webhook_url})
    result = response.json()

    if result.get('ok'):
        print("Webhook успешно установлен!")
        print(f"Описание: {result.get('description')}")
    else:
        print(f"Ошибка: {result.get('description')}")
        sys.exit(1)


def get_webhook_info():
    """Get current webhook info."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')

    if not token or token == 'your_telegram_bot_token_here':
        print("Ошибка: TELEGRAM_BOT_TOKEN не настроен в .env")
        sys.exit(1)

    api_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"

    response = requests.get(api_url)
    result = response.json()

    if result.get('ok'):
        info = result.get('result', {})
        print("Текущий webhook:")
        print(f"  URL: {info.get('url') or '(не установлен)'}")
        print(f"  Pending updates: {info.get('pending_update_count', 0)}")
        if info.get('last_error_message'):
            print(f"  Последняя ошибка: {info.get('last_error_message')}")
    else:
        print(f"Ошибка: {result.get('description')}")


def delete_webhook():
    """Delete current webhook."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')

    if not token or token == 'your_telegram_bot_token_here':
        print("Ошибка: TELEGRAM_BOT_TOKEN не настроен в .env")
        sys.exit(1)

    api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"

    response = requests.post(api_url)
    result = response.json()

    if result.get('ok'):
        print("Webhook удалён")
    else:
        print(f"Ошибка: {result.get('description')}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/setup_telegram_webhook.py https://yourdomain.com  # установить webhook")
        print("  python scripts/setup_telegram_webhook.py --info                   # проверить текущий")
        print("  python scripts/setup_telegram_webhook.py --delete                 # удалить webhook")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == '--info':
        get_webhook_info()
    elif arg == '--delete':
        delete_webhook()
    else:
        set_webhook(arg)

"""Сервис уведомлений через Telegram"""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "HTML"
) -> bool:
    """
    Отправить сообщение в Telegram.

    Args:
        bot_token: Токен бота от @BotFather
        chat_id: ID чата или username канала (@channel)
        message: Текст сообщения (поддерживает HTML)
        parse_mode: Режим парсинга (HTML или Markdown)

    Returns:
        True если сообщение отправлено успешно
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram: bot_token или chat_id не заданы")
        return False

    url = TELEGRAM_API_URL.format(token=bot_token, method="sendMessage")

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()
        if result.get("ok"):
            logger.info(f"Telegram: сообщение отправлено в {chat_id}")
            return True
        else:
            logger.error(f"Telegram API error: {result}")
            return False

    except requests.exceptions.Timeout:
        logger.error("Telegram: таймаут при отправке")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram: ошибка отправки: {e}")
        return False


def send_telegram_photo(
    bot_token: str,
    chat_id: str,
    photo_path: str,
    caption: str = "",
    parse_mode: str = "HTML"
) -> bool:
    """
    Отправить фото в Telegram.

    Args:
        bot_token: Токен бота
        chat_id: ID чата
        photo_path: Путь к файлу фото
        caption: Подпись к фото (макс. 1024 символа)
        parse_mode: Режим парсинга

    Returns:
        True если фото отправлено успешно
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram: bot_token или chat_id не заданы")
        return False

    url = TELEGRAM_API_URL.format(token=bot_token, method="sendPhoto")

    # Обрезаем caption до лимита Telegram (1024 символа)
    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': parse_mode,
            }
            response = requests.post(url, data=data, files=files, timeout=30)
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                logger.info(f"Telegram: фото отправлено в {chat_id}")
                return True
            else:
                logger.error(f"Telegram API error: {result}")
                return False

    except FileNotFoundError:
        logger.error(f"Telegram: файл не найден: {photo_path}")
        return False
    except requests.exceptions.Timeout:
        logger.error("Telegram: таймаут при отправке фото")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram: ошибка отправки фото: {e}")
        return False


def format_negative_review_message(review) -> str:
    """
    Форматирует сообщение о негативном отзыве.

    Args:
        review: объект Review

    Returns:
        Отформатированное HTML-сообщение
    """
    stars = "⭐" * review.rating + "☆" * (5 - review.rating)

    # Формируем заголовок
    company_line = f"<b>{review.company.name}</b>"
    if review.company.address:
        company_line += f", {review.company.address}"

    lines = [
        f"🔴 <b>Негативный отзыв!</b>",
        f"",
        company_line,
    ]

    # Добавляем точку если есть
    if review.spot:
        lines.append(f"<b>Точка:</b> {review.spot.name}")

    # QR-код
    if review.qr:
        lines.append(f"<b>QR:</b> {review.qr.name or review.qr.code}")

    lines.extend([
        f"",
        f"<b>Оценка:</b> {stars} ({review.rating}/5)",
        f"<b>Автор:</b> {review.author_name or 'Аноним'}",
    ])

    # Контакт автора
    if review.author_contact:
        lines.append(f"<b>Контакт:</b> {review.author_contact}")

    # Текст отзыва (лимит Telegram = 4096, оставляем запас для метаданных)
    if review.text:
        text = review.text[:3000]
        if len(review.text) > 3000:
            text += "..."
        lines.extend([
            f"",
            f"<b>Отзыв:</b>",
            f"<i>{text}</i>",
        ])

    # Детальные оценки
    if review.ratings:
        ratings_labels = {
            'food': '🍽 Еда',
            'service': '👨‍🍳 Сервис',
            'atmosphere': '✨ Атмосфера',
            'cleanliness': '🧹 Чистота',
            'speed': '⚡ Скорость',
        }
        ratings_str = []
        for key, value in review.ratings.items():
            label = ratings_labels.get(key, key)
            icon = "👍" if value == 1 else "👎" if value == 0 else "—"
            ratings_str.append(f"{label}: {icon}")

        if ratings_str:
            lines.extend([
                f"",
                f"<b>Оценки:</b> {', '.join(ratings_str)}",
            ])

    # Информация о прикреплённых фото
    photos_count = review.photos_count
    if photos_count > 0:
        photo_word = "фото" if photos_count == 1 else "фото"
        lines.extend([
            f"",
            f"📷 <b>Прикреплено {photos_count} {photo_word}</b>",
        ])

    lines.extend([
        f"",
        f"🕐 {review.created_at.strftime('%d.%m.%Y %H:%M')}",
    ])

    return "\n".join(lines)


def notify_negative_review(review) -> bool:
    """
    Отправляет уведомление о негативном отзыве.

    Args:
        review: объект Review

    Returns:
        True если уведомление отправлено
    """
    company = review.company

    # Получаем настройки Telegram из company.settings
    settings = company.settings or {}
    telegram_settings = settings.get('telegram', {})

    bot_token = telegram_settings.get('bot_token')
    chat_id = telegram_settings.get('chat_id')
    enabled = telegram_settings.get('enabled', True)

    if not enabled:
        logger.info(f"Telegram уведомления отключены для {company.name}")
        return False

    if not bot_token or not chat_id:
        logger.info(f"Telegram не настроен для {company.name}")
        return False

    message = format_negative_review_message(review)
    return send_telegram_message(bot_token, chat_id, message)

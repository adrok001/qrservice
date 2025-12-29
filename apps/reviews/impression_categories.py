"""
Карта впечатлений (Impression Map) для ниши HoReCa
==================================================

HoReCa (Hotel/Restaurant/Cafe) — сегмент индустрии гостеприимства.

Категории описывают основные аспекты клиентского опыта,
упоминаемые в отзывах. Используются для аналитики и
автоматической классификации обратной связи.

Тональность (sentiment):
- positive — позитивное упоминание
- negative — негативное упоминание
- neutral  — нейтральное упоминание
"""

# Основные категории и их подкатегории
IMPRESSION_CATEGORIES = {
    "Сервис": [
        "Сервис/персонал",
        "Вежливость/уважение",
        "Хамство/грубость/конфликт",
        "Внимание/вовлечённость",
        "Компетентность/знание меню",
        "Решение проблем/гарантия",
        "Коммуникация/тон",
        "Навязывание/апселл",
    ],
    "Скорость": [
        "Скорость/ожидание",
        "Скорость обслуживания",
    ],
    "Продукт": [
        "Еда/кухня",
        "Напитки/бар",
        "Качество/свежесть",
        "Порции/сытость",
    ],
    "Цена": [
        "Цена/ценность",
    ],
    "Комфорт": [
        "Интерьер/атмосфера",
        "Чистота/санитария",
    ],
    "Процесс": [
        "Бронирование/стол",
        "Управление/организация зала",
        "Заказ/ошибки",
        "Оплата/касса",
        "Доставка/вынос",
        "Локация/парковка",
    ],
}

# Допустимые значения тональности
SENTIMENT_CHOICES = [
    ("positive", "Позитивная"),
    ("negative", "Негативная"),
    ("neutral", "Нейтральная"),
]

# Плоский список всех подкатегорий для валидации
ALL_SUBCATEGORIES = []
for category, subcategories in IMPRESSION_CATEGORIES.items():
    for subcategory in subcategories:
        ALL_SUBCATEGORIES.append({
            "category": category,
            "subcategory": subcategory,
        })


def get_category_by_subcategory(subcategory: str) -> str | None:
    """Получить основную категорию по подкатегории."""
    for category, subcategories in IMPRESSION_CATEGORIES.items():
        if subcategory in subcategories:
            return category
    return None


def validate_impression_tag(tag: dict) -> bool:
    """
    Валидация тега впечатления.

    Ожидаемый формат:
    {
        "category": "Сервис",
        "subcategory": "Вежливость/уважение",
        "sentiment": "positive"
    }
    """
    required_keys = {"category", "subcategory", "sentiment"}
    if not all(key in tag for key in required_keys):
        return False

    if tag["category"] not in IMPRESSION_CATEGORIES:
        return False

    if tag["subcategory"] not in IMPRESSION_CATEGORIES[tag["category"]]:
        return False

    valid_sentiments = [s[0] for s in SENTIMENT_CHOICES]
    if tag["sentiment"] not in valid_sentiments:
        return False

    return True

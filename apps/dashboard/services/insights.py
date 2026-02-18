"""
Dashboard insights: топ жалоб и похвал (basic + AI режимы).
"""
from collections import Counter

from django.db.models import QuerySet


# === Топ жалоб и похвал ===

# Маппинг конкретных проблем на человекочитаемые описания
COMPLAINT_PATTERNS = {
    # Ожидание
    'долго': 'Долгое ожидание',
    'ждать': 'Долгое ожидание',
    'медленно': 'Долгое ожидание',
    'часа': 'Долгое ожидание',
    'часов': 'Долгое ожидание',
    'полчаса': 'Долгое ожидание',

    # Еда
    'холодный': 'Холодная еда',
    'остыть': 'Холодная еда',
    'невкусный': 'Невкусная еда',
    'безвкусный': 'Невкусная еда',
    'пересолен': 'Пересолено',
    'недосолен': 'Недосолено',
    'подгорел': 'Подгоревшая еда',
    'сырой': 'Сырая/недожаренная еда',
    'несвежий': 'Несвежие продукты',
    'тухлый': 'Несвежие продукты',
    'маленькая порция': 'Маленькие порции',
    'порция маленькая': 'Маленькие порции',
    'мало еды': 'Маленькие порции',

    # Персонал
    'грубый': 'Грубый персонал',
    'хамств': 'Грубый персонал',
    'хамит': 'Грубый персонал',
    'хамят': 'Грубый персонал',
    'хамка': 'Грубый персонал',
    'хамло': 'Грубый персонал',
    'нахамил': 'Грубый персонал',
    'невнимательн': 'Невнимательный персонал',
    'игнорир': 'Игнорируют гостей',
    'забыл': 'Забыли заказ/блюдо',
    'перепутал': 'Перепутали заказ',
    'не извинил': 'Не извинились',
    'обсчитал': 'Обсчёт',
    'обманул': 'Обман',

    # Комфорт
    'грязн': 'Грязно',
    'неубран': 'Грязно',
    'вонь': 'Неприятный запах',
    'воняет': 'Неприятный запах',
    'пахнет': 'Неприятный запах',
    'шумно': 'Шумно',
    'душно': 'Душно',
    'холодно в зале': 'Холодно в помещении',
    'жарко': 'Жарко в помещении',

    # Цена
    'дорого': 'Высокие цены',
    'дорогой': 'Высокие цены',
    'цены завышен': 'Высокие цены',
    'не стоит своих денег': 'Не соответствует цене',

    # Бронь/место
    'не было места': 'Нет свободных мест',
    'нет мест': 'Нет свободных мест',
    'отменили бронь': 'Проблемы с бронированием',
}

# === Маппинг AI-подкатегорий на человекочитаемые лейблы ===

SUBCATEGORY_MAP = {
    'Еда/кухня': 'Вкус/качество еды',
    'Скорость/ожидание': 'Скорость обслуживания',
    'Сервис/персонал': 'Отношение персонала',
    'Интерьер/атмосфера': 'Чистота/атмосфера',
    'Цена/ценность': 'Цены',
    'Бронирование/стол': 'Бронирование',
    'Отравление/симптомы': 'Безопасность еды',
    'Общее впечатление': None,  # пропускаем — не даёт действенной информации
}

# Обратный маппинг: label → список subcategories
SUBCATEGORY_MAP_REVERSE: dict[str, list[str]] = {}
for _subcat, _label in SUBCATEGORY_MAP.items():
    if _label:
        SUBCATEGORY_MAP_REVERSE.setdefault(_label, []).append(_subcat)


PRAISE_PATTERNS = {
    # Еда
    'вкусно': 'Вкусная еда',
    'вкусный': 'Вкусная еда',
    'очень вкусно': 'Вкусная еда',
    'объедение': 'Вкусная еда',
    'свежий': 'Свежие продукты',
    'свежая': 'Свежие продукты',
    'большая порция': 'Большие порции',
    'порции большие': 'Большие порции',
    'сытно': 'Большие порции',

    # Персонал
    'приятный персонал': 'Приятный персонал',
    'вежливый': 'Вежливый персонал',
    'внимательный': 'Внимательный персонал',
    'улыбчив': 'Приветливый персонал',
    'дружелюбн': 'Приветливый персонал',
    'официант молодец': 'Хороший официант',
    'официант отличн': 'Хороший официант',
    'спасибо официанту': 'Хороший официант',

    # Скорость
    'быстро': 'Быстрое обслуживание',
    'оперативно': 'Быстрое обслуживание',
    'не ждали': 'Быстрое обслуживание',

    # Атмосфера
    'уютно': 'Уютная атмосфера',
    'уютный': 'Уютная атмосфера',
    'атмосферн': 'Приятная атмосфера',
    'красивый интерьер': 'Красивый интерьер',
    'чисто': 'Чисто',
    'чистый': 'Чисто',

    # Цена
    'недорого': 'Доступные цены',
    'демократичные цены': 'Доступные цены',
    'цены приятные': 'Доступные цены',
    'цены радуют': 'Доступные цены',
    'соотношение цена': 'Хорошее соотношение цена/качество',

    # Общее
    'рекомендую': 'Рекомендуют друзьям',
    'советую': 'Рекомендуют друзьям',
    'вернусь': 'Хотят вернуться',
    'придём ещё': 'Хотят вернуться',
    'придем еще': 'Хотят вернуться',
}


def _extract_issues(text: str, patterns: dict) -> list[str]:
    """Извлечь проблемы/похвалы из текста по паттернам."""
    if not text:
        return []

    text_lower = text.lower()
    found = []

    for pattern, label in patterns.items():
        if pattern in text_lower and label not in found:
            found.append(label)

    return found


def get_top_complaints(reviews_qs: QuerySet, limit: int = 5) -> list[dict]:
    """
    Получить топ жалоб из отзывов.

    Returns:
        [{'label': 'Долгое ожидание', 'count': 47}, ...]
    """
    counter = Counter()

    # Анализируем только негативные отзывы
    negative_reviews = reviews_qs.filter(rating__lte=3)

    for review in negative_reviews.values('text'):
        issues = _extract_issues(review['text'], COMPLAINT_PATTERNS)
        counter.update(issues)

    return [
        {'label': label, 'count': count}
        for label, count in counter.most_common(limit)
    ]


def get_top_praises(reviews_qs: QuerySet, limit: int = 5) -> list[dict]:
    """
    Получить топ похвал из отзывов.

    Returns:
        [{'label': 'Вкусная еда', 'count': 156}, ...]
    """
    counter = Counter()

    # Анализируем только позитивные отзывы
    positive_reviews = reviews_qs.filter(rating__gte=4)

    for review in positive_reviews.values('text'):
        praises = _extract_issues(review['text'], PRAISE_PATTERNS)
        counter.update(praises)

    return [
        {'label': label, 'count': count}
        for label, count in counter.most_common(limit)
    ]


def get_top_complaints_ai(reviews_qs: QuerySet, limit: int = 5) -> list[dict]:
    """
    Получить топ жалоб из AI-тегов (review.tags).

    Группирует по SUBCATEGORY_MAP, считает только negative sentiment + rating <= 3.
    """
    counter = Counter()

    for review in reviews_qs.filter(rating__lte=3).only('tags'):
        tags = review.tags
        if not tags or not isinstance(tags, list):
            continue
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            if tag.get('sentiment') != 'negative':
                continue
            subcategory = tag.get('subcategory', '')
            label = SUBCATEGORY_MAP.get(subcategory)
            if label:
                counter[label] += 1

    return [
        {'label': label, 'count': count}
        for label, count in counter.most_common(limit)
    ]


def get_top_praises_ai(reviews_qs: QuerySet, limit: int = 5) -> list[dict]:
    """
    Получить топ похвал из AI-тегов (review.tags).

    Группирует по SUBCATEGORY_MAP, считает только positive sentiment + rating >= 4.
    """
    counter = Counter()

    for review in reviews_qs.filter(rating__gte=4).only('tags'):
        tags = review.tags
        if not tags or not isinstance(tags, list):
            continue
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            if tag.get('sentiment') != 'positive':
                continue
            subcategory = tag.get('subcategory', '')
            label = SUBCATEGORY_MAP.get(subcategory)
            if label:
                counter[label] += 1

    return [
        {'label': label, 'count': count}
        for label, count in counter.most_common(limit)
    ]

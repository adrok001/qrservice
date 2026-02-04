"""
Dashboard insights: конкретные жалобы, похвалы и задачи.
"""
from collections import Counter
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from apps.companies.models import Company, Spot
from apps.reviews.models import Review


# === Иерархия проблем по уровням критичности ===

PROBLEM_PATTERNS = [
    # Уровень 1: КРИТИЧНО (может закрыть бизнес)
    {
        'key': 'poisoning',
        'label': 'Отравления',
        'level': 'critical',
        'patterns': ['отравил', 'отравление', 'стало плохо', 'рвота',
                     'тошнит', 'скорая', 'больница', 'понос', 'диарея']
    },
    {
        'key': 'foreign_objects',
        'label': 'Посторонние предметы',
        'level': 'critical',
        'patterns': ['волос в', 'нашли в еде', 'посторонн', 'что-то чёрное',
                     'пластик в еде', 'стекло в еде', 'муха в супе', 'муха в еде']
    },
    {
        'key': 'insects',
        'label': 'Насекомые',
        'level': 'critical',
        'patterns': ['таракан', 'тараканы', 'мухи ползают', 'насекомые']
    },
    {
        'key': 'raw_meat',
        'label': 'Сырое мясо/рыба',
        'level': 'critical',
        'patterns': ['сырая курица', 'сырое мясо', 'сырая рыба',
                     'недожарен', 'недоварен', 'с кровью внутри']
    },

    # Уровень 2: СЕРЬЁЗНО (теряем клиентов навсегда)
    {
        'key': 'rude_staff',
        'label': 'Грубость персонала',
        'level': 'serious',
        'patterns': ['нахамил', 'хамит', 'хамка', 'хам ', 'грубый', 'грубая',
                     'грубо ответил', 'оскорбил', 'унизил', 'наорал']
    },
    {
        'key': 'fraud',
        'label': 'Обман/обсчёт',
        'level': 'serious',
        'patterns': ['обсчитал', 'обманул', 'обман', 'в счёте лишнее',
                     'приписали', 'накрутили', 'мошенни']
    },
    {
        'key': 'spoiled',
        'label': 'Испорченные продукты',
        'level': 'serious',
        'patterns': ['тухлый', 'тухлая', 'несвежий', 'несвежая', 'испорчен',
                     'с душком', 'протух', 'плесень', 'прокисш']
    },
    {
        'key': 'dirty_dishes',
        'label': 'Грязная посуда',
        'level': 'serious',
        'patterns': ['грязная посуда', 'грязный стакан', 'грязная тарелка',
                     'губная помада на', 'немытая', 'следы еды']
    },

    # Уровень 3: ВАЖНО (теряем повторные визиты)
    {
        'key': 'bad_taste',
        'label': 'Невкусная еда',
        'level': 'important',
        'patterns': ['невкусно', 'безвкусно', 'несъедобно', 'ужасный вкус',
                     'отвратительно', 'есть невозможно']
    },
    {
        'key': 'long_wait',
        'label': 'Долгое ожидание',
        'level': 'important',
        'patterns': ['ждали час', 'ждали 40', 'ждали 50', 'долго несут',
                     'забыли про нас', 'очень долго', 'прождали']
    },
    {
        'key': 'cold_food',
        'label': 'Холодная еда',
        'level': 'important',
        'patterns': ['холодный', 'холодная', 'остывш', 'еле тёплый', 'еле теплый']
    },
    {
        'key': 'wrong_order',
        'label': 'Ошибки в заказе',
        'level': 'important',
        'patterns': ['перепутали', 'принесли не то', 'забыли блюдо',
                     'не то принесли', 'заказывали другое']
    },
]

LEVEL_PRIORITY = {'critical': 1, 'serious': 2, 'important': 3}
LEVEL_COLORS = {
    'critical': {'border': '#ef4444', 'bg': '#fef2f2'},
    'serious': {'border': '#f97316', 'bg': '#fff7ed'},
    'important': {'border': '#eab308', 'bg': '#fefce8'},
}


# === Требует внимания ===

def get_attention_items(company: Company) -> dict:
    """
    Получить срочные задачи для предпринимателя.

    Независимо от периода — всегда актуальные данные.
    """
    reviews = Review.objects.filter(company=company)

    # Негативные без ответа
    no_response = reviews.filter(
        rating__lte=3,
        response=''
    ).count()

    # Клиенты, которые просят связаться (без ответа)
    wants_contact = reviews.filter(
        wants_contact=True,
        response=''
    ).count()

    # Негативные за последние 24 часа
    yesterday = timezone.now() - timedelta(hours=24)
    recent_negative = reviews.filter(
        rating__lte=3,
        created_at__gte=yesterday
    ).count()

    # Отзывы с категорией "Безопасность" (критические)
    # SQLite не поддерживает JSON contains, поэтому фильтруем в Python
    safety_issues = _count_safety_reviews(reviews.filter(rating__lte=3))
    safety_by_spot = _get_safety_by_spot(company)

    # Общее количество задач
    total = no_response + wants_contact

    return {
        'no_response': no_response,
        'wants_contact': wants_contact,
        'recent_negative': recent_negative,
        'safety_issues': safety_issues,
        'safety_by_spot': safety_by_spot,
        'total': total,
        'has_urgent': wants_contact > 0 or recent_negative > 0 or safety_issues > 0,
    }


def _count_safety_reviews(reviews_qs: QuerySet) -> int:
    """Подсчитать отзывы с категорией Безопасность."""
    count = 0
    for review in reviews_qs.only('tags'):
        if review.tags:
            for tag in review.tags:
                if isinstance(tag, dict) and tag.get('category') == 'Безопасность':
                    count += 1
                    break
    return count


def _get_safety_by_spot(company: Company) -> list[dict]:
    """Получить распределение проблем безопасности по точкам."""
    from apps.companies.models import Spot

    result = []
    for spot in Spot.objects.filter(company=company, is_active=True):
        reviews = Review.objects.filter(company=company, spot=spot, rating__lte=3)
        count = _count_safety_reviews(reviews)
        if count > 0:
            result.append({'spot': spot.name, 'spot_id': str(spot.id), 'count': count})

    # Сортируем по количеству (больше = выше)
    result.sort(key=lambda x: x['count'], reverse=True)
    return result


def get_priority_alerts(company: Company, limit: int = 3) -> list[dict]:
    """
    Получить топ проблем по приоритету.

    Возвращает до `limit` проблем, начиная с самых критичных.
    Если критичных нет — показывает серьёзные, затем важные.

    Returns:
        [
            {
                'key': 'poisoning',
                'label': 'Отравления',
                'level': 'critical',
                'count': 2,
                'last_date': datetime,
                'last_spot': 'Невский',
                'color_border': '#ef4444',
                'color_bg': '#fef2f2',
            },
            ...
        ]
    """
    # Берём ВСЕ отзывы (любой рейтинг) — проблемы безопасности важны даже в позитивных
    all_reviews = Review.objects.filter(
        company=company
    ).select_related('spot').order_by('-created_at')

    # Собираем статистику по каждому типу проблемы
    problem_stats = {}

    for review in all_reviews:
        text_lower = (review.text or '').lower()

        for problem in PROBLEM_PATTERNS:
            key = problem['key']

            # Проверяем паттерны
            matched = any(p in text_lower for p in problem['patterns'])
            if not matched:
                continue

            if key not in problem_stats:
                problem_stats[key] = {
                    'key': key,
                    'label': problem['label'],
                    'level': problem['level'],
                    'count': 0,
                    'last_date': None,
                    'last_spot': None,
                    'reviews': [],
                }

            problem_stats[key]['count'] += 1

            # Запоминаем последний отзыв (первый в списке = самый свежий)
            if problem_stats[key]['last_date'] is None:
                problem_stats[key]['last_date'] = review.created_at
                problem_stats[key]['last_spot'] = review.spot.name if review.spot else None

    # Сортируем по приоритету уровня, затем по количеству
    alerts = list(problem_stats.values())
    alerts.sort(key=lambda x: (LEVEL_PRIORITY[x['level']], -x['count']))

    # Добавляем цвета и ограничиваем количество
    result = []
    for alert in alerts[:limit]:
        colors = LEVEL_COLORS.get(alert['level'], {})
        alert['color_border'] = colors.get('border', '#999')
        alert['color_bg'] = colors.get('bg', '#f5f5f5')
        result.append(alert)

    return result


def has_critical_alerts(alerts: list[dict]) -> bool:
    """Проверить есть ли критические проблемы."""
    return any(a['level'] == 'critical' for a in alerts)


# === Топ жалоб и похвал ===

# Маппинг конкретных проблем на человекочитаемые описания
COMPLAINT_PATTERNS = {
    # Ожидание
    'долго': 'Долгое ожидание',
    'ждать': 'Долгое ожидание',
    'медленно': 'Долгое ожидание',
    'час': 'Долгое ожидание',

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
    'хам': 'Грубый персонал',
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


# === Сравнение по точкам ===

def get_spots_comparison(
    company: Company,
    start_date: Any = None,
    end_date: Any = None
) -> list[dict]:
    """
    Сравнение статистики по точкам/филиалам.

    Returns:
        [{'name': 'Тверская', 'rating': 4.5, 'negative_pct': 8, 'trend': 'up', 'count': 234}, ...]
    """
    spots = Spot.objects.filter(company=company, is_active=True)
    if not spots.exists():
        return []

    results = []
    week_ago = timezone.now() - timedelta(days=7)

    for spot in spots:
        # Основная статистика за период
        reviews = Review.objects.filter(company=company, spot=spot)
        if start_date:
            reviews = reviews.filter(created_at__gte=start_date)
        if end_date:
            reviews = reviews.filter(created_at__lt=end_date)

        total = reviews.count()
        if total == 0:
            continue

        stats = reviews.aggregate(
            avg_rating=Avg('rating'),
            negative=Count('id', filter=Q(rating__lte=3))
        )

        avg_rating = stats['avg_rating'] or 0
        negative_count = stats['negative'] or 0
        negative_pct = round(negative_count / total * 100) if total > 0 else 0

        # Тренд: сравниваем с предыдущей неделей
        recent = reviews.filter(created_at__gte=week_ago)
        recent_stats = recent.aggregate(avg_rating=Avg('rating'))
        recent_rating = recent_stats['avg_rating']

        if recent_rating and avg_rating:
            if recent_rating > avg_rating + 0.1:
                trend = 'up'
            elif recent_rating < avg_rating - 0.1:
                trend = 'down'
            else:
                trend = 'stable'
        else:
            trend = 'stable'

        results.append({
            'id': str(spot.id),
            'name': spot.name,
            'rating': round(avg_rating, 1),
            'negative_pct': negative_pct,
            'trend': trend,
            'count': total,
        })

    # Сортируем по рейтингу (худшие внизу)
    results.sort(key=lambda x: x['rating'], reverse=True)

    return results


# === Простые метрики ===

def get_simple_metrics(
    reviews_qs: QuerySet,
    prev_reviews_qs: QuerySet = None
) -> dict:
    """
    Простые метрики с трендами.

    Returns:
        {
            'rating': 4.3,
            'rating_trend': 'up',  # up/down/stable
            'rating_delta': +0.2,
            'negative_pct': 15,
            'negative_trend': 'down',
            'total': 1897
        }
    """
    total = reviews_qs.count()
    if total == 0:
        return {
            'rating': 0, 'rating_trend': 'stable', 'rating_delta': 0,
            'negative_pct': 0, 'negative_trend': 'stable', 'total': 0
        }

    stats = reviews_qs.aggregate(
        avg_rating=Avg('rating'),
        negative=Count('id', filter=Q(rating__lte=3))
    )

    rating = round(stats['avg_rating'] or 0, 1)
    negative_pct = round((stats['negative'] or 0) / total * 100)

    # Тренды
    rating_trend = 'stable'
    rating_delta = 0
    negative_trend = 'stable'

    if prev_reviews_qs is not None and prev_reviews_qs.exists():
        prev_total = prev_reviews_qs.count()
        prev_stats = prev_reviews_qs.aggregate(
            avg_rating=Avg('rating'),
            negative=Count('id', filter=Q(rating__lte=3))
        )

        prev_rating = prev_stats['avg_rating'] or 0
        prev_negative_pct = round((prev_stats['negative'] or 0) / prev_total * 100) if prev_total > 0 else 0

        rating_delta = round(rating - prev_rating, 1)
        if rating_delta > 0.1:
            rating_trend = 'up'
        elif rating_delta < -0.1:
            rating_trend = 'down'

        if negative_pct < prev_negative_pct - 2:
            negative_trend = 'down'  # негатив уменьшается = хорошо
        elif negative_pct > prev_negative_pct + 2:
            negative_trend = 'up'  # негатив растёт = плохо

    return {
        'rating': rating,
        'rating_trend': rating_trend,
        'rating_delta': rating_delta,
        'negative_pct': negative_pct,
        'negative_trend': negative_trend,
        'total': total,
    }

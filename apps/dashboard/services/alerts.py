"""
Dashboard alerts: приоритетные проблемы и требующие внимания.
"""
from collections import Counter
from datetime import timedelta

from django.db.models import QuerySet
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
    Каждая проблема содержит список точек с количеством и датой,
    отсортированный по свежести (свежие сверху).
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
                    'spots_data': {},
                }

            problem_stats[key]['count'] += 1

            # Собираем статистику по точкам
            spot_name = review.spot.name if review.spot else 'Без точки'
            if spot_name not in problem_stats[key]['spots_data']:
                problem_stats[key]['spots_data'][spot_name] = {
                    'name': spot_name,
                    'count': 0,
                    'last_date': review.created_at,
                }
            problem_stats[key]['spots_data'][spot_name]['count'] += 1

    # Сортируем по приоритету уровня, затем по количеству
    alerts = list(problem_stats.values())
    alerts.sort(key=lambda x: (LEVEL_PRIORITY[x['level']], -x['count']))

    # Добавляем цвета, формируем список точек и ограничиваем количество
    result = []
    for alert in alerts[:limit]:
        colors = LEVEL_COLORS.get(alert['level'], {})
        alert['color_border'] = colors.get('border', '#999')
        alert['color_bg'] = colors.get('bg', '#f5f5f5')

        # Преобразуем spots_data в отсортированный список (свежие сверху)
        spots_list = list(alert['spots_data'].values())
        spots_list.sort(key=lambda x: x['last_date'], reverse=True)
        alert['spots'] = spots_list
        del alert['spots_data']

        result.append(alert)

    return result


def has_critical_alerts(alerts: list[dict]) -> bool:
    """Проверить есть ли критические проблемы."""
    return any(a['level'] == 'critical' for a in alerts)

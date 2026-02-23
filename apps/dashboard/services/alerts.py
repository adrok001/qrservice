"""
Dashboard alerts: приоритетные проблемы и требующие внимания.
"""
from datetime import timedelta

from django.utils import timezone

from apps.companies.models import Company
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
    'critical': {'border': '#ef4444', 'bg_rgb': (254, 202, 202)},   # red-200
    'serious': {'border': '#f97316', 'bg_rgb': (254, 215, 170)},    # orange-200
    'important': {'border': '#eab308', 'bg_rgb': (254, 240, 138)},  # yellow-200
}

# Временные окна по уровню критичности (дни)
LEVEL_WINDOWS = {'critical': 180, 'serious': 90, 'important': 30}

# Человекочитаемые подписи окон
LEVEL_WINDOW_LABELS = {'critical': '6 мес.', 'serious': '3 мес.', 'important': '30 дн.'}

# Минимальный порог срабатывания
LEVEL_THRESHOLDS = {'critical': 1, 'serious': 2, 'important': 3}


# === Требует внимания ===

def get_priority_alerts(company: Company, limit: int = 3) -> list[dict]:
    """
    Получить топ проблем по приоритету с временными окнами и трендами.

    Каждый уровень критичности имеет своё окно:
    - critical: 180 дней (редкие, но опасные)
    - serious: 90 дней (системные проблемы)
    - important: 30 дней (операционные)

    Тренд: сравнение текущего окна с предыдущим аналогичным периодом.
    """
    now = timezone.now()
    max_window = max(LEVEL_WINDOWS.values())

    # Загружаем отзывы за двойное макс. окно (текущий + предыдущий период для тренда)
    cutoff = now - timedelta(days=max_window * 2)
    all_reviews = Review.objects.filter(
        company=company,
        created_at__gte=cutoff,
    ).select_related('spot').order_by('-created_at')

    # Собираем статистику: текущее окно + предыдущее (для тренда)
    problem_stats = {}

    for review in all_reviews:
        text_lower = (review.text or '').lower()
        review_age = (now - review.created_at).days

        for problem in PROBLEM_PATTERNS:
            key = problem['key']
            level = problem['level']
            window = LEVEL_WINDOWS[level]

            # Отзыв за пределами двойного окна этого уровня — пропускаем
            if review_age > window * 2:
                continue

            # Проверяем паттерны
            if not any(p in text_lower for p in problem['patterns']):
                continue

            in_current = review_age <= window
            in_previous = window < review_age <= window * 2

            if key not in problem_stats:
                problem_stats[key] = {
                    'key': key,
                    'label': problem['label'],
                    'level': level,
                    'window_days': window,
                    'window_label': LEVEL_WINDOW_LABELS[level],
                    'count': 0,
                    'prev_count': 0,
                    'spots_data': {},
                }

            if in_current:
                problem_stats[key]['count'] += 1

                # Точки — только для текущего периода
                spot_name = review.spot.name if review.spot else 'Без точки'
                if spot_name not in problem_stats[key]['spots_data']:
                    problem_stats[key]['spots_data'][spot_name] = {
                        'name': spot_name,
                        'count': 0,
                        'last_date': review.created_at,
                    }
                problem_stats[key]['spots_data'][spot_name]['count'] += 1

            elif in_previous:
                problem_stats[key]['prev_count'] += 1

    # Фильтруем по порогу, вычисляем тренд
    alerts = []
    for stats in problem_stats.values():
        if stats['count'] < LEVEL_THRESHOLDS[stats['level']]:
            continue

        stats['trend'] = _calc_trend(stats['count'], stats['prev_count'])
        alerts.append(stats)

    # Сортируем по приоритету уровня, затем по количеству
    alerts.sort(key=lambda x: (LEVEL_PRIORITY[x['level']], -x['count']))

    # Добавляем цвета, формируем список точек
    result = []
    for alert in alerts[:limit]:
        colors = LEVEL_COLORS.get(alert['level'], {})
        alert['color_border'] = colors.get('border', '#999')

        # Числовая дельта (B: Power BI-стиль)
        alert['delta'] = abs(alert['count'] - alert['prev_count'])
        del alert['prev_count']

        # Насыщенность фона по количеству (C: Power BI-стиль)
        # intensity: 0.15 (1 шт) → 0.55 (4+ шт) — как alpha канал
        intensity = min(0.15 + (alert['count'] - 1) * 0.15, 0.55)
        r, g, b = colors.get('bg_rgb', (200, 200, 200))
        alert['color_bg'] = f'rgba({r}, {g}, {b}, {intensity:.2f})'

        # Преобразуем spots_data в отсортированный список (свежие сверху)
        spots_list = list(alert['spots_data'].values())
        spots_list.sort(key=lambda x: x['last_date'], reverse=True)
        alert['spots'] = spots_list
        del alert['spots_data']

        result.append(alert)

    return result


def _calc_trend(current: int, previous: int) -> str:
    """Вычислить тренд: up/down/stable/new."""
    if previous == 0:
        return 'new' if current > 0 else 'stable'
    if current > previous:
        return 'up'
    if current < previous:
        return 'down'
    return 'stable'


def has_critical_alerts(alerts: list[dict]) -> bool:
    """Проверить есть ли критические проблемы."""
    return any(a['level'] == 'critical' for a in alerts)

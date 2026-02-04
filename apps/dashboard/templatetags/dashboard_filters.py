"""Custom template filters for dashboard."""
import re
from django import template
from django.utils.timesince import timesince

register = template.Library()


@register.filter
def shorttime(value):
    """
    Сокращает timesince до короткого формата.

    "1 месяц, 2 недели" → "1м"
    "3 дня, 5 часов" → "3д"
    "2 недели, 1 день" → "2н"
    """
    if not value:
        return ''

    # Получаем timesince строку
    time_str = timesince(value)

    # Берём только первую часть (до запятой)
    first_part = time_str.split(',')[0].strip()

    # Извлекаем число и единицу
    match = re.match(r'(\d+)\s+(.+)', first_part)
    if not match:
        return first_part

    num = match.group(1)
    unit = match.group(2).lower()

    # Сокращаем
    if 'минут' in unit:
        return f'{num}мин'
    elif 'час' in unit:
        return f'{num}ч'
    elif 'д' in unit and ('день' in unit or 'дня' in unit or 'дней' in unit):
        return f'{num}д'
    elif 'недел' in unit:
        return f'{num}н'
    elif 'месяц' in unit:
        return f'{num}м'
    elif 'год' in unit or 'лет' in unit:
        return f'{num}г'

    return first_part

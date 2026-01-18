"""
Кэширование анализа отзывов.

Кэширует результаты ML-анализа и определения категорий.
В production использует Redis, в development — локальный кэш.
"""
import hashlib
from typing import List, Dict, Tuple, Optional

from django.core.cache import cache

from .services import analyze_review_impressions

# Время жизни кэша: 7 дней (анализ стабилен)
CACHE_TIMEOUT = 60 * 60 * 24 * 7


def _make_cache_key(text: str, rating: int) -> str:
    """Создать ключ кэша на основе хэша текста и рейтинга."""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:16]
    return f"review_analysis:{text_hash}:{rating}"


def get_analysis_cached(
    text: str,
    rating: int,
    force_refresh: bool = False
) -> Tuple[List[Dict[str, str]], float]:
    """
    Получить анализ отзыва из кэша или выполнить анализ.

    Args:
        text: Текст отзыва
        rating: Рейтинг (1-5)
        force_refresh: Принудительно обновить кэш

    Returns:
        Tuple[tags, ml_score]
    """
    if not text or not text.strip():
        return [], 0.5

    key = _make_cache_key(text, rating)

    if not force_refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    # Выполняем анализ
    result = analyze_review_impressions(text, rating)
    cache.set(key, result, CACHE_TIMEOUT)
    return result


def invalidate_analysis_cache(text: str, rating: int) -> None:
    """Инвалидировать кэш для конкретного отзыва."""
    key = _make_cache_key(text, rating)
    cache.delete(key)


def clear_all_analysis_cache() -> None:
    """Очистить весь кэш анализа (использовать осторожно)."""
    cache.clear()

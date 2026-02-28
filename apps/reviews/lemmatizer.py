"""
Лемматизатор для анализа тональности отзывов.
Использует pymorphy3 для приведения слов к начальной форме.
"""
from functools import lru_cache

import pymorphy3

# Ленивая инициализация морфологического анализатора
_morph = None


def _get_morph():
    """Ленивая загрузка морфологического анализатора."""
    global _morph
    if _morph is None:
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


@lru_cache(maxsize=10000)
def get_lemma(word: str) -> str:
    """Получить лемму (начальную форму) слова с кэшированием."""
    morph = _get_morph()
    parsed = morph.parse(word)
    if parsed:
        return parsed[0].normal_form
    return word

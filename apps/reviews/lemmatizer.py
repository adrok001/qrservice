"""
Лемматизатор для анализа тональности отзывов.
Использует pymorphy3 для приведения слов к начальной форме.
"""
import re
from functools import lru_cache
from typing import Tuple

import pymorphy3

from .dictionaries import (
    NEGATIVE_LEMMAS,
    POSITIVE_LEMMAS,
    NEGATIVE_PHRASES,
    POSITIVE_PHRASES,
    NEGATABLE_WORDS,
    NEGATIVE_WITHOUT_CONSTRUCTS,
    WAIT_TIME_PATTERNS,
)

# Реэкспорт для обратной совместимости
__all__ = [
    'get_lemma',
    'lemmatize_text',
    'has_negative_sentiment',
    'has_positive_sentiment',
    'detect_sentiment',
    'NEGATIVE_LEMMAS',
    'POSITIVE_LEMMAS',
    'NEGATIVE_PHRASES',
    'POSITIVE_PHRASES',
    'NEGATABLE_WORDS',
    'NEGATIVE_WITHOUT_CONSTRUCTS',
    'WAIT_TIME_PATTERNS',
]

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


def lemmatize_text(text: str) -> list[str]:
    """Лемматизировать текст, вернуть список лемм."""
    words = re.findall(r'[а-яёА-ЯЁ]+', text.lower())
    return [get_lemma(word) for word in words]


def has_negative_sentiment(text: str) -> Tuple[bool, list[str]]:
    """Проверить наличие негативной тональности в тексте."""
    text_lower = text.lower()
    found = []

    # Проверяем фразы
    for phrase in NEGATIVE_PHRASES:
        if phrase in text_lower:
            found.append(phrase)

    # Проверяем леммы
    for lemma in lemmatize_text(text):
        if lemma in NEGATIVE_LEMMAS:
            found.append(lemma)

    # Проверяем отрицания
    words = re.findall(r'[а-яёА-ЯЁ]+', text_lower)
    for i, word in enumerate(words):
        if i > 0 and words[i - 1] in ('не', 'нет', 'ни'):
            lemma = get_lemma(word)
            if lemma in POSITIVE_LEMMAS or lemma in NEGATABLE_WORDS:
                found.append(f'не {word}')

    # Проверяем конструкции с "без"
    for i, word in enumerate(words):
        if word == 'без' and i + 1 < len(words):
            next_lemma = get_lemma(words[i + 1])
            if next_lemma in NEGATIVE_WITHOUT_CONSTRUCTS:
                found.append(f'без {words[i + 1]}')

    # Проверяем время ожидания
    for pattern in WAIT_TIME_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            found.append(f'долгое ожидание: {match.group(0)}')

    return (len(found) > 0, found)


def has_positive_sentiment(text: str) -> Tuple[bool, list[str]]:
    """Проверить наличие позитивной тональности в тексте."""
    text_lower = text.lower()
    found = []

    for phrase in POSITIVE_PHRASES:
        if phrase in text_lower:
            found.append(phrase)

    for lemma in lemmatize_text(text):
        if lemma in POSITIVE_LEMMAS:
            found.append(lemma)

    return (len(found) > 0, found)


def detect_sentiment(text: str, rating: int = 3) -> Tuple[str, list[str], list[str]]:
    """Определить тональность текста с учётом рейтинга."""
    has_neg, neg_markers = has_negative_sentiment(text)
    has_pos, pos_markers = has_positive_sentiment(text)

    if has_neg and not has_pos:
        return ('negative', neg_markers, pos_markers)
    if has_pos and not has_neg:
        return ('positive', neg_markers, pos_markers)
    if has_neg and has_pos:
        if rating <= 2:
            return ('negative', neg_markers, pos_markers)
        if rating >= 4:
            return ('positive', neg_markers, pos_markers)
        return ('neutral', neg_markers, pos_markers)

    if rating <= 2:
        return ('negative', neg_markers, pos_markers)
    if rating >= 4:
        return ('positive', neg_markers, pos_markers)
    return ('neutral', neg_markers, pos_markers)

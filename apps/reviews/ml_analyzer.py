"""
ML-анализатор тональности отзывов.
Использует rubert-tiny2 для русского языка.
"""
from functools import lru_cache
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

# Lazy loading — модель загружается при первом вызове
_classifier = None


def _get_classifier():
    """Загрузка модели (singleton)."""
    global _classifier
    if _classifier is None:
        from transformers import pipeline
        _classifier = pipeline(
            "sentiment-analysis",
            model="seara/rubert-tiny2-russian-sentiment",
            device=-1,  # CPU
        )
        logger.info("ML sentiment model loaded")
    return _classifier


def analyze_sentiment_ml(text: str) -> Tuple[str, float]:
    """
    Анализ тональности текста через ML.

    Returns:
        (sentiment, score) — ('positive'|'negative'|'neutral', 0.0-1.0)
    """
    if not text or not text.strip():
        return ('neutral', 0.5)

    try:
        classifier = _get_classifier()
        result = classifier(text[:512])[0]  # Ограничение по токенам
        label = result['label'].lower()
        score = result['score']

        # Нормализация меток модели
        sentiment_map = {
            'positive': 'positive',
            'negative': 'negative',
            'neutral': 'neutral',
        }
        sentiment = sentiment_map.get(label, 'neutral')

        return (sentiment, score)
    except Exception as e:
        logger.warning(f"ML analysis failed: {e}")
        return ('neutral', 0.5)


def sentiment_to_score(sentiment: str, confidence: float) -> float:
    """Конвертация в score от -1.0 до +1.0."""
    if sentiment == 'positive':
        return round(confidence, 2)
    elif sentiment == 'negative':
        return round(-confidence, 2)
    return 0.0

"""
ML-анализатор тональности отзывов.

Поддерживает два режима:
- ONNX Runtime (по умолчанию) — быстрее, меньше зависимостей
- Transformers pipeline (fallback) — если ONNX недоступен
"""
import os
import logging
from pathlib import Path
from typing import Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Пути к моделям
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ONNX_MODEL_DIR = BASE_DIR / 'models' / 'rubert-sentiment-onnx'

# Lazy loading
_onnx_session = None
_onnx_tokenizer = None
_transformers_classifier = None


def _load_onnx_model():
    """Загрузка ONNX модели и токенизатора."""
    global _onnx_session, _onnx_tokenizer

    if _onnx_session is not None:
        return True

    model_path = ONNX_MODEL_DIR / 'model.onnx'
    if not model_path.exists():
        logger.warning(f"ONNX model not found at {model_path}")
        return False

    try:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        _onnx_session = ort.InferenceSession(
            str(model_path),
            providers=['CPUExecutionProvider']
        )
        _onnx_tokenizer = AutoTokenizer.from_pretrained(
            str(ONNX_MODEL_DIR),
            local_files_only=True
        )
        logger.info("ONNX sentiment model loaded")
        return True
    except Exception as e:
        logger.warning(f"Failed to load ONNX model: {e}")
        return False


def _load_transformers_model():
    """Загрузка модели через transformers (fallback)."""
    global _transformers_classifier

    if _transformers_classifier is not None:
        return True

    try:
        from transformers import pipeline
        _transformers_classifier = pipeline(
            "sentiment-analysis",
            model="seara/rubert-tiny2-russian-sentiment",
            device=-1,
        )
        logger.info("Transformers sentiment model loaded")
        return True
    except Exception as e:
        logger.warning(f"Failed to load transformers model: {e}")
        return False


def _analyze_with_onnx(text: str) -> Tuple[str, float]:
    """Анализ через ONNX Runtime."""
    inputs = _onnx_tokenizer(
        text[:512],
        return_tensors='np',
        truncation=True,
        padding=True
    )

    outputs = _onnx_session.run(
        None,
        {
            'input_ids': inputs['input_ids'].astype(np.int64),
            'attention_mask': inputs['attention_mask'].astype(np.int64)
        }
    )

    logits = outputs[0][0]
    probabilities = _softmax(logits)
    predicted_class = int(np.argmax(probabilities))
    confidence = float(probabilities[predicted_class])

    # Маппинг классов (из config.json модели)
    label_map = {0: 'neutral', 1: 'positive', 2: 'negative'}
    sentiment = label_map.get(predicted_class, 'neutral')

    return (sentiment, confidence)


def _softmax(x):
    """Softmax для numpy."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()


def _analyze_with_transformers(text: str) -> Tuple[str, float]:
    """Анализ через transformers pipeline."""
    result = _transformers_classifier(text[:512])[0]
    label = result['label'].lower()
    score = result['score']

    sentiment_map = {'positive': 'positive', 'negative': 'negative', 'neutral': 'neutral'}
    sentiment = sentiment_map.get(label, 'neutral')

    return (sentiment, score)


def analyze_sentiment_ml(text: str) -> Tuple[str, float]:
    """
    Анализ тональности текста через ML.

    Приоритет: ONNX → Transformers → fallback neutral.

    Returns:
        (sentiment, score) — ('positive'|'negative'|'neutral', 0.0-1.0)
    """
    if not text or not text.strip():
        return ('neutral', 0.5)

    try:
        # Пробуем ONNX (быстрее, меньше RAM)
        if _onnx_session is not None or _load_onnx_model():
            return _analyze_with_onnx(text)

        # Fallback на transformers
        if _transformers_classifier is not None or _load_transformers_model():
            return _analyze_with_transformers(text)

        logger.error("No ML model available")
        return ('neutral', 0.5)
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

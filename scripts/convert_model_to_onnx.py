#!/usr/bin/env python
"""
Скрипт конвертации ML модели в ONNX формат.

Запуск: python scripts/convert_model_to_onnx.py
"""
import os
import sys
import json
from pathlib import Path

# Добавляем корень проекта в путь
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

MODEL_NAME = 'seara/rubert-tiny2-russian-sentiment'
OUTPUT_DIR = BASE_DIR / 'models' / 'rubert-sentiment-onnx'


def main():
    print(f'Конвертация {MODEL_NAME} в ONNX...')
    print(f'Директория: {OUTPUT_DIR}')

    # Создаём директорию
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Импортируем зависимости
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
    except ImportError as e:
        print(f'Ошибка: {e}')
        print('Установите: pip install torch transformers')
        return 1

    # Загружаем модель
    print('Загрузка модели...')
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()

    # Экспортируем в ONNX
    print('Экспорт в ONNX...')
    dummy_input = tokenizer('Тестовый текст', return_tensors='pt')

    torch.onnx.export(
        model,
        (dummy_input['input_ids'], dummy_input['attention_mask']),
        str(OUTPUT_DIR / 'model.onnx'),
        input_names=['input_ids', 'attention_mask'],
        output_names=['logits'],
        dynamic_axes={
            'input_ids': {0: 'batch', 1: 'sequence'},
            'attention_mask': {0: 'batch', 1: 'sequence'},
            'logits': {0: 'batch'}
        },
        opset_version=14
    )

    # Сохраняем токенизатор
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    # Сохраняем конфиг
    config = model.config.to_dict()
    with open(OUTPUT_DIR / 'config.json', 'w') as f:
        json.dump(config, f)

    print(f'Готово! Модель сохранена в {OUTPUT_DIR}')

    # Показываем размер
    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.glob('*') if f.is_file())
    print(f'Размер: {total_size / 1024 / 1024:.1f} MB')

    return 0


if __name__ == '__main__':
    sys.exit(main())

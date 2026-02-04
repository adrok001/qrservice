"""
Management command для импорта демо-отзывов из CSV/Excel.
Анонимизирует данные и создаёт демо-компанию с реальными отзывами.
"""
import re
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

import pandas as pd

from apps.companies.models import Company, Spot
from apps.reviews.models import Review
from apps.reviews.services import analyze_review_impressions


# Маппинг адресов для анонимизации (Ижевск → Москва, Пермь → СПб)
# Ключи должны точно соответствовать адресам в Excel/CSV файле
ADDRESS_MAP = {
    'Россия, г Ижевск, ул 9 Января, д 213': 'Москва, Тверская',
    'Россия, г Ижевск, ул Карла Маркса, д 244': 'Москва, Арбат',
    'Россия, г Ижевск, ул Клубная, зд 47А': 'Москва, Новый Арбат',
    'Россия, г Ижевск, ул Пушкинская, д 165': 'Москва, Петровка',
    'Россия, г Ижевск, ул Пушкинская, д 268Г': 'Москва, Дмитровка',
    'Россия, г Пермь, Комсомольский пр-кт, д 36': 'Санкт-Петербург, Невский',
}

# Провайдеры → source
SOURCE_MAP = {
    'yandex': 'yandex',
    'Яндекс': 'yandex',
    '2gis': '2gis',
    '2ГИС': '2gis',
    'google': 'google',
    'Google': 'google',
}


def anonymize_author(name: str) -> str:
    """Сокращает имя автора: 'Ирина Петрова' → 'Ирина П.'"""
    if not name:
        return 'Аноним'

    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0]

    # Берём первое имя + первая буква фамилии
    first_name = parts[0]
    last_initial = parts[1][0] if parts[1] else ''
    return f'{first_name} {last_initial}.' if last_initial else first_name


def anonymize_text(text: str) -> str:
    """Удаляет упоминания бренда, номера телефонов, URL из текста."""
    if not text:
        return ''

    result = text

    # Удаляем упоминания "Арчи", "Дядя Арчи" и т.п.
    result = re.sub(r'\b[Дд]яд[яеюи]\s+[Аа]рчи\b', 'этот ресторан', result)
    result = re.sub(r'\b[Аа]рчи\b', 'ресторан', result)

    # Удаляем номера телефонов (WhatsApp и др.)
    result = re.sub(r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', '[телефон удалён]', result)
    result = re.sub(r'whatsapp[:\s]*\S+', '', result, flags=re.IGNORECASE)

    # Удаляем URL
    result = re.sub(r'https?://\S+', '', result)
    result = re.sub(r'www\.\S+', '', result)

    # Удаляем лишние пробелы
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def parse_date(date_str: str) -> datetime:
    """Парсит дату из CSV."""
    if not date_str:
        return timezone.now()

    # Пробуем разные форматы
    formats = [
        '%d.%m.%Y %H:%M',
        '%d.%m.%Y %H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%d.%m.%Y',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return timezone.make_aware(dt)
        except ValueError:
            continue

    return timezone.now()


class Command(BaseCommand):
    help = 'Импортирует демо-отзывы из CSV или Excel файла'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='Путь к CSV или Excel файлу')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет сделано без внесения изменений'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Удалить старые демо-отзывы перед импортом'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']
        clear = options['clear']

        self.stdout.write(f'Импорт из: {file_path}')

        # Создаём или получаем демо-компанию
        demo_company, created = Company.objects.get_or_create(
            slug='demo-restaurant-network',
            defaults={
                'name': 'Демо: Сеть ресторанов',
                'is_demo': True,
                'is_chain': True,
                'is_active': True,
                'address': 'г. Москва',
                'city': 'Москва',
                'description': 'Демонстрационная компания с реальными анонимизированными отзывами',
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Создана демо-компания: {demo_company.name}'))
        else:
            self.stdout.write(f'Используем существующую компанию: {demo_company.name}')
            # Обновляем флаг is_demo если нужно
            if not demo_company.is_demo:
                demo_company.is_demo = True
                demo_company.save(update_fields=['is_demo'])

        # Создаём точки (Spots) для каждого адреса
        spots = {}
        for original_addr, anon_name in ADDRESS_MAP.items():
            # anon_name уже в формате "Москва, Тверская"
            spot, created = Spot.objects.get_or_create(
                company=demo_company,
                name=anon_name,
                defaults={
                    'zone': anon_name.split(', ')[0] if ', ' in anon_name else anon_name,
                    'is_active': True,
                }
            )
            spots[original_addr] = spot
            status = 'создана' if created else 'существует'
            self.stdout.write(f'  Точка: {spot.name} ({status})')

        # Очищаем старые данные если нужно
        if clear and not dry_run:
            old_count = Review.objects.filter(company=demo_company).count()
            Review.objects.filter(company=demo_company).delete()
            self.stdout.write(self.style.WARNING(f'Удалено {old_count} старых отзывов'))

        # Читаем файл (CSV или Excel)
        try:
            if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                df = pd.read_excel(file_path)
            else:
                # Пробуем CSV с разными кодировками
                for encoding in ['utf-8-sig', 'utf-8', 'cp1251']:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding, sep=None, engine='python')
                        break
                    except Exception:
                        continue
                else:
                    raise ValueError('Не удалось прочитать CSV')

            self.stdout.write(f'Файл прочитан: {len(df)} строк')
            self.stdout.write(f'Колонки: {list(df.columns)}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка чтения файла: {e}'))
            return

        # Обрабатываем строки
        imported = 0
        skipped = 0
        errors = 0

        for _, row in df.iterrows():
            try:
                result = self.process_row(row.to_dict(), demo_company, spots, dry_run)
                if result == 'imported':
                    imported += 1
                elif result == 'skipped':
                    skipped += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    self.stdout.write(self.style.WARNING(f'Ошибка в строке: {e}'))

        # Итоги
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{prefix}Импорт завершён:\n'
            f'  Импортировано: {imported}\n'
            f'  Пропущено (дубли): {skipped}\n'
            f'  Ошибок: {errors}'
        ))

    def process_row(self, row: dict, company: Company, spots: dict, dry_run: bool) -> str:
        """Обрабатывает одну строку из файла."""
        # Получаем данные с учётом разных названий колонок
        def get_col(names):
            for name in names:
                if name in row:
                    val = row[name]
                    # Проверяем на NaN (pandas) и пустые значения
                    if pd.isna(val) or val is None:
                        continue
                    val_str = str(val).strip()
                    if val_str:
                        return val_str
            return ''

        original_addr = get_col(['Адрес', 'адрес', 'Address'])
        rating_str = get_col(['Рейтинг', 'рейтинг', 'Rating', 'Оценка'])
        text = get_col(['Отзыв', 'отзыв', 'Review', 'Текст', 'текст'])
        response = get_col(['Ответ', 'ответ', 'Response', 'Ответ компании'])
        author = get_col(['Автор', 'автор', 'Author', 'Имя'])
        date_str = get_col(['Дата публикации по мск', 'Дата', 'дата', 'Date', 'Дата отзыва'])
        source_str = get_col(['Провайдер', 'провайдер', 'Source', 'Источник', 'Платформа'])

        # Парсим рейтинг
        try:
            rating = int(float(rating_str)) if rating_str else 5
            rating = max(1, min(5, rating))
        except (ValueError, TypeError):
            rating = 5

        # Определяем источник
        source = SOURCE_MAP.get(source_str, 'internal')

        # Получаем точку
        spot = spots.get(original_addr)

        # Анонимизируем данные
        anon_author = anonymize_author(author)
        anon_text = anonymize_text(text)
        anon_response = anonymize_text(response)
        created_at = parse_date(date_str)

        # Проверяем дубликаты (по тексту и дате)
        if Review.objects.filter(
            company=company,
            text=anon_text,
            created_at__date=created_at.date()
        ).exists():
            return 'skipped'

        if dry_run:
            self.stdout.write(f'  [{rating}★] {anon_author}: {anon_text[:50]}...')
            return 'imported'

        # Анализируем текст нашей системой
        tags, sentiment_score = analyze_review_impressions(anon_text, rating)

        # Создаём отзыв (используем update для обхода auto_now_add)
        review = Review(
            company=company,
            source=source,
            spot=spot,
            rating=rating,
            text=anon_text,
            author_name=anon_author,
            response=anon_response,
            tags=tags,
            sentiment_score=sentiment_score,
        )
        review.save()
        # Обновляем created_at напрямую (обход auto_now_add)
        Review.objects.filter(pk=review.pk).update(created_at=created_at)

        return 'imported'

"""
Management command для переанализа всех отзывов.

Использует обновлённые словари и правила segment_analyzer
для пересчёта tags и sentiment_score.
"""
from django.core.management.base import BaseCommand

from apps.reviews.models import Review
from apps.reviews.services import analyze_review_impressions


class Command(BaseCommand):
    help = 'Переанализировать все отзывы с обновлёнными словарями'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать изменения без сохранения',
        )
        parser.add_argument(
            '--rating',
            type=int,
            choices=[1, 2, 3, 4, 5],
            help='Переанализировать только отзывы с указанным рейтингом',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        rating_filter = options.get('rating')

        qs = Review.objects.all()
        if rating_filter:
            qs = qs.filter(rating=rating_filter)

        total = qs.count()
        updated = 0
        changed_tags = 0
        changed_score = 0

        self.stdout.write(f'Переанализ {total} отзывов...')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — изменения не сохраняются'))

        for i, review in enumerate(qs.iterator(), 1):
            if not review.text:
                continue

            new_tags, new_score = analyze_review_impressions(review.text, review.rating)
            new_score = round(float(new_score), 2)
            old_score = float(review.sentiment_score) if review.sentiment_score is not None else None

            tags_differ = new_tags != review.tags
            score_differs = new_score != old_score

            if tags_differ or score_differs:
                if tags_differ:
                    changed_tags += 1
                if score_differs:
                    changed_score += 1

                if not dry_run:
                    review.tags = new_tags
                    review.sentiment_score = new_score
                    review.save(update_fields=['tags', 'sentiment_score', 'updated_at'])
                updated += 1

            if i % 500 == 0:
                self.stdout.write(f'  Обработано {i}/{total}...')

        self.stdout.write(self.style.SUCCESS(
            f'Готово: {updated}/{total} отзывов обновлено '
            f'(теги: {changed_tags}, score: {changed_score})'
        ))

        # Статистика по тегам
        if not dry_run and updated > 0:
            self._print_stats()

    def _print_stats(self):
        """Вывести статистику по тегам после переанализа."""
        from collections import Counter
        reviews = Review.objects.exclude(tags=[])
        cat_counter = Counter()
        subcat_counter = Counter()
        tag_counts = []

        for review in reviews.iterator():
            tags = review.tags or []
            tag_counts.append(len(tags))
            for tag in tags:
                cat_counter[tag.get('category', '?')] += 1
                subcat_counter[tag.get('subcategory', '?')] += 1

        if tag_counts:
            avg_tags = sum(tag_counts) / len(tag_counts)
            self.stdout.write(f'\nСреднее тегов на отзыв: {avg_tags:.2f}')

        self.stdout.write('\nТоп-10 подкатегорий:')
        for subcat, count in subcat_counter.most_common(10):
            self.stdout.write(f'  {subcat}: {count}')

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Review(models.Model):
    """Отзыв (внутренний или внешний)"""

    class Source(models.TextChoices):
        INTERNAL = 'internal', 'Наш сервис'
        YANDEX = 'yandex', 'Яндекс Карты'
        TWOGIS = '2gis', '2GIS'
        GOOGLE = 'google', 'Google Maps'
        TRIPADVISOR = 'tripadvisor', 'TripAdvisor'

    class Sentiment(models.TextChoices):
        POSITIVE = 'positive', 'Позитивный'
        NEUTRAL = 'neutral', 'Нейтральный'
        NEGATIVE = 'negative', 'Негативный'

    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        IN_PROGRESS = 'in_progress', 'В работе'
        RESOLVED = 'resolved', 'Решён'
        ARCHIVED = 'archived', 'Архив'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Компания'
    )

    # Источник
    source = models.CharField(
        'Источник',
        max_length=20,
        choices=Source.choices,
        default=Source.INTERNAL
    )
    external_id = models.CharField('ID на платформе', max_length=100, blank=True)
    external_url = models.URLField('Ссылка на отзыв', max_length=500, blank=True)

    # Привязка (для internal)
    spot = models.ForeignKey(
        'companies.Spot',
        on_delete=models.SET_NULL,
        related_name='reviews',
        verbose_name='Точка',
        blank=True,
        null=True
    )
    qr = models.ForeignKey(
        'qr.QR',
        on_delete=models.SET_NULL,
        related_name='reviews',
        verbose_name='QR-код',
        blank=True,
        null=True
    )

    # Автор
    author_name = models.CharField('Имя автора', max_length=100, blank=True, default='Аноним')
    author_contact = models.CharField('Контакт', max_length=200, blank=True)
    wants_contact = models.BooleanField(
        'Просит связаться',
        default=False,
        help_text='Клиент отметил галочку "Свяжитесь со мной"'
    )

    # Контент
    rating = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField('Текст', blank=True)
    photo = models.ImageField(
        'Фото',
        upload_to='reviews/%Y/%m/',
        blank=True,
        null=True
    )

    # Детальные оценки (для internal): {"food": 1, "service": 0, "atmosphere": 1}
    # 1 = like, 0 = dislike, null = не оценено
    ratings = models.JSONField('Детальные оценки', default=dict, blank=True)

    # AI-анализ
    sentiment = models.CharField(
        'Тональность',
        max_length=20,
        choices=Sentiment.choices,
        blank=True
    )
    sentiment_score = models.DecimalField(
        'Оценка тональности',
        max_digits=3,
        decimal_places=2,
        blank=True,
        null=True,
        help_text='-1.00 (негатив) до +1.00 (позитив)'
    )
    tags = models.JSONField('Теги', default=list, blank=True)

    # Статус и модерация
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.NEW
    )
    is_public = models.BooleanField('Публичный', default=True)

    # Ответ
    response = models.TextField('Ответ', blank=True)
    response_at = models.DateTimeField('Время ответа', blank=True, null=True)
    response_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        related_name='responses',
        verbose_name='Ответил',
        blank=True,
        null=True
    )

    # Даты
    created_at = models.DateTimeField('Создан', auto_now_add=True, db_index=True)
    platform_date = models.DateTimeField('Дата на платформе', blank=True, null=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),  # Список отзывов компании
            models.Index(fields=['company', 'source']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'rating']),
            models.Index(fields=['company', 'sentiment']),  # Фильтр по тональности
            models.Index(fields=['status', '-created_at']),  # Новые для обработки
        ]

    def __str__(self):
        return f'{self.get_source_display()} ★{self.rating} — {self.author_name}'

    def save(self, *args, **kwargs):
        # Автоматически скрываем негативные внутренние отзывы
        if self.source == self.Source.INTERNAL and self.rating <= 3:
            self.is_public = False

        # Автоматически определяем sentiment по рейтингу, если не задан
        if not self.sentiment:
            if self.rating >= 4:
                self.sentiment = self.Sentiment.POSITIVE
            elif self.rating <= 2:
                self.sentiment = self.Sentiment.NEGATIVE
            else:
                self.sentiment = self.Sentiment.NEUTRAL

        super().save(*args, **kwargs)

    @property
    def is_negative(self):
        return self.rating <= 3 or self.sentiment == self.Sentiment.NEGATIVE

    @property
    def needs_attention(self):
        """Требует внимания: негативный и без ответа"""
        return self.is_negative and not self.response and self.status == self.Status.NEW

    @property
    def photos_count(self):
        """Количество прикреплённых фото"""
        count = self.photos.count()
        # Учитываем старое поле photo для обратной совместимости
        if self.photo:
            count += 1
        return count


class ReviewPhoto(models.Model):
    """Фото к отзыву (до 5 штук)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name='Отзыв'
    )
    image = models.ImageField(
        'Фото',
        upload_to='reviews/%Y/%m/'
    )
    created_at = models.DateTimeField('Загружено', auto_now_add=True)

    class Meta:
        verbose_name = 'Фото отзыва'
        verbose_name_plural = 'Фото отзывов'
        ordering = ['created_at']

    def __str__(self):
        return f'Фото к отзыву {self.review_id}'


class ReviewHistory(models.Model):
    """История действий с отзывом"""

    class Action(models.TextChoices):
        CREATED = 'created', 'Отзыв получен'
        RESPONSE_SENT = 'response_sent', 'Ответ отправлен'
        STATUS_CHANGED = 'status_changed', 'Статус изменён'
        ASSIGNED = 'assigned', 'Назначен ответственный'
        NOTE_ADDED = 'note_added', 'Добавлена заметка'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Отзыв'
    )
    action = models.CharField(
        'Действие',
        max_length=20,
        choices=Action.choices
    )
    description = models.TextField('Описание', blank=True)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Пользователь'
    )
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        verbose_name = 'История отзыва'
        verbose_name_plural = 'История отзывов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_action_display()} — {self.created_at}'

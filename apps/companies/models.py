import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from unidecode import unidecode


ANALYSIS_MODE_CHOICES = [
    ('basic', 'Базовый (паттерны)'),
    ('ai', 'AI-анализ (DeepSeek)'),
]


class Company(models.Model):
    """Компания (заведение)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('Название', max_length=200)
    slug = models.SlugField('URL', max_length=100, unique=True)
    address = models.CharField('Адрес', max_length=500, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    description = models.TextField('Описание', blank=True)

    logo = models.ImageField('Логотип', upload_to='logos/', blank=True, null=True)
    cover = models.ImageField('Обложка', upload_to='covers/', blank=True, null=True)

    # Настройки формы отзыва
    settings = models.JSONField('Настройки', default=dict, blank=True)

    # Для будущего: сеть заведений
    is_chain = models.BooleanField('Это сеть', default=False)

    # Демо-компания для новых пользователей
    is_demo = models.BooleanField(
        'Демо-компания',
        default=False,
        help_text='Демо-компания с примерами отзывов, доступная всем новым пользователям только для просмотра'
    )

    analysis_mode = models.CharField(
        'Режим анализа',
        max_length=10,
        choices=ANALYSIS_MODE_CHOICES,
        default='basic',
        help_text='basic — бесплатные паттерны, ai — DeepSeek + 8 подкатегорий',
    )

    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлена', auto_now=True)

    class Meta:
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    def generate_slug(self) -> str:
        """Генерирует slug из названия, города и улицы."""
        import re
        parts = []

        # Название компании
        if self.name:
            parts.append(slugify(unidecode(self.name))[:40])

        # Город из поля city или парсим из адреса
        city = self.city
        if not city and self.address:
            # Пробуем извлечь город из адреса (первая часть до запятой часто город)
            addr_parts = [p.strip() for p in self.address.split(',')]
            if addr_parts:
                first = addr_parts[0]
                # Если начинается с "г." или не содержит "ул." - это город
                if first.startswith('г.') or first.startswith('г '):
                    city = re.sub(r'^г\.?\s*', '', first)
                elif not re.search(r'(ул\.|улица|пр\.|проспект|пер\.|ш\.|шоссе)', first, re.I):
                    city = first

        if city:
            parts.append(slugify(unidecode(city))[:25])

        # Улица из адреса
        if self.address:
            # Ищем часть с улицей
            street = None
            for part in self.address.split(','):
                part = part.strip()
                if re.search(r'(ул\.|улица|пр\.|проспект|пер\.|переулок|б-р|бульвар|наб\.|набережная|ш\.|шоссе)', part, re.I):
                    # Убираем префикс и номер дома
                    street = re.sub(r'^(ул\.?|улица|пр\.?|проспект|пер\.?|переулок|б-р|бульвар|наб\.?|набережная|ш\.?|шоссе)\s*', '', part, flags=re.I)
                    street = re.sub(r'\s*[,.]?\s*д\.?\s*\d+.*$', '', street)  # убираем "д. 123"
                    street = street.strip()
                    break
            if street:
                parts.append(slugify(unidecode(street))[:25])

        base_slug = '-'.join(parts) if parts else 'company'

        # Проверяем уникальность
        slug = base_slug[:95]
        counter = 1
        while Company.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base_slug[:90]}-{counter}'
            counter += 1
        return slug

    def update_slug_from_address(self):
        """Обновляет slug на основе текущих данных."""
        self.slug = self.generate_slug()
        self.save(update_fields=['slug'])

    def get_feedback_url(self):
        """URL для формы отзыва"""
        return f'/f/{self.slug}/'

    def get_feedback_settings(self):
        """Настройки формы обратной связи с дефолтами"""
        defaults = {
            'title': 'Как вам у нас?',
            'subtitle': '',
            'bg_color': '#f8f9fa',
            'positive_title': 'Рады, что вам понравилось!',
            'positive_subtitle': 'Поделитесь впечатлениями — это поможет другим гостям найти нас',
            'negative_title': 'Нам очень жаль',
            'negative_subtitle': 'Расскажите, что пошло не так — мы обязательно разберёмся',
            'thank_you_title': 'Спасибо за отзыв!',
            'thank_you_subtitle': 'Ваше мнение помогает нам становиться лучше',
            'show_internal_form': True,  # Показывать кнопку "Оставить отзыв напрямую нам"
        }
        settings = self.settings.get('feedback', {}) if self.settings else {}
        return {**defaults, **settings}

    def get_telegram_settings(self):
        """Настройки Telegram уведомлений"""
        defaults = {
            'enabled': False,
            'bot_token': '',
            'chat_id': '',
            'notify_negative': True,  # Уведомлять о негативных отзывах
            'notify_all': False,  # Уведомлять о всех отзывах
        }
        settings = self.settings.get('telegram', {}) if self.settings else {}
        return {**defaults, **settings}

    def set_telegram_settings(self, bot_token: str, chat_id: str, enabled: bool = True):
        """Установить настройки Telegram"""
        if not self.settings:
            self.settings = {}
        self.settings['telegram'] = {
            'enabled': enabled,
            'bot_token': bot_token,
            'chat_id': chat_id,
            'notify_negative': True,
            'notify_all': False,
        }
        self.save(update_fields=['settings'])


class Spot(models.Model):
    """Точка размещения QR-кода (стол, стойка и т.д.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='spots',
        verbose_name='Компания'
    )
    name = models.CharField('Название', max_length=50)  # "Стол 5"
    zone = models.CharField('Зона', max_length=100, blank=True)  # "Терраса"
    description = models.TextField('Описание', blank=True)

    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Точка'
        verbose_name_plural = 'Точки'
        ordering = ['company', 'name']

    def __str__(self):
        if self.zone:
            return f'{self.name} ({self.zone})'
        return self.name


class Platform(models.Model):
    """Внешняя платформа (Яндекс, 2GIS, Google)"""

    id = models.CharField('ID', max_length=20, primary_key=True)  # 'yandex', '2gis'
    name = models.CharField('Название', max_length=50)
    icon = models.CharField('Иконка', max_length=50, blank=True)
    is_active = models.BooleanField('Активна', default=True)

    class Meta:
        verbose_name = 'Платформа'
        verbose_name_plural = 'Платформы'

    def __str__(self):
        return self.name


class Connection(models.Model):
    """Привязка компании к внешней платформе"""

    class SyncStatus(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        SUCCESS = 'success', 'Успешно'
        ERROR = 'error', 'Ошибка'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='connections',
        verbose_name='Компания'
    )
    platform = models.ForeignKey(
        Platform,
        on_delete=models.CASCADE,
        related_name='connections',
        verbose_name='Платформа'
    )
    external_id = models.CharField('ID на платформе', max_length=100)
    external_url = models.URLField('Ссылка на профиль', max_length=500, blank=True)

    # OAuth2 tokens (for Google Business Profile API)
    access_token = models.TextField('Access Token', blank=True)
    refresh_token = models.TextField('Refresh Token', blank=True)
    token_expires_at = models.DateTimeField('Token Expires', blank=True, null=True)

    # Google-specific identifiers
    google_account_id = models.CharField(
        'Google Account ID',
        max_length=50,
        blank=True,
        help_text='accounts/{accountId}'
    )
    google_location_id = models.CharField(
        'Google Location ID',
        max_length=50,
        blank=True,
        help_text='locations/{locationId}'
    )

    # Sync settings
    sync_enabled = models.BooleanField('Синхронизация включена', default=True)
    sync_frequency = models.PositiveIntegerField(
        'Частота синхронизации (сек)',
        default=3600,
        help_text='По умолчанию: 1 час'
    )
    last_sync = models.DateTimeField('Последняя синхронизация', blank=True, null=True)
    last_sync_status = models.CharField(
        'Статус синхронизации',
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING
    )
    last_sync_error = models.TextField('Ошибка синхронизации', blank=True)

    # Platform public rating (e.g. Yandex 4.9)
    platform_rating = models.DecimalField(
        'Рейтинг на платформе', max_digits=2, decimal_places=1,
        null=True, blank=True,
    )
    platform_review_count = models.PositiveIntegerField(
        'Кол-во отзывов на платформе', null=True, blank=True,
    )

    created_at = models.DateTimeField('Создано', default=timezone.now)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Подключение'
        verbose_name_plural = 'Подключения'
        unique_together = ['company', 'platform']

    def __str__(self):
        return f'{self.company.name} @ {self.platform.name}'

    @property
    def is_google(self) -> bool:
        """Check if this is a Google connection"""
        return self.platform_id == 'google'

    @property
    def is_token_valid(self) -> bool:
        """Check if OAuth token is still valid"""
        from django.utils import timezone
        if not self.access_token or not self.token_expires_at:
            return False
        return self.token_expires_at > timezone.now()

    @property
    def google_resource_name(self) -> str:
        """Full Google API resource name for this location"""
        if self.google_account_id and self.google_location_id:
            return f'{self.google_account_id}/{self.google_location_id}'
        return ''

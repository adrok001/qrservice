import uuid
import secrets
import string
from django.db import models


def generate_short_code():
    """Генерация уникального 8-символьного кода"""
    alphabet = string.ascii_uppercase + string.digits
    # Убираем похожие символы: 0, O, I, L
    alphabet = alphabet.replace('0', '').replace('O', '').replace('I', '').replace('L', '')
    return ''.join(secrets.choice(alphabet) for _ in range(8))


class QR(models.Model):
    """QR-код со статичной ссылкой и динамическим редиректом"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        'Код',
        max_length=8,
        unique=True,
        default=generate_short_code,
        help_text='Уникальный код для URL (например: ABC12345)'
    )

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='qr_codes',
        verbose_name='Компания'
    )
    spot = models.ForeignKey(
        'companies.Spot',
        on_delete=models.SET_NULL,
        related_name='qr_codes',
        verbose_name='Точка',
        blank=True,
        null=True
    )

    # Кастомизация
    color = models.CharField('Цвет', max_length=7, default='#000000')
    background = models.CharField('Фон', max_length=7, default='#FFFFFF')
    logo = models.ImageField('Логотип', upload_to='qr_logos/', blank=True, null=True)
    image = models.ImageField('Изображение QR', upload_to='qrcodes/', blank=True, null=True)

    # Статистика
    scans = models.PositiveIntegerField('Сканирований', default=0)
    last_scan_at = models.DateTimeField('Последнее сканирование', blank=True, null=True)

    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        verbose_name='Создал',
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = 'QR-код'
        verbose_name_plural = 'QR-коды'
        ordering = ['-created_at']

    def __str__(self):
        spot_info = f' ({self.spot.name})' if self.spot else ''
        return f'QR-{self.code}{spot_info}'

    def get_absolute_url(self):
        """Полный URL QR-кода"""
        return f'/{self.code}'

    def get_redirect_url(self):
        """URL для редиректа (форма отзыва)"""
        base_url = f'/f/{self.company.slug}/'
        if self.spot:
            return f'{base_url}?spot={self.spot.id}&qr={self.code}'
        return f'{base_url}?qr={self.code}'

    def increment_scans(self):
        """Увеличить счётчик сканирований"""
        from django.utils import timezone
        self.scans += 1
        self.last_scan_at = timezone.now()
        self.save(update_fields=['scans', 'last_scan_at'])


class QRScan(models.Model):
    """Лог сканирования QR-кода"""

    id = models.BigAutoField(primary_key=True)
    qr = models.ForeignKey(
        QR,
        on_delete=models.CASCADE,
        related_name='scan_logs',
        verbose_name='QR-код'
    )
    scanned_at = models.DateTimeField('Время', auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField('IP', blank=True, null=True)
    user_agent = models.CharField('User Agent', max_length=500, blank=True)
    session_id = models.CharField('ID сессии', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Сканирование'
        verbose_name_plural = 'Сканирования'
        ordering = ['-scanned_at']

    def __str__(self):
        return f'{self.qr.code} @ {self.scanned_at}'

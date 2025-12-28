import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """Менеджер кастомной модели User"""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Кастомная модель пользователя с email вместо username"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField('Email', unique=True)
    first_name = models.CharField('Имя', max_length=100, blank=True)
    last_name = models.CharField('Фамилия', max_length=100, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    avatar = models.ImageField('Аватар', upload_to='avatars/', blank=True, null=True)
    telegram_id = models.BigIntegerField('Telegram ID', blank=True, null=True)

    is_active = models.BooleanField('Активен', default=True)
    is_staff = models.BooleanField('Сотрудник', default=False)

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email


class Member(models.Model):
    """Связь пользователя с компанией + роль"""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Владелец'
        MANAGER = 'manager', 'Менеджер'
        VIEWER = 'viewer', 'Наблюдатель'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Пользователь'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='members',
        verbose_name='Компания'
    )
    role = models.CharField(
        'Роль',
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER
    )
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        verbose_name = 'Членство'
        verbose_name_plural = 'Членства'
        unique_together = ['user', 'company']

    def __str__(self):
        return f'{self.user.email} @ {self.company.name} ({self.role})'

    def can_respond(self) -> bool:
        """Может ли отвечать на отзывы"""
        return self.role in [self.Role.OWNER, self.Role.MANAGER]

    def can_manage(self) -> bool:
        """Может ли управлять настройками"""
        return self.role == self.Role.OWNER

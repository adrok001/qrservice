"""URL configuration for qrservice project."""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

from apps.reviews.api import respond_to_review

urlpatterns = [
    # Главная -> Dashboard
    path('', RedirectView.as_view(url='/dashboard/', permanent=False), name='home'),

    # Админка Django
    path('admin/', admin.site.urls),

    # Авторизация
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),

    # API
    path('api/reviews/<uuid:review_id>/respond/', respond_to_review, name='api_respond'),

    # Форма отзыва (гостевой интерфейс)
    path('f/', include('apps.reviews.urls', namespace='feedback')),

    # Дашборд (авторизованный интерфейс)
    path('dashboard/', include('apps.dashboard.urls', namespace='dashboard')),

    # Интеграции
    path('integrations/', include('apps.integrations.urls', namespace='integrations')),

    # Старое приложение (для совместимости)
    path('old/', include('qrcode_app.urls')),

    # QR-редирект должен быть в конце (ловит /{CODE})
    path('', include('apps.qr.urls', namespace='qr')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)

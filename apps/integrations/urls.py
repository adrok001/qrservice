"""URL configuration for integrations app."""

from django.urls import path

from . import views

app_name = 'integrations'

urlpatterns = [
    # Settings page
    path('', views.integrations_settings, name='settings'),

    # Google OAuth flow
    path('google/connect/', views.google_connect, name='google_connect'),
    path('google/callback/', views.google_callback, name='google_callback'),
    path(
        'google/<uuid:connection_id>/location/',
        views.google_select_location,
        name='google_select_location'
    ),
    path(
        'google/<uuid:connection_id>/disconnect/',
        views.google_disconnect,
        name='google_disconnect'
    ),
    path(
        'google/<uuid:connection_id>/sync/',
        views.google_sync_now,
        name='google_sync_now'
    ),

    # Telegram notifications (legacy - company level)
    path('telegram/save/', views.telegram_save, name='telegram_save'),
    path('telegram/test/', views.telegram_test, name='telegram_test'),

    # Telegram user-level connection
    path('telegram/connect/', views.telegram_connect, name='telegram_connect'),
    path('telegram/disconnect/', views.telegram_disconnect, name='telegram_disconnect'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
]

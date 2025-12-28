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
]

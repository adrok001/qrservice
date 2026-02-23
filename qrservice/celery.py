"""Celery configuration for qrservice project."""

import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qrservice.settings')

# Create Celery app
app = Celery('qrservice')

# Load config from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all registered Django apps
app.autodiscover_tasks()

# Periodic tasks (Celery Beat)
app.conf.beat_schedule = {
    'sync-google-reviews-hourly': {
        'task': 'apps.integrations.tasks.sync_all_google_reviews',
        'schedule': crontab(minute=0),  # Every hour
    },
    'sync-yandex-reviews-every-3h': {
        'task': 'apps.integrations.tasks.sync_all_yandex_reviews',
        'schedule': crontab(minute=0, hour='0,9,12,15,18,21'),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f'Request: {self.request!r}')

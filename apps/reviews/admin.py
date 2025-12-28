from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'company', 'source', 'rating', 'sentiment', 'status', 'is_public', 'created_at')
    list_filter = ('source', 'status', 'sentiment', 'is_public', 'rating', 'company')
    search_fields = ('text', 'author_name', 'author_contact', 'company__name')
    readonly_fields = ('created_at', 'updated_at', 'response_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основное', {
            'fields': ('company', 'source', 'external_id', 'external_url')
        }),
        ('Привязка', {
            'fields': ('spot', 'qr')
        }),
        ('Автор', {
            'fields': ('author_name', 'author_contact')
        }),
        ('Контент', {
            'fields': ('rating', 'text', 'ratings')
        }),
        ('AI-анализ', {
            'fields': ('sentiment', 'sentiment_score', 'tags')
        }),
        ('Статус', {
            'fields': ('status', 'is_public')
        }),
        ('Ответ', {
            'fields': ('response', 'response_by', 'response_at')
        }),
        ('Даты', {
            'fields': ('created_at', 'platform_date', 'updated_at')
        }),
    )

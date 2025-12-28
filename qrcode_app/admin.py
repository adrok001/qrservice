from django.contrib import admin
from .models import QRCode


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ['id', 'data', 'created_at']
    list_filter = ['created_at']
    search_fields = ['data']
    readonly_fields = ['created_at']

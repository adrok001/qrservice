from django.contrib import admin
from .models import QR, QRScan


@admin.register(QR)
class QRAdmin(admin.ModelAdmin):
    list_display = ('code', 'company', 'spot', 'scans', 'is_active', 'created_at')
    list_filter = ('is_active', 'company')
    search_fields = ('code', 'company__name', 'spot__name')
    readonly_fields = ('code', 'scans', 'last_scan_at', 'created_at')


@admin.register(QRScan)
class QRScanAdmin(admin.ModelAdmin):
    list_display = ('qr', 'scanned_at', 'ip_address')
    list_filter = ('qr__company',)
    date_hierarchy = 'scanned_at'

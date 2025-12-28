from django.contrib import admin
from .models import Company, Spot, Platform, Connection


class SpotInline(admin.TabularInline):
    model = Spot
    extra = 1


class ConnectionInline(admin.TabularInline):
    model = Connection
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'is_active', 'created_at')
    list_filter = ('is_active', 'city', 'is_chain')
    search_fields = ('name', 'address', 'city')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SpotInline, ConnectionInline]


@admin.register(Spot)
class SpotAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'zone', 'is_active')
    list_filter = ('is_active', 'company')
    search_fields = ('name', 'company__name')


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active')


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ('company', 'platform', 'sync_enabled', 'last_sync')
    list_filter = ('platform', 'sync_enabled')

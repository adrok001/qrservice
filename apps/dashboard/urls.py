from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_index, name='index'),
    path('reviews/', views.reviews_list, name='reviews'),
    path('qr/', views.qr_list, name='qr'),
    path('qr/create/', views.qr_create, name='qr_create'),
    path('qr/<uuid:qr_id>/edit/', views.qr_edit, name='qr_edit'),
    path('qr/<uuid:qr_id>/delete/', views.qr_delete, name='qr_delete'),
    path('switch-company/<str:company_id>/', views.switch_company, name='switch_company'),
    path('settings/form/', views.form_settings, name='form_settings'),
    path('settings/company/', views.company_settings, name='company_settings'),
]

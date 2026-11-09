"""Главный файл маршрутов проекта «Конные туры»."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/doc/', include('django.contrib.admindocs.urls')),  # документация (Django docs)
    path('admin/', admin.site.urls),
    path('', include('tours.urls')),
]

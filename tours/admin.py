from django.contrib import admin

from .models import Booking, Category, Comment, Customer, Tour


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'duration_hours', 'is_active')
    list_filter = ('categories', 'is_active')
    filter_horizontal = ('categories',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('customer', 'tour', 'date', 'time')
    list_filter = ('date', 'tour')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'tour', 'rating', 'created_at')

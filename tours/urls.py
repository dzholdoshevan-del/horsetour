from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'tours'

urlpatterns = [
    path('', views.tour_list, name='list'),
    path('tours/<int:pk>/', views.tour_detail, name='detail'),
    path('tours/<int:pk>/book/', views.book_tour, name='book'),
    path('tours/<int:pk>/comment/', views.add_comment, name='comment'),
    path('bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='tours/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

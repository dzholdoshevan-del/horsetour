"""Представления (страницы) приложения «Туры»."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BookingForm, CommentForm, RegisterForm
from .models import Booking, Category, Customer, Tour


def get_customer(request):
    """Возвращает профиль клиента текущего пользователя.

    Если профиля нет (например, у администратора), он создаётся автоматически.
    """
    customer, _ = Customer.objects.get_or_create(user=request.user)
    return customer


def tour_list(request):
    """Каталог туров.

    Показывает все доступные туры. Параметр ``?category=<id>`` оставляет только
    туры выбранной категории; несуществующая категория даёт ошибку 404.
    """
    tours = Tour.objects.filter(is_active=True).prefetch_related('categories')
    current = None
    category_id = request.GET.get('category')
    if category_id:
        if not category_id.isdigit():
            raise Http404('Некорректная категория')
        current = get_object_or_404(Category, pk=category_id)
        tours = tours.filter(categories=current)
    return render(request, 'tours/tour_list.html', {
        'tours': tours,
        'categories': Category.objects.all(),
        'current_category': current,
    })


def tour_detail(request, pk):
    """Страница тура: описание, категории и комментарии.

    Контекст содержит флаг ``can_comment`` — можно ли текущему пользователю
    оставить комментарий (только если он покупал этот тур).
    """
    tour = get_object_or_404(Tour, pk=pk, is_active=True)
    can_comment = False
    if request.user.is_authenticated:
        can_comment = get_customer(request).has_visited(tour)
    return render(request, 'tours/tour_detail.html', {
        'tour': tour,
        'comments': tour.comments.select_related('customer__user'),
        'can_comment': can_comment,
    })


def register(request):
    """Регистрация клиента (отправка данных: имя, пароль, телефон).

    После успешной регистрации создаются пользователь и профиль клиента,
    пользователь сразу входит в систему.
    """
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Регистрация прошла успешно.')
        return redirect('tours:list')
    return render(request, 'tours/register.html', {'form': form})


@login_required
def book_tour(request, pk):
    """Покупка тура на дату и время (отправка данных).

    Один клиент может купить только один тур на определённые день и время.
    При нарушении правила форма показывает ошибку и бронирование не создаётся.
    """
    tour = get_object_or_404(Tour, pk=pk, is_active=True)
    form = BookingForm(request.POST or None, customer=get_customer(request), tour=tour)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Тур куплен.')
        return redirect('tours:my_bookings')
    return render(request, 'tours/booking_form.html', {'form': form, 'tour': tour})


@login_required
def my_bookings(request):
    """Список купленных туров текущего клиента."""
    bookings = get_customer(request).bookings.select_related('tour')
    return render(request, 'tours/my_bookings.html', {'bookings': bookings})


@login_required
@require_POST
def cancel_booking(request, pk):
    """Отмена бронирования (только POST).

    Клиент может отменить только своё бронирование, чужое даёт ошибку 404.
    """
    booking = get_object_or_404(Booking, pk=pk, customer=get_customer(request))
    booking.delete()
    messages.success(request, 'Бронирование отменено.')
    return redirect('tours:my_bookings')


@login_required
def add_comment(request, pk):
    """Добавление комментария к туру (отправка данных: текст и оценка).

    Комментарий принимается только от клиента, который покупал этот тур.
    Количество комментариев одного клиента к туру не ограничено.
    """
    tour = get_object_or_404(Tour, pk=pk, is_active=True)
    form = CommentForm(request.POST or None, customer=get_customer(request), tour=tour)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Комментарий добавлен.')
        return redirect(tour)
    return render(request, 'tours/comment_form.html', {'form': form, 'tour': tour})

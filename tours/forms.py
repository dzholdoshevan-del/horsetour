"""Формы приложения «Туры». Через них проходят все отправки данных."""
from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.utils import timezone

from .models import Booking, Comment, Customer

SLOT_CHOICES = [(f'{hour:02d}:00', f'{hour:02d}:00') for hour in (9, 12, 15, 18)]


class RegisterForm(UserCreationForm):
    """Регистрация: создаёт пользователя и его профиль клиента (1:1)."""

    phone = forms.CharField(label='Телефон', max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username',)

    @transaction.atomic
    def save(self, commit=True):
        """Сохраняет пользователя и создаёт связанный профиль ``Customer``."""
        user = super().save(commit=True)
        Customer.objects.create(user=user, phone=self.cleaned_data.get('phone', ''))
        return user


class BookingForm(forms.ModelForm):
    """Покупка тура: выбор даты и времени.

    Принимает клиента и тур (``customer``, ``tour``). Проверяет, что дата не
    в прошлом, время входит в список слотов и у клиента нет другого тура на
    это же время.
    """

    time = forms.TypedChoiceField(
        label='Время', choices=SLOT_CHOICES,
        coerce=lambda value: datetime.strptime(value, '%H:%M').time())

    class Meta:
        model = Booking
        fields = ['date', 'time']
        labels = {'date': 'Дата'}
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, customer, tour, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.customer = customer
        self.instance.tour = tour

    def clean_date(self):
        """Нельзя купить тур на прошедшую дату."""
        date = self.cleaned_data['date']
        if date < timezone.localdate():
            raise forms.ValidationError('Нельзя купить тур на прошедшую дату.')
        return date


class CommentForm(forms.ModelForm):
    """Комментарий к туру (текст и оценка).

    Принимает клиента и тур. Комментарий разрешён только если клиент
    покупал этот тур (проверка в ``Comment.clean``).
    """

    class Meta:
        model = Comment
        fields = ['text', 'rating']
        labels = {'text': 'Комментарий', 'rating': 'Оценка (1–5)'}

    def __init__(self, *args, customer, tour, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.customer = customer
        self.instance.tour = tour

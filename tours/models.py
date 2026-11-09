"""Модели приложения «Туры».

Связи между моделями:

* **Один к одному (1:1)** — ``Customer`` ↔ ``User`` (у каждого пользователя
  ровно один профиль клиента).
* **Один ко многим (1:M)** — ``Customer`` → ``Booking``,
  ``Tour`` → ``Booking``, ``Customer`` → ``Comment``,
  ``Tour`` → ``Comment``.
* **Многие ко многим (M:M)** — ``Tour`` ↔ ``Category``
  (у тура может быть несколько категорий, в категории — несколько туров).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


class Category(models.Model):
    """Категория тура.

    Примеры: «Конный», «Пеший», «Мото». Связана с турами отношением
    «многие ко многим» (поле ``categories`` у модели ``Tour``).
    """

    name = models.CharField('Название', max_length=50, unique=True,
                            help_text='Уникальное название категории, например «Конный».')

    class Meta:
        ordering = ['name']
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name


class Tour(models.Model):
    """Тур (конный, пеший, мото и т. д.).

    Тур может относиться сразу к нескольким категориям (M:M). На тур
    оформляются бронирования (1:M) и оставляются комментарии (1:M).
    """

    title = models.CharField('Название', max_length=200, help_text='Название тура.')
    description = models.TextField('Описание', blank=True, help_text='Подробное описание маршрута.')
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(0)], help_text='Цена за одного человека.')
    duration_hours = models.PositiveSmallIntegerField('Длительность, ч', default=2,
                                                      help_text='Сколько часов длится тур.')
    categories = models.ManyToManyField(Category, related_name='tours', blank=True,
                                        verbose_name='Категории',
                                        help_text='Связь «многие ко многим»: у тура может быть несколько категорий.')
    is_active = models.BooleanField('Доступен', default=True,
                                    help_text='Скрытые туры не показываются в каталоге.')

    class Meta:
        ordering = ['title']
        verbose_name = 'Тур'
        verbose_name_plural = 'Туры'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('tours:detail', kwargs={'pk': self.pk})


class Customer(models.Model):
    """Клиент — профиль пользователя.

    Связь «один к одному» с встроенной моделью ``User``: у одного пользователя
    только один профиль клиента и наоборот. Профиль создаётся при регистрации.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='customer', verbose_name='Пользователь',
                                help_text='Связь «один к одному» со встроенным пользователем.')
    phone = models.CharField('Телефон', max_length=20, blank=True, help_text='Контактный телефон.')

    class Meta:
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'

    def __str__(self):
        return self.user.get_username()

    def has_visited(self, tour):
        """Был ли клиент на туре.

        Клиент считается побывавшим на туре, если у него есть бронирование
        этого тура. Только такие клиенты могут оставлять комментарии.
        """
        return self.bookings.filter(tour=tour).exists()


class Booking(models.Model):
    """Бронирование (покупка) тура клиентом на дату и время.

    **Правило:** один клиент может купить только один тур на определённые
    день и время. Правило защищено дважды: ограничением уникальности в базе
    данных (``unique_customer_slot``) и проверкой в методе ``clean``.
    """

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='bookings',
                                 verbose_name='Клиент', help_text='Кто купил тур (1:M).')
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='bookings',
                             verbose_name='Тур', help_text='Какой тур куплен (1:M).')
    date = models.DateField('Дата', help_text='День проведения тура.')
    time = models.TimeField('Время', help_text='Время начала тура.')
    created_at = models.DateTimeField('Создано', auto_now_add=True)

    class Meta:
        ordering = ['date', 'time']
        verbose_name = 'Бронирование'
        verbose_name_plural = 'Бронирования'
        constraints = [
            models.UniqueConstraint(fields=['customer', 'date', 'time'], name='unique_customer_slot'),
        ]

    def __str__(self):
        return f'{self.customer} — {self.tour} ({self.date} {self.time:%H:%M})'

    def clean(self):
        """Проверяет, что у клиента нет другого тура на эту дату и время."""
        super().clean()
        if self.customer_id and self.date and self.time:
            clash = Booking.objects.filter(customer_id=self.customer_id, date=self.date, time=self.time)
            if self.pk:
                clash = clash.exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError('У вас уже куплен тур на эту дату и время.')


class Comment(models.Model):
    """Комментарий клиента к туру.

    Один клиент может оставить **несколько** комментариев, но только к турам,
    на которых он был (см. ``Customer.has_visited``).
    """

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='comments',
                                 verbose_name='Автор', help_text='Кто написал комментарий (1:M).')
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name='comments',
                             verbose_name='Тур', help_text='К какому туру комментарий (1:M).')
    text = models.TextField('Текст', help_text='Текст комментария.')
    rating = models.PositiveSmallIntegerField('Оценка', default=5,
                                              validators=[MinValueValidator(1), MaxValueValidator(5)],
                                              help_text='Оценка тура от 1 до 5.')
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'

    def __str__(self):
        return f'{self.customer}: {self.text[:30]}'

    def clean(self):
        """Запрещает комментарий к туру, на котором клиент не был."""
        super().clean()
        if self.customer_id and self.tour_id and not self.customer.has_visited(self.tour):
            raise ValidationError('Комментарий можно оставить только к туру, который вы покупали.')

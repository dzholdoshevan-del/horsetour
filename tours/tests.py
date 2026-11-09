from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import BookingForm, CommentForm, RegisterForm
from .models import Booking, Category, Comment, Customer, Tour

User = get_user_model()
PASSWORD = 'Str0ng-pass-123'
FAST_HASHER = ['django.contrib.auth.hashers.MD5PasswordHasher']


def make_customer(username='ivan', phone=''):
    """Создаёт пользователя вместе с профилем клиента."""
    user = User.objects.create_user(username=username, password=PASSWORD)
    return Customer.objects.create(user=user, phone=phone)


def future(days=3):
    return timezone.localdate() + timedelta(days=days)


def past(days=3):
    return timezone.localdate() - timedelta(days=days)


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class BaseTestCase(TestCase):
    """Общие данные: категории, туры, два клиента."""

    @classmethod
    def setUpTestData(cls):
        cls.horse = Category.objects.create(name='Конный')
        cls.hiking = Category.objects.create(name='Пеший')
        cls.moto = Category.objects.create(name='Мото')

        cls.horse_tour = Tour.objects.create(title='Горы верхом', price=3500)
        cls.horse_tour.categories.add(cls.horse)
        cls.hiking_tour = Tour.objects.create(title='Каньон пешком', price=1200)
        cls.hiking_tour.categories.add(cls.hiking)
        cls.moto_tour = Tour.objects.create(title='Мото вдоль озера', price=6000)
        cls.moto_tour.categories.add(cls.moto)

        cls.ivan = make_customer('ivan')
        cls.olga = make_customer('olga')

    def login(self, customer):
        self.assertTrue(self.client.login(username=customer.user.username, password=PASSWORD))

    @staticmethod
    def book(customer, tour, date=None, at=time(9, 0)):
        return Booking.objects.create(customer=customer, tour=tour, date=date or future(), time=at)


# =====================================================================
# 1. СВЯЗИ МЕЖДУ МОДЕЛЯМИ
# =====================================================================
class RelationsTests(BaseTestCase):
    """Связи 1:1, 1:M, M:M"""

    # 1:1 — у клиента есть пользователь, а у пользователя есть клиент
    def test_one_to_one_both_directions(self):
        self.assertEqual(self.ivan.user.customer, self.ivan)
        self.assertEqual(self.ivan.user.username, 'ivan')

    # 1:1 — второй профиль для того же пользователя создать нельзя
    def test_one_to_one_second_profile_not_allowed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(user=self.ivan.user)

    # 1:1 — при удалении пользователя профиль клиента удаляется
    def test_one_to_one_delete_user_deletes_customer(self):
        pk = self.ivan.pk
        self.ivan.user.delete()
        self.assertFalse(Customer.objects.filter(pk=pk).exists())

    # 1:M — у тура много бронирований
    def test_one_to_many_tour_has_many_bookings(self):
        self.book(self.ivan, self.horse_tour)
        self.book(self.olga, self.horse_tour)
        self.assertEqual(self.horse_tour.bookings.count(), 2)

    # 1:M — у клиента много бронирований
    def test_one_to_many_customer_has_many_bookings(self):
        self.book(self.ivan, self.horse_tour, at=time(9, 0))
        self.book(self.ivan, self.moto_tour, at=time(12, 0))
        self.assertEqual(self.ivan.bookings.count(), 2)

    # 1:M — у тура много комментариев, у клиента тоже
    def test_one_to_many_comments(self):
        Comment.objects.create(customer=self.ivan, tour=self.horse_tour, text='a')
        Comment.objects.create(customer=self.olga, tour=self.horse_tour, text='b')
        self.assertEqual(self.horse_tour.comments.count(), 2)
        self.assertEqual(self.ivan.comments.count(), 1)

    # 1:M — при удалении тура удаляются его бронирования и комментарии
    def test_delete_tour_cascades(self):
        self.book(self.ivan, self.horse_tour)
        Comment.objects.create(customer=self.ivan, tour=self.horse_tour, text='a')
        self.horse_tour.delete()
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Comment.objects.count(), 0)

    # M:M — у тура может быть несколько категорий, у категории несколько туров
    def test_many_to_many_both_directions(self):
        self.horse_tour.categories.add(self.hiking)
        self.assertEqual(set(self.horse_tour.categories.all()), {self.horse, self.hiking})
        self.assertEqual(set(self.hiking.tours.all()), {self.horse_tour, self.hiking_tour})

    # M:M — одну и ту же категорию нельзя добавить туру дважды
    def test_many_to_many_no_duplicates(self):
        self.horse_tour.categories.add(self.horse)
        self.assertEqual(self.horse_tour.categories.count(), 1)

    # M:M — тур может быть без категорий
    def test_tour_without_categories(self):
        tour = Tour.objects.create(title='Без категории', price=1)
        self.assertEqual(tour.categories.count(), 0)

    # Название категории уникально
    def test_category_name_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.create(name='Конный')

    # Строковые представления моделей
    def test_str_methods(self):
        self.assertEqual(str(self.horse), 'Конный')
        self.assertEqual(str(self.horse_tour), 'Горы верхом')
        self.assertEqual(str(self.ivan), 'ivan')
        booking = self.book(self.ivan, self.horse_tour)
        self.assertIn('ivan', str(booking))
        comment = Comment.objects.create(customer=self.ivan, tour=self.horse_tour, text='Отлично')
        self.assertIn('Отлично', str(comment))


# =====================================================================
# 2. ПРАВИЛО: 1 ЧЕЛОВЕК — 1 ТУР НА ДЕНЬ И ВРЕМЯ
# =====================================================================
class BookingRuleModelTests(BaseTestCase):
    """Правило слота на уровне модели и базы данных"""

    # База не даёт создать второе бронирование клиента на ту же дату и время
    def test_db_blocks_same_customer_same_slot(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.book(self.ivan, self.horse_tour, future(), time(9, 0))

    # Даже другой тур на тот же слот база не разрешает
    def test_db_blocks_same_slot_other_tour(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.book(self.ivan, self.moto_tour, future(), time(9, 0))

    # Другое время в тот же день разрешено
    def test_same_day_different_time_allowed(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        self.book(self.ivan, self.moto_tour, future(), time(12, 0))
        self.assertEqual(self.ivan.bookings.count(), 2)

    # То же время в другой день разрешено
    def test_same_time_different_day_allowed(self):
        self.book(self.ivan, self.horse_tour, future(3), time(9, 0))
        self.book(self.ivan, self.horse_tour, future(4), time(9, 0))
        self.assertEqual(self.ivan.bookings.count(), 2)

    # Разные клиенты могут занять один и тот же слот
    def test_different_customers_same_slot_allowed(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        self.book(self.olga, self.horse_tour, future(), time(9, 0))
        self.assertEqual(Booking.objects.count(), 2)

    # Метод clean() модели находит дубликат (используется в админке и формах)
    def test_model_clean_detects_duplicate(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        duplicate = Booking(customer=self.ivan, tour=self.moto_tour, date=future(), time=time(9, 0))
        with self.assertRaises(ValidationError):
            duplicate.full_clean(exclude=['created_at'])

    # clean() не считает дубликатом саму запись при её редактировании
    def test_model_clean_ignores_itself(self):
        booking = self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        booking.full_clean(exclude=['created_at'])


class BookingFormTests(BaseTestCase):
    """Правило слота и проверки на уровне формы"""

    def form(self, data, customer=None, tour=None):
        return BookingForm(data, customer=customer or self.ivan, tour=tour or self.horse_tour)

    # Корректные данные проходят
    def test_valid(self):
        self.assertTrue(self.form({'date': future(), 'time': '09:00'}).is_valid())

    # Второй тур на тот же слот отклоняется с понятной ошибкой
    def test_second_booking_same_slot_invalid(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        form = self.form({'date': future(), 'time': '09:00'}, tour=self.moto_tour)
        self.assertFalse(form.is_valid())
        self.assertIn('У вас уже куплен тур', form.non_field_errors()[0])

    # Другой клиент с теми же данными проходит
    def test_other_customer_same_slot_valid(self):
        self.book(self.ivan, self.horse_tour, future(), time(9, 0))
        self.assertTrue(self.form({'date': future(), 'time': '09:00'}, customer=self.olga).is_valid())

    # Прошедшая дата отклоняется
    def test_past_date_invalid(self):
        form = self.form({'date': past(), 'time': '09:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)

    # Сегодняшняя дата допустима
    def test_today_valid(self):
        self.assertTrue(self.form({'date': timezone.localdate(), 'time': '09:00'}).is_valid())

    # Время вне списка слотов отклоняется
    def test_time_not_in_slots_invalid(self):
        form = self.form({'date': future(), 'time': '10:30'})
        self.assertFalse(form.is_valid())
        self.assertIn('time', form.errors)

    # Дата и время обязательны
    def test_required_fields(self):
        form = self.form({})
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)
        self.assertIn('time', form.errors)

    # Неверный формат даты отклоняется
    def test_bad_date_format_invalid(self):
        self.assertFalse(self.form({'date': 'завтра', 'time': '09:00'}).is_valid())


class BookingRuleViewTests(BaseTestCase):
    """Правило слота через отправку формы на сайте"""

    def post_book(self, tour, date=None, at='09:00'):
        return self.client.post(reverse('tours:book', args=[tour.pk]),
                                {'date': date or future(), 'time': at})

    # Покупка создаёт бронирование и ведёт на «Мои туры»
    def test_book_creates_booking(self):
        self.login(self.ivan)
        response = self.post_book(self.horse_tour)
        self.assertRedirects(response, reverse('tours:my_bookings'))
        booking = Booking.objects.get()
        self.assertEqual((booking.customer, booking.tour, booking.time), (self.ivan, self.horse_tour, time(9, 0)))

    # Повторная покупка на тот же слот не создаётся, показывается ошибка
    def test_double_booking_not_created(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour)
        response = self.post_book(self.horse_tour)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'У вас уже куплен тур')
        self.assertEqual(Booking.objects.count(), 1)

    # Другой тур на тот же слот тоже не создаётся
    def test_other_tour_same_slot_blocked(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour)
        response = self.post_book(self.moto_tour)
        self.assertContains(response, 'У вас уже куплен тур')
        self.assertEqual(Booking.objects.count(), 1)

    # В тот же день на другое время купить можно
    def test_two_slots_same_day(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour, at='09:00')
        self.post_book(self.moto_tour, at='12:00')
        self.assertEqual(Booking.objects.count(), 2)

    # Другой клиент может купить тот же слот
    def test_other_customer_can_take_same_slot(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour)
        self.client.logout()
        self.login(self.olga)
        self.post_book(self.horse_tour)
        self.assertEqual(Booking.objects.count(), 2)

    # После отмены слот снова можно купить
    def test_cancel_then_rebook(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour)
        booking = Booking.objects.get()
        self.client.post(reverse('tours:cancel_booking', args=[booking.pk]))
        self.assertEqual(Booking.objects.count(), 0)
        self.post_book(self.horse_tour)
        self.assertEqual(Booking.objects.count(), 1)

    # Прошедшая дата, неверное время и пустая форма не создают бронирование
    def test_invalid_data_creates_nothing(self):
        self.login(self.ivan)
        self.post_book(self.horse_tour, date=past())
        self.post_book(self.horse_tour, at='10:30')
        self.client.post(reverse('tours:book', args=[self.horse_tour.pk]), {})
        self.assertEqual(Booking.objects.count(), 0)


# =====================================================================
# 3. ПРАВИЛО: НЕСКОЛЬКО КОММЕНТАРИЕВ К ТУРАМ, В КОТОРЫХ БЫЛ
# =====================================================================
class CommentRuleTests(BaseTestCase):
    """Комментарии клиента"""

    def post_comment(self, tour, text='Отличный тур', rating=5):
        return self.client.post(reverse('tours:comment', args=[tour.pk]), {'text': text, 'rating': rating})

    # После покупки тура можно оставить комментарий
    def test_comment_after_booking(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        response = self.post_comment(self.horse_tour)
        self.assertRedirects(response, self.horse_tour.get_absolute_url())
        comment = Comment.objects.get()
        self.assertEqual((comment.customer, comment.tour, comment.rating), (self.ivan, self.horse_tour, 5))

    # Один клиент может оставить несколько комментариев к одному туру
    def test_multiple_comments_same_tour(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        for i in range(3):
            self.post_comment(self.horse_tour, text=f'Комментарий {i}')
        self.assertEqual(Comment.objects.filter(customer=self.ivan, tour=self.horse_tour).count(), 3)

    # Можно комментировать несколько разных туров, в которых был
    def test_comments_on_several_booked_tours(self):
        self.book(self.ivan, self.horse_tour, at=time(9, 0))
        self.book(self.ivan, self.moto_tour, at=time(12, 0))
        self.login(self.ivan)
        self.post_comment(self.horse_tour)
        self.post_comment(self.moto_tour)
        self.assertEqual(self.ivan.comments.count(), 2)
        self.assertEqual({c.tour for c in self.ivan.comments.all()}, {self.horse_tour, self.moto_tour})

    # Нельзя комментировать тур, который не покупал
    def test_cannot_comment_without_booking(self):
        self.login(self.ivan)
        response = self.post_comment(self.horse_tour)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'только к туру, который вы покупали')
        self.assertEqual(Comment.objects.count(), 0)

    # Нельзя комментировать тур, на который записан только другой клиент
    def test_cannot_comment_tour_booked_by_other(self):
        self.book(self.olga, self.horse_tour)
        self.login(self.ivan)
        self.post_comment(self.horse_tour)
        self.assertEqual(Comment.objects.count(), 0)

    # Если был на одном туре, на другой комментарий всё равно нельзя
    def test_cannot_comment_other_tour(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        self.post_comment(self.moto_tour)
        self.assertEqual(Comment.objects.count(), 0)

    # Форма: пустой текст недопустим
    def test_form_empty_text_invalid(self):
        self.book(self.ivan, self.horse_tour)
        form = CommentForm({'text': '', 'rating': 5}, customer=self.ivan, tour=self.horse_tour)
        self.assertFalse(form.is_valid())
        self.assertIn('text', form.errors)

    # Форма: оценка должна быть от 1 до 5
    def test_form_rating_out_of_range(self):
        self.book(self.ivan, self.horse_tour)
        for bad in (0, 6, -1, 100):
            form = CommentForm({'text': 'x', 'rating': bad}, customer=self.ivan, tour=self.horse_tour)
            self.assertFalse(form.is_valid(), bad)
            self.assertIn('rating', form.errors)
        for good in (1, 3, 5):
            form = CommentForm({'text': 'x', 'rating': good}, customer=self.ivan, tour=self.horse_tour)
            self.assertTrue(form.is_valid(), good)

    # Форма: оценка не число
    def test_form_rating_not_a_number(self):
        self.book(self.ivan, self.horse_tour)
        form = CommentForm({'text': 'x', 'rating': 'отлично'}, customer=self.ivan, tour=self.horse_tour)
        self.assertFalse(form.is_valid())

    # Автор комментария — текущий клиент
    def test_comment_author_is_current_customer(self):
        self.book(self.ivan, self.horse_tour)
        self.book(self.olga, self.horse_tour)
        self.login(self.olga)
        self.post_comment(self.horse_tour)
        self.assertEqual(Comment.objects.get().customer, self.olga)

    # Комментарий виден на странице тура
    def test_comment_visible_on_tour_page(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        self.post_comment(self.horse_tour, text='Супер маршрут')
        self.assertContains(self.client.get(self.horse_tour.get_absolute_url()), 'Супер маршрут')

    # Ссылка «Оставить комментарий» видна только побывавшим на туре
    def test_can_comment_flag(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        self.assertTrue(self.client.get(self.horse_tour.get_absolute_url()).context['can_comment'])
        self.assertFalse(self.client.get(self.moto_tour.get_absolute_url()).context['can_comment'])

    # Гость не видит ссылку на комментарий
    def test_can_comment_false_for_anonymous(self):
        response = self.client.get(self.horse_tour.get_absolute_url())
        self.assertFalse(response.context['can_comment'])

    # Метод has_visited
    def test_has_visited(self):
        self.book(self.ivan, self.horse_tour)
        self.assertTrue(self.ivan.has_visited(self.horse_tour))
        self.assertFalse(self.ivan.has_visited(self.moto_tour))
        self.assertFalse(self.olga.has_visited(self.horse_tour))


# =====================================================================
# 4. КАТЕГОРИИ ТУРОВ
# =====================================================================
class CategoryTests(BaseTestCase):
    """Категории «Конный», «Пеший», «Мото»"""

    # У туров есть категории с нужными названиями
    def test_tours_have_categories(self):
        self.assertEqual(self.horse_tour.categories.get().name, 'Конный')
        self.assertEqual(self.hiking_tour.categories.get().name, 'Пеший')
        self.assertEqual(self.moto_tour.categories.get().name, 'Мото')

    # В каталоге видны названия категорий
    def test_list_shows_category_names(self):
        response = self.client.get(reverse('tours:list'))
        for name in ('Конный', 'Пеший', 'Мото'):
            self.assertContains(response, name)

    # Фильтр по категории оставляет только туры этой категории
    def test_filter_by_category(self):
        response = self.client.get(reverse('tours:list'), {'category': self.horse.pk})
        self.assertEqual(list(response.context['tours']), [self.horse_tour])
        self.assertEqual(response.context['current_category'], self.horse)

    # Фильтр «Мото»
    def test_filter_moto(self):
        response = self.client.get(reverse('tours:list'), {'category': self.moto.pk})
        self.assertEqual(list(response.context['tours']), [self.moto_tour])

    # Тур с двумя категориями виден в обеих
    def test_tour_in_two_categories_shown_in_both(self):
        self.horse_tour.categories.add(self.hiking)
        for cat in (self.horse, self.hiking):
            response = self.client.get(reverse('tours:list'), {'category': cat.pk})
            self.assertIn(self.horse_tour, response.context['tours'])

    # Без фильтра показываются все туры
    def test_no_filter_shows_all(self):
        response = self.client.get(reverse('tours:list'))
        self.assertEqual(len(response.context['tours']), 3)

    # Несуществующая категория — 404
    def test_unknown_category_404(self):
        self.assertEqual(self.client.get(reverse('tours:list'), {'category': 9999}).status_code, 404)

    # Некорректное значение категории — 404
    def test_invalid_category_404(self):
        self.assertEqual(self.client.get(reverse('tours:list'), {'category': 'abc'}).status_code, 404)

    # Категория без туров даёт пустой список
    def test_empty_category(self):
        extra = Category.objects.create(name='Велосипедный')
        response = self.client.get(reverse('tours:list'), {'category': extra.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Туров нет.')

    # Скрытые туры не показываются в каталоге и недоступны
    def test_inactive_tour_hidden(self):
        self.horse_tour.is_active = False
        self.horse_tour.save()
        self.assertNotIn(self.horse_tour, self.client.get(reverse('tours:list')).context['tours'])
        self.assertEqual(self.client.get(self.horse_tour.get_absolute_url()).status_code, 404)


# =====================================================================
# 5. ОТПРАВКА ДАННЫХ: РЕГИСТРАЦИЯ, ВХОД, ВЫХОД
# =====================================================================
class RegisterSubmissionTests(BaseTestCase):
    """POST /register/"""

    url = '/register/'
    valid = {'username': 'newuser', 'password1': PASSWORD, 'password2': PASSWORD, 'phone': '+996700111222'}

    # Страница регистрации открывается
    def test_page_opens(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], RegisterForm)

    # Корректная регистрация создаёт пользователя и профиль (1:1) и входит в систему
    def test_valid_registration(self):
        response = self.client.post(self.url, self.valid)
        self.assertRedirects(response, reverse('tours:list'))
        user = User.objects.get(username='newuser')
        self.assertEqual(user.customer.phone, '+996700111222')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    # Телефон необязателен
    def test_phone_optional(self):
        data = {**self.valid}
        del data['phone']
        self.client.post(self.url, data)
        self.assertEqual(User.objects.get(username='newuser').customer.phone, '')

    # Пароль хранится в виде хеша
    def test_password_is_hashed(self):
        self.client.post(self.url, self.valid)
        self.assertNotEqual(User.objects.get(username='newuser').password, PASSWORD)

    # Занятое имя пользователя отклоняется
    def test_duplicate_username(self):
        response = self.client.post(self.url, {**self.valid, 'username': 'ivan'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(User.objects.filter(username='ivan').count(), 1)

    # Разные пароли отклоняются, пользователь не создаётся
    def test_password_mismatch(self):
        response = self.client.post(self.url, {**self.valid, 'password2': 'другой-пароль-123'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    # Слишком простой пароль отклоняется
    def test_weak_password(self):
        data = {**self.valid, 'password1': '12345678', 'password2': '12345678'}
        self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    # Пустое имя пользователя отклоняется
    def test_missing_username(self):
        self.client.post(self.url, {**self.valid, 'username': ''})
        self.assertFalse(Customer.objects.filter(user__username='').exists())
        self.assertEqual(User.objects.count(), 2)

    # Пустая форма ничего не создаёт
    def test_empty_form(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Customer.objects.count(), 2)

    # Слишком длинный телефон отклоняется
    def test_phone_too_long(self):
        self.client.post(self.url, {**self.valid, 'phone': '1' * 21})
        self.assertFalse(User.objects.filter(username='newuser').exists())


class LoginLogoutSubmissionTests(BaseTestCase):
    """POST /login/ и /logout/"""

    # Страница входа открывается
    def test_login_page_opens(self):
        self.assertEqual(self.client.get(reverse('tours:login')).status_code, 200)

    # Верные данные: вход и редирект на каталог
    def test_login_valid(self):
        response = self.client.post(reverse('tours:login'), {'username': 'ivan', 'password': PASSWORD})
        self.assertRedirects(response, reverse('tours:list'))
        self.assertIn('_auth_user_id', self.client.session)

    # Неверный пароль: вход не выполнен
    def test_login_wrong_password(self):
        response = self.client.post(reverse('tours:login'), {'username': 'ivan', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    # Несуществующий пользователь
    def test_login_unknown_user(self):
        response = self.client.post(reverse('tours:login'), {'username': 'ghost', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    # Пустая форма входа
    def test_login_empty(self):
        response = self.client.post(reverse('tours:login'), {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    # Вход с параметром next возвращает на нужную страницу
    def test_login_next_redirect(self):
        response = self.client.post(reverse('tours:login') + '?next=/bookings/',
                                    {'username': 'ivan', 'password': PASSWORD})
        self.assertRedirects(response, '/bookings/')

    # Выход выполняется только через POST и разлогинивает пользователя
    def test_logout_post(self):
        self.login(self.ivan)
        response = self.client.post(reverse('tours:logout'))
        self.assertRedirects(response, reverse('tours:list'))
        self.assertNotIn('_auth_user_id', self.client.session)

    # GET на выход не разрешён
    def test_logout_get_not_allowed(self):
        self.login(self.ivan)
        self.assertEqual(self.client.get(reverse('tours:logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)


# =====================================================================
# 6. ОТПРАВКА ДАННЫХ: ПОКУПКА, ОТМЕНА, КОММЕНТАРИЙ (доступ и ошибки)
# =====================================================================
class BookingSubmissionAccessTests(BaseTestCase):
    """POST /tours/<id>/book/"""

    # Гость перенаправляется на вход (GET и POST), бронирование не создаётся
    def test_anonymous_redirected(self):
        url = reverse('tours:book', args=[self.horse_tour.pk])
        login_url = f"{reverse('tours:login')}?next={url}"
        self.assertRedirects(self.client.get(url), login_url)
        self.assertRedirects(self.client.post(url, {'date': future(), 'time': '09:00'}), login_url)
        self.assertEqual(Booking.objects.count(), 0)

    # Форма покупки открывается у вошедшего пользователя
    def test_page_opens(self):
        self.login(self.ivan)
        response = self.client.get(reverse('tours:book', args=[self.horse_tour.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], BookingForm)

    # Несуществующий тур — 404 и на GET, и на POST
    def test_unknown_tour_404(self):
        self.login(self.ivan)
        url = reverse('tours:book', args=[9999])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'date': future(), 'time': '09:00'}).status_code, 404)

    # Скрытый тур купить нельзя
    def test_inactive_tour_404(self):
        self.horse_tour.is_active = False
        self.horse_tour.save()
        self.login(self.ivan)
        response = self.client.post(reverse('tours:book', args=[self.horse_tour.pk]),
                                    {'date': future(), 'time': '09:00'})
        self.assertEqual(response.status_code, 404)

    # Администратор без профиля клиента: профиль создаётся автоматически
    def test_user_without_profile_gets_customer(self):
        admin = User.objects.create_superuser('boss', password=PASSWORD)
        self.client.login(username='boss', password=PASSWORD)
        self.client.post(reverse('tours:book', args=[self.horse_tour.pk]), {'date': future(), 'time': '12:00'})
        self.assertEqual(Booking.objects.get().customer.user, admin)


class CancelSubmissionTests(BaseTestCase):
    """POST /bookings/<id>/cancel/"""

    # Клиент отменяет своё бронирование
    def test_cancel_own_booking(self):
        booking = self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        response = self.client.post(reverse('tours:cancel_booking', args=[booking.pk]))
        self.assertRedirects(response, reverse('tours:my_bookings'))
        self.assertFalse(Booking.objects.filter(pk=booking.pk).exists())

    # Чужое бронирование отменить нельзя (404), оно остаётся
    def test_cannot_cancel_foreign_booking(self):
        booking = self.book(self.olga, self.horse_tour)
        self.login(self.ivan)
        response = self.client.post(reverse('tours:cancel_booking', args=[booking.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    # GET на отмену не разрешён, бронирование остаётся
    def test_get_not_allowed(self):
        booking = self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        self.assertEqual(self.client.get(reverse('tours:cancel_booking', args=[booking.pk])).status_code, 405)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    # Гость перенаправляется на вход
    def test_anonymous_redirected(self):
        booking = self.book(self.ivan, self.horse_tour)
        response = self.client.post(reverse('tours:cancel_booking', args=[booking.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    # Несуществующее бронирование — 404
    def test_unknown_booking_404(self):
        self.login(self.ivan)
        self.assertEqual(self.client.post(reverse('tours:cancel_booking', args=[9999])).status_code, 404)


class CommentSubmissionAccessTests(BaseTestCase):
    """POST /tours/<id>/comment/"""

    # Гость перенаправляется на вход, комментарий не создаётся
    def test_anonymous_redirected(self):
        url = reverse('tours:comment', args=[self.horse_tour.pk])
        response = self.client.post(url, {'text': 'x', 'rating': 5})
        self.assertRedirects(response, f"{reverse('tours:login')}?next={url}")
        self.assertEqual(Comment.objects.count(), 0)

    # Форма комментария открывается
    def test_page_opens(self):
        self.login(self.ivan)
        response = self.client.get(reverse('tours:comment', args=[self.horse_tour.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], CommentForm)

    # Несуществующий тур — 404
    def test_unknown_tour_404(self):
        self.login(self.ivan)
        response = self.client.post(reverse('tours:comment', args=[9999]), {'text': 'x', 'rating': 5})
        self.assertEqual(response.status_code, 404)

    # Пустая форма не создаёт комментарий
    def test_empty_post(self):
        self.book(self.ivan, self.horse_tour)
        self.login(self.ivan)
        response = self.client.post(reverse('tours:comment', args=[self.horse_tour.pk]), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 0)


# =====================================================================
# 7. CSRF-ЗАЩИТА ВСЕХ ФОРМ
# =====================================================================
class CsrfProtectionTests(BaseTestCase):
    """Все POST-формы отклоняют запросы без csrf-токена"""

    # Каждая отправка данных без токена даёт 403 и ничего не меняет
    def test_all_post_endpoints_require_csrf(self):
        booking = self.book(self.ivan, self.horse_tour)
        strict = Client(enforce_csrf_checks=True)
        strict.login(username='ivan', password=PASSWORD)
        endpoints = [
            (reverse('tours:register'), {'username': 'x', 'password1': PASSWORD, 'password2': PASSWORD}),
            (reverse('tours:login'), {'username': 'ivan', 'password': PASSWORD}),
            (reverse('tours:logout'), {}),
            (reverse('tours:book', args=[self.moto_tour.pk]), {'date': future(9), 'time': '12:00'}),
            (reverse('tours:cancel_booking', args=[booking.pk]), {}),
            (reverse('tours:comment', args=[self.horse_tour.pk]), {'text': 'x', 'rating': 5}),
        ]
        for url, data in endpoints:
            with self.subTest(url=url):
                self.assertEqual(strict.post(url, data).status_code, 403)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Comment.objects.count(), 0)


# =====================================================================
# 8. СТРАНИЦЫ (GET)
# =====================================================================
class PagesTests(BaseTestCase):
    """Обычные страницы"""

    # Каталог открывается и использует нужный шаблон
    def test_list_page(self):
        response = self.client.get(reverse('tours:list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tours/tour_list.html')

    # Страница тура показывает данные и категории
    def test_detail_page(self):
        response = self.client.get(self.horse_tour.get_absolute_url())
        self.assertContains(response, 'Горы верхом')
        self.assertContains(response, 'Конный')

    # Несуществующий тур — 404
    def test_detail_404(self):
        self.assertEqual(self.client.get(reverse('tours:detail', args=[9999])).status_code, 404)

    # «Мои туры» показывают только свои бронирования
    def test_my_bookings_only_own(self):
        self.book(self.ivan, self.horse_tour)
        self.book(self.olga, self.moto_tour)
        self.login(self.ivan)
        response = self.client.get(reverse('tours:my_bookings'))
        self.assertEqual([b.tour for b in response.context['bookings']], [self.horse_tour])

    # Пустые «Мои туры» показывают заглушку
    def test_my_bookings_empty(self):
        self.login(self.ivan)
        self.assertContains(self.client.get(reverse('tours:my_bookings')), 'ни одного тура')

    # «Мои туры» недоступны гостю
    def test_my_bookings_anonymous_redirect(self):
        self.assertEqual(self.client.get(reverse('tours:my_bookings')).status_code, 302)


# =====================================================================
# 9. ДОКУМЕНТАЦИЯ (Django admindocs)
# =====================================================================
class AdminDocsTests(BaseTestCase):
    """Документация проекта: /admin/doc/"""

    def setUp(self):
        User.objects.create_superuser('boss', password=PASSWORD)
        self.client.login(username='boss', password=PASSWORD)

    # Главная страница документации открывается
    def test_docs_index(self):
        self.assertEqual(self.client.get('/admin/doc/').status_code, 200)

    # Список моделей содержит модели приложения tours
    def test_docs_models_list(self):
        response = self.client.get('/admin/doc/models/')
        self.assertContains(response, 'Tour')
        self.assertContains(response, 'Booking')

    # Документация модели Booking содержит описание правила
    def test_docs_model_booking(self):
        response = self.client.get('/admin/doc/models/tours.booking/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'определённые')

    # Документация показывает связи (поля-связи) модели Tour
    def test_docs_model_tour_relations(self):
        response = self.client.get('/admin/doc/models/tours.tour/')
        self.assertContains(response, 'categories')

    # Список представлений открывается
    def test_docs_views(self):
        self.assertEqual(self.client.get('/admin/doc/views/').status_code, 200)

    # Документация без входа недоступна
    def test_docs_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get('/admin/doc/').status_code, 302)

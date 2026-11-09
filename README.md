# Конные туры (Django, приложение `tours`)

## Запуск
    py -m pip install -r requirements.txt
    py manage.py migrate
    py manage.py seed_demo          # демо-данные: категории, туры, пользователь demo / demo-pass-123
    py manage.py test               # 103 теста
    py manage.py runserver          # http://127.0.0.1:8000/

## Что где (по требованиям)
| Требование | Где |
|---|---|
| Startapp | `tours/` |
| Связь 1:1 | `Customer.user` — `OneToOneField(User)` |
| Связь 1:M | `Booking.customer`, `Booking.tour`, `Comment.customer`, `Comment.tour` (`ForeignKey`) |
| Связь M:M | `Tour.categories` — `ManyToManyField(Category)` |
| 1 человек — 1 тур на день и время | `Booking`: `UniqueConstraint(customer, date, time)` + `Booking.clean()` + `BookingForm` |
| Несколько комментариев к турам, где был | `Comment.clean()` + `Customer.has_visited()`; ограничения на число комментариев нет |
| Категории «Конный», «Пеший», «Мото» | модель `Category`, фильтр `/?category=<id>` |
| Тесты на все отправки данных | `tours/tests.py`: регистрация, вход, выход, покупка, отмена, комментарий, CSRF |
| Документация через Django docs | `django.contrib.admindocs`: см. ниже |

## Все формы (отправки данных)
| Адрес | Что отправляется |
|---|---|
| `/register/` | регистрация (создаёт User + Customer) |
| `/login/`, `/logout/` | вход, выход (POST) |
| `/tours/<id>/book/` | покупка тура: дата + время |
| `/bookings/<id>/cancel/` | отмена бронирования (POST) |
| `/tours/<id>/comment/` | комментарий: текст + оценка 1–5 |

## Документация (Django docs / admindocs)
1. `py manage.py createsuperuser`
2. `py manage.py runserver`
3. Войти в админку http://127.0.0.1:8000/admin/ и открыть http://127.0.0.1:8000/admin/doc/
   - `/admin/doc/models/`  — модели, поля, связи (текст берётся из docstring и help_text)
   - `/admin/doc/views/`   — представления (страницы)
   - `/admin/doc/models/tours.booking/` — например, документация модели Booking

## Ручная проверка
1. Зайти под demo / demo-pass-123, открыть тур, «Купить тур», выбрать дату и время.
2. Купить любой тур на то же время ещё раз: появится ошибка «У вас уже куплен тур на эту дату и время».
3. На странице купленного тура «Оставить комментарий» — можно оставить несколько.
4. На тур, который не покупали, комментировать нельзя.
5. Каталог: фильтр по категориям Конный / Пеший / Мото.

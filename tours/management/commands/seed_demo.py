"""python manage.py seed_demo — заполняет базу примерами для проверки."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tours.models import Category, Customer, Tour

TOURS = [
    ('Горный маршрут на лошадях', 'Три часа верхом по ущелью.', 3500, 3, ['Конный']),
    ('Закат в седле', 'Вечерняя прогулка верхом.', 2500, 2, ['Конный']),
    ('Каньон Сказка пешком', 'Пеший маршрут по каньону.', 1200, 4, ['Пеший']),
    ('Мото-тур по Иссык-Кулю', 'Поездка на мотоциклах вдоль озера.', 6000, 6, ['Мото']),
    ('Конно-пеший поход', 'Половина пути верхом, половина пешком.', 4000, 5, ['Конный', 'Пеший']),
]


class Command(BaseCommand):
    help = 'Создаёт категории, туры и демо-пользователя demo / demo-pass-123.'

    def handle(self, *args, **options):
        cats = {name: Category.objects.get_or_create(name=name)[0] for name in ('Конный', 'Пеший', 'Мото')}
        for title, desc, price, hours, cat_names in TOURS:
            tour, _ = Tour.objects.get_or_create(
                title=title, defaults={'description': desc, 'price': price, 'duration_hours': hours})
            tour.categories.set([cats[n] for n in cat_names])
        user, created = get_user_model().objects.get_or_create(username='demo')
        if created:
            user.set_password('demo-pass-123')
            user.save()
        Customer.objects.get_or_create(user=user)
        self.stdout.write(self.style.SUCCESS('Готово. Демо-вход: demo / demo-pass-123'))

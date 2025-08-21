from django.db import models
from django.utils import timezone

class Client(models.Model):
    name = models.CharField(max_length=200, verbose_name="Имя клиента")
    contacts = models.TextField(verbose_name="Контакты")
    notes = models.TextField(blank=True, verbose_name="Примечания")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"


class Order(models.Model):
    STATUS_CHOICES = [
        ('unpaid', 'Неоплачен'),
        ('paid', 'Оплачен'),
        ('completed', 'Завершен'),
    ]
    
    name = models.CharField(max_length=200, verbose_name="Название сделки")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Клиент")
    cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость")
    deadline = models.DateField(verbose_name="Срок исполнения")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid', verbose_name="Статус")
    date = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    
    def __str__(self):
        return f"{self.name} - {self.client.name}"

    class Meta:
        verbose_name = "Сделка"
        verbose_name_plural = "Сделки"


class Expense(models.Model):
    comment = models.TextField(verbose_name="Комментарий")
    cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    date = models.DateTimeField(default=timezone.now, verbose_name="Дата")
    
    def __str__(self):
        return f"{self.comment} - {self.cost}"

    class Meta:
        verbose_name = "Расход"
        verbose_name_plural = "Расходы"
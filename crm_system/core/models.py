from django.db import models

class Client(models.Model):
    name = models.CharField("Имя", max_length=100)
    contacts = models.TextField("Контакты")
    notes = models.TextField("Примечание", blank=True)
    
    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = (
        ('unpaid', 'Не оплачен'),
        ('paid', 'Оплачен'),
        ('completed', 'Завершен'),
    )
    
    date = models.DateField("Дата создания", auto_now_add=True)
    deadline = models.DateField("Срок исполнения", null=True, blank=True)
    name = models.CharField("Наименование", max_length=200)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='unpaid')
    cost = models.DecimalField("Стоимость", max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"{self.name} ({self.client})"
    
    @property
    def is_active(self):
        return self.status in ['unpaid', 'paid']

class Expense(models.Model):
    date = models.DateField("Дата", auto_now_add=True)
    comment = models.TextField("Комментарий")
    cost = models.DecimalField("Стоимость", max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.comment
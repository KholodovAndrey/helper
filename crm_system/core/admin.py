from django.contrib import admin
from .models import Client, Order, Expense

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'contacts')
    search_fields = ('name',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'date', 'deadline', 'status', 'cost')
    list_editable = ('deadline', 'status', 'cost')
    list_filter = ('status', 'date', 'deadline')
    date_hierarchy = 'date'
    search_fields = ('name', 'client__name')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('comment', 'date', 'cost')
    date_hierarchy = 'date'
    search_fields = ('comment',)
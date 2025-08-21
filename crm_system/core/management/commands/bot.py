import os
import datetime
from django.core.management.base import BaseCommand
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from core.models import Client, Order, Expense
from asgiref.sync import sync_to_async

# Состояния для ConversationHandler
(
    # Клиенты
    AWAITING_CLIENT_NAME,
    AWAITING_CLIENT_CONTACTS,
    AWAITING_CLIENT_NOTES,
    
    # Сделки
    AWAITING_ORDER_NAME,
    AWAITING_ORDER_CLIENT,
    AWAITING_ORDER_COST,
    AWAITING_ORDER_DEADLINE,
    
    # Операции
    AWAITING_INCOME_ORDER,
    AWAITING_EXPENSE_COMMENT,
    AWAITING_EXPENSE_COST,
    
    # Дополнительные
    AWAITING_PAYMENT_ORDER,
    AWAITING_COMPLETION_ORDER
) = range(13)

class Command(BaseCommand):
    help = 'Запуск телеграм-бота CRM системы'
    
    def handle(self, *args, **kwargs):
        TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
        if not TOKEN:
            self.stderr.write("Ошибка: Не задан TELEGRAM_BOT_TOKEN")
            return
        
        application = Application.builder().token(TOKEN).build()
        
        # Conversation Handler для пошагового ввода
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_main_menu)
            ],
            states={
                # Клиенты
                AWAITING_CLIENT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_name)
                ],
                AWAITING_CLIENT_CONTACTS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_contacts)
                ],
                AWAITING_CLIENT_NOTES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_notes)
                ],
                
                # Сделки
                AWAITING_ORDER_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_name)
                ],
                AWAITING_ORDER_CLIENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_client)
                ],
                AWAITING_ORDER_COST: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_cost)
                ],
                AWAITING_ORDER_DEADLINE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_deadline)
                ],
                
                # Операции
                AWAITING_INCOME_ORDER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_income)
                ],
                AWAITING_EXPENSE_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_expense_comment)
                ],
                AWAITING_EXPENSE_COST: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_expense_cost)
                ],
                
                # Дополнительные
                AWAITING_PAYMENT_ORDER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_payment)
                ],
                AWAITING_COMPLETION_ORDER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_completion)
                ],
            },
            fallbacks=[MessageHandler(filters.Regex('^🔙 Назад$'), self.back_to_main)],
        )
        
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("start", self.start))
        
        self.stdout.write(self.style.SUCCESS('Бот запущен...'))
        application.run_polling()

    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка главного меню"""
        text = update.message.text
        
        if text == '👥 Клиенты':
            await self.show_clients_menu(update, context)
        elif text == '📋 Сделки':
            await self.show_orders_menu(update, context)
        elif text == '💼 Операции':
            await self.show_operations_menu(update, context)
        elif text == '📊 Статистика':
            await self.show_stats(update, context)
        elif text == '🔙 Назад':
            await self.show_main_menu(update, context)
        else:
            await self.show_main_menu(update, context)
        
        return ConversationHandler.END

    async def handle_clients_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню клиентов"""
        text = update.message.text
        
        if text == '➕ Добавить клиента':
            await update.message.reply_text(
                "Введите имя клиента:",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_CLIENT_NAME
        elif text == '📋 Список клиентов':
            await self.list_clients(update, context)
        elif text == '🔙 Назад':
            await self.show_main_menu(update, context)
        
        return ConversationHandler.END

    async def handle_orders_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню сделок"""
        text = update.message.text
        
        if text == '➕ Добавить сделку':
            await update.message.reply_text(
                "Введите наименование сделки:",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_ORDER_NAME
        elif text == '📈 Активные сделки':
            await self.show_active_orders(update, context)
        elif text == '📁 Архив сделок':
            await self.show_archived_orders(update, context)
        elif text == '🔙 Назад':
            await self.show_main_menu(update, context)
        
        return ConversationHandler.END

    async def handle_operations_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню операций"""
        text = update.message.text
        
        if text == '💰 Добавить доход':
            await self.add_income(update, context)
            return AWAITING_INCOME_ORDER
        elif text == '💸 Добавить расход':
            await update.message.reply_text(
                "Введите комментарий к расходу:",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_EXPENSE_COMMENT
        elif text == '📋 История операций':
            await self.show_operations_history(update, context)
        elif text == '🔙 Назад':
            await self.show_main_menu(update, context)
        
        return ConversationHandler.END

    async def back_to_main(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат в главное меню"""
        await self.show_main_menu(update, context)
        return ConversationHandler.END

    # ===== ОСНОВНЫЕ МЕНЮ =====
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        keyboard = [
            ['👥 Клиенты', '📋 Сделки'],
            ['💼 Операции', '📊 Статистика']
        ]
        
        await update.message.reply_text(
            "🏠 Главное меню\nВыберите раздел:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    async def show_clients_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню клиентов"""
        keyboard = [
            ['➕ Добавить клиента', '📋 Список клиентов'],
            ['🔙 Назад']
        ]
        
        await update.message.reply_text(
            "👥 Управление клиентами\nВыберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    async def show_orders_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню сделок"""
        keyboard = [
            ['➕ Добавить сделку'],
            ['📈 Активные сделки', '📁 Архив сделок'],
            ['🔙 Назад']
        ]
        
        await update.message.reply_text(
            "📋 Управление сделками\nВыберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    async def show_operations_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню операций"""
        keyboard = [
            ['💰 Добавить доход', '💸 Добавить расход'],
            ['📋 История операций'],
            ['🔙 Назад']
        ]
        
        await update.message.reply_text(
            "💼 Финансовые операции\nВыберите действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

    # ===== АСИНХРОННЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БД =====
    @sync_to_async
    def create_client(self, name, contacts, notes=''):
        return Client.objects.create(
            name=name,
            contacts=contacts,
            notes=notes
        )

    @sync_to_async
    def create_order(self, name, client, cost, deadline):
        return Order.objects.create(
            name=name,
            client=client,
            cost=cost,
            deadline=deadline
        )

    @sync_to_async
    def create_expense(self, comment, cost):
        return Expense.objects.create(
            comment=comment,
            cost=cost
        )

    @sync_to_async
    def get_client_by_name(self, name):
        try:
            return Client.objects.get(name=name)
        except Client.DoesNotExist:
            return None

    @sync_to_async
    def get_all_clients(self):
        return list(Client.objects.all())

    @sync_to_async
    def get_unpaid_orders(self):
        return list(Order.objects.filter(status='unpaid'))

    @sync_to_async
    def get_paid_orders(self):
        return list(Order.objects.filter(status='paid'))

    @sync_to_async
    def get_completed_orders(self):
        return list(Order.objects.filter(status='completed'))

    @sync_to_async
    def get_all_orders(self):
        return list(Order.objects.all())

    @sync_to_async
    def get_all_expenses(self):
        return list(Expense.objects.all())

    @sync_to_async
    def update_order_status(self, order_id, status):
        try:
            order = Order.objects.get(id=order_id)
            order.status = status
            order.save()
            return True
        except Order.DoesNotExist:
            return False

    @sync_to_async
    def get_order_stats(self):
        total_orders = Order.objects.count()
        active_orders = Order.objects.filter(status__in=['unpaid', 'paid']).count()
        archived_orders = Order.objects.filter(status='completed').count()
        expensive_order = Order.objects.order_by('-cost').first()
        
        return total_orders, active_orders, archived_orders, expensive_order

    @sync_to_async
    def get_financial_stats(self):
        total_income = sum(order.cost for order in Order.objects.filter(status__in=['paid', 'completed']))
        total_expense = sum(expense.cost for expense in Expense.objects.all())
        
        now = datetime.datetime.now()
        month_income = sum(order.cost for order in Order.objects.filter(
            status__in=['paid', 'completed'],
            date__month=now.month,
            date__year=now.year
        ))
        
        month_expense = sum(expense.cost for expense in Expense.objects.filter(
            date__month=now.month,
            date__year=now.year
        ))
        
        return total_income, total_expense, month_income, month_expense

    # ===== КОМАНДА START =====
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск бота"""
        await update.message.reply_text(
            "🚀 Добро пожаловать в CRM систему!\n\n"
            "Доступные разделы:\n"
            "👥 Клиенты - управление клиентами\n"
            "📋 Сделки - работа с заказами\n"
            "💼 Операции - финансовые операции\n"
            "📊 Статистика - отчеты и аналитика"
        )
        
        await self.show_main_menu(update, context)
        return ConversationHandler.END

    # ===== РАБОТА С КЛИЕНТАМИ =====
    async def get_client_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение имени клиента"""
        if update.message.text == '🔙 Назад':
            await self.show_clients_menu(update, context)
            return ConversationHandler.END
            
        context.user_data['client_name'] = update.message.text
        await update.message.reply_text("Введите контакты клиента:")
        return AWAITING_CLIENT_CONTACTS

    async def get_client_contacts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение контактов клиента"""
        if update.message.text == '🔙 Назад':
            await self.show_clients_menu(update, context)
            return ConversationHandler.END
            
        context.user_data['client_contacts'] = update.message.text
        await update.message.reply_text("Введите примечание (или 'пропустить' чтобы пропустить):")
        return AWAITING_CLIENT_NOTES

    async def get_client_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение примечания клиента"""
        if update.message.text == '🔙 Назад':
            await self.show_clients_menu(update, context)
            return ConversationHandler.END
            
        if update.message.text.lower() != 'пропустить':
            context.user_data['client_notes'] = update.message.text
        else:
            context.user_data['client_notes'] = ''
        
        await self.create_client(
            context.user_data['client_name'],
            context.user_data['client_contacts'],
            context.user_data.get('client_notes', '')
        )
        
        await update.message.reply_text("✅ Клиент успешно добавлен!")
        context.user_data.clear()
        
        await self.show_clients_menu(update, context)
        return ConversationHandler.END

    async def list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список всех клиентов"""
        clients = await self.get_all_clients()
        if not clients:
            await update.message.reply_text("📝 Клиентов пока нет.")
        else:
            response = "📋 Список клиентов:\n\n"
            for client in clients:
                response += f"● {client.name} - {client.contacts}\n"
                if client.notes:
                    response += f"  Примечание: {client.notes}\n"
                response += "\n"
            
            await update.message.reply_text(response)
        
        await self.show_clients_menu(update, context)

    # ===== РАБОТА СО СДЕЛКАМИ =====
    async def get_order_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение названия сделки"""
        if update.message.text == '🔙 Назад':
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
            
        context.user_data['order_name'] = update.message.text
        
        clients = await self.get_all_clients()
        if not clients:
            await update.message.reply_text("❌ Нет клиентов. Сначала добавьте клиента.")
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
        
        keyboard = [[client.name] for client in clients]
        keyboard.append(['🔙 Назад'])
        
        await update.message.reply_text(
            "Выберите клиента из списка:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return AWAITING_ORDER_CLIENT

    async def get_order_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение клиента для сделки"""
        if update.message.text == '🔙 Назад':
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
            
        client = await self.get_client_by_name(update.message.text)
        
        if client:
            context.user_data['order_client'] = client
            await update.message.reply_text(
                "Введите стоимость сделки (только число):",
                reply_markup=ReplyKeyboardRemove()
            )
            return AWAITING_ORDER_COST
        else:
            await update.message.reply_text("❌ Клиент не найден. Попробуйте еще раз:")
            return AWAITING_ORDER_CLIENT

    async def get_order_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение стоимости сделки"""
        if update.message.text == '🔙 Назад':
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
            
        try:
            cost = float(update.message.text)
            context.user_data['order_cost'] = cost
            
            # Создаем клавиатуру с датами для календарика
            today = datetime.date.today()
            dates_keyboard = []
            
            # Предлагаем даты на ближайшие 7 дней
            for i in range(7):
                date = today + datetime.timedelta(days=i)
                dates_keyboard.append([date.strftime('%d.%m.%Y')])
            
            dates_keyboard.append(['🔙 Назад'])
            
            await update.message.reply_text(
                "Выберите дату исполнения или введите свою (ДД.ММ.ГГГГ):",
                reply_markup=ReplyKeyboardMarkup(dates_keyboard, resize_keyboard=True)
            )
            return AWAITING_ORDER_DEADLINE
        except ValueError:
            await update.message.reply_text("❌ Неверный формат стоимости. Введите число:")
            return AWAITING_ORDER_COST

    async def get_order_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение дедлайна сделки"""
        if update.message.text == '🔙 Назад':
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
            
        try:
            deadline = datetime.datetime.strptime(update.message.text, '%d.%m.%Y').date()
            
            await self.create_order(
                context.user_data['order_name'],
                context.user_data['order_client'],
                context.user_data['order_cost'],
                deadline
            )
            
            await update.message.reply_text("✅ Сделка успешно создана!")
            context.user_data.clear()
            
            await self.show_orders_menu(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
            return AWAITING_ORDER_DEADLINE

    async def show_active_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать активные сделки"""
        active_orders = await self.get_unpaid_orders()
        paid_orders = await self.get_paid_orders()
        
        if not active_orders and not paid_orders:
            await update.message.reply_text("📝 Активных сделок нет.")
        else:
            response = "📈 Активные сделки:\n\n"
            
            if active_orders:
                response += "💳 Неоплаченные:\n"
                for order in active_orders:
                    response += f"ID: {order.id} - {order.name} ({order.client.name}) - {order.cost} руб\n"
                response += "\n"
            
            if paid_orders:
                response += "✅ Оплаченные:\n"
                for order in paid_orders:
                    deadline_str = order.deadline.strftime('%d.%m.%Y') if order.deadline else "не указан"
                    response += f"ID: {order.id} - {order.name} ({order.client.name}) - {order.cost} руб\n"
                    response += f"  Срок: {deadline_str}\n"
                response += "\n"
            
            response += "💳 Для оплаты используйте меню 'Операции' -> 'Добавить доход'"
            
            await update.message.reply_text(response)
        
        await self.show_orders_menu(update, context)

    async def show_archived_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать архив сделок"""
        completed_orders = await self.get_completed_orders()
        
        if not completed_orders:
            await update.message.reply_text("📁 Архив сделок пуст.")
        else:
            response = "📁 Архив завершенных сделок:\n\n"
            for order in completed_orders:
                deadline_str = order.deadline.strftime('%d.%m.%Y') if order.deadline else "не указан"
                response += f"● {order.name} ({order.client.name})\n"
                response += f"  Стоимость: {order.cost} руб\n"
                response += f"  Срок: {deadline_str}\n"
                response += f"  Дата создания: {order.date.strftime('%d.%m.%Y')}\n\n"
            
            await update.message.reply_text(response)
        
        await self.show_orders_menu(update, context)

    # ===== ОПЕРАЦИИ =====
    async def add_income(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление дохода"""
        unpaid_orders = await self.get_unpaid_orders()
        
        if not unpaid_orders:
            await update.message.reply_text("❌ Нет неоплаченных сделок.")
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
        
        response = "💳 Неоплаченные сделки:\n\n"
        for order in unpaid_orders:
            response += f"ID: {order.id} - {order.name} ({order.client.name}) - {order.cost} руб\n"
        
        response += "\nВведите ID сделки для учета оплаты:"
        
        await update.message.reply_text(response)
        return AWAITING_INCOME_ORDER

    async def process_income(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка дохода"""
        if update.message.text == '🔙 Назад':
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
            
        try:
            order_id = int(update.message.text)
            success = await self.update_order_status(order_id, 'paid')
            
            if success:
                await update.message.reply_text("✅ Оплата учтена! Сделка перемещена в оплаченные.")
            else:
                await update.message.reply_text("❌ Неверный ID сделки или сделка уже оплачена.")
            
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Введите число:")
            return AWAITING_INCOME_ORDER

    async def get_expense_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение комментария расхода"""
        if update.message.text == '🔙 Назад':
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
            
        context.user_data['expense_comment'] = update.message.text
        await update.message.reply_text("Введите сумму расхода (только число):")
        return AWAITING_EXPENSE_COST

    async def get_expense_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение суммы расхода"""
        if update.message.text == '🔙 Назад':
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
            
        try:
            cost = float(update.message.text)
            
            await self.create_expense(
                context.user_data['expense_comment'],
                cost
            )
            
            await update.message.reply_text("✅ Расход успешно добавлен!")
            context.user_data.clear()
            
            await self.show_operations_menu(update, context)
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы. Введите число:")
            return AWAITING_EXPENSE_COST

    async def show_operations_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """История операций"""
        expenses = await self.get_all_expenses()
        paid_orders = await self.get_paid_orders()
        
        if not expenses and not paid_orders:
            await update.message.reply_text("📝 История операций пуста.")
        else:
            response = "📋 История операций:\n\n"
            
            if paid_orders:
                response += "💰 Доходы (оплаченные сделки):\n"
                for order in paid_orders:
                    response += f"● {order.date.strftime('%d.%m.%Y')} - {order.name} - +{order.cost} руб\n"
                response += "\n"
            
            if expenses:
                response += "💸 Расходы:\n"
                for expense in expenses:
                    response += f"● {expense.date.strftime('%d.%m.%Y')} - {expense.comment} - -{expense.cost} руб\n"
            
            # Итоги
            total_income = sum(order.cost for order in paid_orders)
            total_expense = sum(expense.cost for expense in expenses)
            balance = total_income - total_expense
            
            response += f"\n📊 Итоги:\n"
            response += f"Общий доход: {total_income} руб\n"
            response += f"Общий расход: {total_expense} руб\n"
            response += f"Баланс: {balance} руб"
            
            await update.message.reply_text(response)
        
        await self.show_operations_menu(update, context)

    # ===== СТАТИСТИКА =====
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика системы"""
        total_orders, active_orders, archived_orders, expensive_order = await self.get_order_stats()
        total_income, total_expense, month_income, month_expense = await self.get_financial_stats()
        
        clients_count = len(await self.get_all_clients())
        
        response = (
            f"📊 Статистика системы\n\n"
            f"👥 Клиенты: {clients_count}\n"
            f"📋 Всего сделок: {total_orders}\n"
            f"📈 Активных: {active_orders}\n"
            f"📁 В архиве: {archived_orders}\n"
            f"💰 Самая крупная сделка: {expensive_order.name if expensive_order else 'N/A'} "
            f"({expensive_order.cost if expensive_order else 0} руб)\n\n"
            f"💵 Общий доход: {total_income} руб\n"
            f"💸 Общий расход: {total_expense} руб\n"
            f"⚖️ Баланс: {total_income - total_expense} руб\n"
            f"📅 Доход за месяц: {month_income} руб\n"
            f"📅 Расход за месяц: {month_expense} руб\n"
            f"📅 Месячный баланс: {month_income - month_expense} руб"
        )
        
        await update.message.reply_text(response)
        await self.show_main_menu(update, context)
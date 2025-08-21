import os
import datetime
import logging
from enum import Enum
from django.core.management.base import BaseCommand
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackContext
)
from core.models import Client, Order, Expense
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from django.core.exceptions import MultipleObjectsReturned

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler с использованием Enum для лучшей читаемости
class State(Enum):
    MAIN_MENU = 0
    CLIENTS_MENU = 1
    ORDERS_MENU = 2
    OPERATIONS_MENU = 3
    AWAITING_CLIENT_NAME = 4
    AWAITING_CLIENT_CONTACTS = 5
    AWAITING_CLIENT_NOTES = 6
    AWAITING_ORDER_NAME = 7
    AWAITING_ORDER_CLIENT = 8
    AWAITING_ORDER_COST = 9
    AWAITING_ORDER_DEADLINE = 10
    AWAITING_INCOME_ORDER = 11
    AWAITING_EXPENSE_COMMENT = 12
    AWAITING_EXPENSE_COST = 13
    AWAITING_COMPLETE_ORDER = 14

# Тексты кнопок для избежания "магических строк"
class ButtonText:
    CLIENTS = '👥 Клиенты'
    ORDERS = '📋 Сделки'
    OPERATIONS = '💼 Операции'
    STATS = '📊 Статистика'
    ADD_CLIENT = '➕ Добавить клиента'
    LIST_CLIENTS = '📋 Список клиентов'
    BACK = '🔙 Назад'
    ADD_ORDER = '➕ Добавить сделку'
    ACTIVE_ORDERS = '📈 Активные сделки'
    ARCHIVED_ORDERS = '📁 Архив сделок'
    COMPLETE_ORDER = '✅ Завершить сделку'
    ADD_INCOME = '💰 Добавить доход'
    ADD_EXPENSE = '💸 Добавить расход'
    OPERATIONS_HISTORY = '📋 История операций'
    SKIP = 'пропустить'

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
                CommandHandler("start", self.start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_main_menu)
            ],
            states={
                State.MAIN_MENU.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_main_menu)
                ],
                State.CLIENTS_MENU.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_clients_menu)
                ],
                State.ORDERS_MENU.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_orders_menu)
                ],
                State.OPERATIONS_MENU.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_operations_menu)
                ],
                State.AWAITING_CLIENT_NAME.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_name)
                ],
                State.AWAITING_CLIENT_CONTACTS.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_contacts)
                ],
                State.AWAITING_CLIENT_NOTES.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_client_notes)
                ],
                State.AWAITING_ORDER_NAME.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_name)
                ],
                State.AWAITING_ORDER_CLIENT.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_client)
                ],
                State.AWAITING_ORDER_COST.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_cost)
                ],
                State.AWAITING_ORDER_DEADLINE.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_order_deadline)
                ],
                State.AWAITING_INCOME_ORDER.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_income)
                ],
                State.AWAITING_EXPENSE_COMMENT.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_expense_comment)
                ],
                State.AWAITING_EXPENSE_COST.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_expense_cost)
                ],
                State.AWAITING_COMPLETE_ORDER.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_complete_order)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            map_to_parent={
                ConversationHandler.END: State.MAIN_MENU.value,
            }
        )
        
        application.add_handler(conv_handler)
        
        # Обработчик ошибок
        application.add_error_handler(self.error_handler)
        
        self.stdout.write(self.style.SUCCESS('Бот запущен...'))
        application.run_polling()

    async def error_handler(self, update: object, context: CallbackContext) -> None:
        """Обработчик ошибок для логгирования исключений."""
        logger.error("Exception while handling an update:", exc_info=context.error)

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
        return State.MAIN_MENU.value

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        
        await self.show_main_menu(update, context)
        return State.MAIN_MENU.value

    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка главного меню"""
        text = update.message.text
        
        if text == ButtonText.CLIENTS:
            await self.show_clients_menu(update, context)
            return State.CLIENTS_MENU.value
        elif text == ButtonText.ORDERS:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
        elif text == ButtonText.OPERATIONS:
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
        elif text == ButtonText.STATS:
            await self.show_stats(update, context)
            return State.MAIN_MENU.value
        else:
            await update.message.reply_text("Пожалуйста, выберите один из вариантов меню:")
            await self.show_main_menu(update, context)
            return State.MAIN_MENU.value

    async def handle_clients_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню клиентов"""
        text = update.message.text
        
        if text == ButtonText.ADD_CLIENT:
            await update.message.reply_text(
                "Введите имя клиента:",
                reply_markup=ReplyKeyboardRemove()
            )
            return State.AWAITING_CLIENT_NAME.value
        elif text == ButtonText.LIST_CLIENTS:
            await self.list_clients(update, context)
            return State.CLIENTS_MENU.value
        elif text == ButtonText.BACK:
            await self.show_main_menu(update, context)
            return State.MAIN_MENU.value
        else:
            await update.message.reply_text("Пожалуйста, выберите один из вариантов меню:")
            await self.show_clients_menu(update, context)
            return State.CLIENTS_MENU.value

    async def handle_orders_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню сделок"""
        text = update.message.text
        
        if text == ButtonText.ADD_ORDER:
            await update.message.reply_text(
                "Введите наименование сделки:",
                reply_markup=ReplyKeyboardRemove()
            )
            return State.AWAITING_ORDER_NAME.value
        elif text == ButtonText.ACTIVE_ORDERS:
            await self.show_active_orders(update, context)
            return State.ORDERS_MENU.value
        elif text == ButtonText.ARCHIVED_ORDERS:
            await self.show_archived_orders(update, context)
            return State.ORDERS_MENU.value
        elif text == ButtonText.COMPLETE_ORDER:
            return await self.ask_order_id_to_complete(update, context)
        elif text == ButtonText.BACK:
            await self.show_main_menu(update, context)
            return State.MAIN_MENU.value
        else:
            await update.message.reply_text("Пожалуйста, выберите один из вариантов меню:")
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value

    async def handle_operations_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка меню операций"""
        text = update.message.text
        
        if text == ButtonText.ADD_INCOME:
            return await self.add_income(update, context)
        elif text == ButtonText.ADD_EXPENSE:
            await update.message.reply_text(
                "Введите комментарий к расходу:",
                reply_markup=ReplyKeyboardRemove()
            )
            return State.AWAITING_EXPENSE_COMMENT.value
        elif text == ButtonText.OPERATIONS_HISTORY:
            await self.show_operations_history(update, context)
            return State.OPERATIONS_MENU.value
        elif text == ButtonText.BACK:
            await self.show_main_menu(update, context)
            return State.MAIN_MENU.value
        else:
            await update.message.reply_text("Пожалуйста, выберите один из вариантов меню:")
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value

    # ===== ОСНОВНЫЕ МЕНЮ =====
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню"""
        keyboard = [
            [ButtonText.CLIENTS, ButtonText.ORDERS],
            [ButtonText.OPERATIONS, ButtonText.STATS]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        if update.message:
            await update.message.reply_text(
                "🏠 Главное меню\nВыберите раздел:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "🏠 Главное меню\nВыберите раздел:",
                reply_markup=reply_markup
            )

    async def show_clients_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню клиентов"""
        keyboard = [
            [ButtonText.ADD_CLIENT, ButtonText.LIST_CLIENTS],
            [ButtonText.BACK]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        if update.message:
            await update.message.reply_text(
                "👥 Управление клиентами\nВыберите действие:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "👥 Управление клиентами\nВыберите действие:",
                reply_markup=reply_markup
            )

    async def show_orders_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню сделок"""
        keyboard = [
            [ButtonText.ADD_ORDER],
            [ButtonText.ACTIVE_ORDERS, ButtonText.ARCHIVED_ORDERS],
            [ButtonText.COMPLETE_ORDER],
            [ButtonText.BACK]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        if update.message:
            await update.message.reply_text(
                "📋 Управление сделками\nВыберите действие:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "📋 Управление сделками\nВыберите действие:",
                reply_markup=reply_markup
            )

    async def show_operations_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню операций"""
        keyboard = [
            [ButtonText.ADD_INCOME, ButtonText.ADD_EXPENSE],
            [ButtonText.OPERATIONS_HISTORY],
            [ButtonText.BACK]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        if update.message:
            await update.message.reply_text(
                "💼 Финансовые операции\nВыберите действие:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "💼 Финансовые операции\nВыберите действие:",
                reply_markup=reply_markup
            )

    # ===== АСИНХРОННЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БД =====
    @sync_to_async
    def create_client(self, name, contacts, notes=''):
        try:
            return Client.objects.create(
                name=name,
                contacts=contacts,
                notes=notes
            )
        except IntegrityError:
            logger.error(f"Ошибка при создании клиента: имя '{name}' уже существует")
            return None

    @sync_to_async
    def create_order(self, name, client, cost, deadline):
        try:
            return Order.objects.create(
                name=name,
                client=client,
                cost=cost,
                deadline=deadline
            )
        except Exception as e:
            logger.error(f"Ошибка при создании сделки: {e}")
            return None

    @sync_to_async
    def create_expense(self, comment, cost):
        try:
            return Expense.objects.create(
                comment=comment,
                cost=cost
            )
        except Exception as e:
            logger.error(f"Ошибка при создании расхода: {e}")
            return None

    @sync_to_async
    def get_client_by_name(self, name):
        try:
            return Client.objects.get(name=name)
        except Client.DoesNotExist:
            return None
        except MultipleObjectsReturned:
            logger.warning(f"Найдено несколько клиентов с именем '{name}'")
            return Client.objects.filter(name=name).first()

    @sync_to_async
    def get_all_clients(self):
        return list(Client.objects.all())

    @sync_to_async
    def get_unpaid_orders(self):
        return list(Order.objects.filter(status='unpaid').select_related('client'))

    @sync_to_async
    def get_paid_orders(self):
        return list(Order.objects.filter(status='paid').select_related('client'))

    @sync_to_async
    def get_completed_orders(self):
        return list(Order.objects.filter(status='completed').select_related('client'))

    @sync_to_async
    def get_all_orders(self):
        return list(Order.objects.all().select_related('client'))

    @sync_to_async
    def get_all_expenses(self):
        return list(Expense.objects.all())

    @sync_to_async
    def update_order_status(self, order_id, status):
        try:
            order = Order.objects.get(id=order_id)
            order.status = status
            order.save()
            return True, order
        except Order.DoesNotExist:
            return False, None
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса сделки: {e}")
            return False, None

    @sync_to_async
    def get_order_stats(self):
        try:
            total_orders = Order.objects.count()
            active_orders = Order.objects.filter(status__in=['unpaid', 'paid']).count()
            archived_orders = Order.objects.filter(status='completed').count()
            expensive_order = Order.objects.order_by('-cost').first()
            
            return total_orders, active_orders, archived_orders, expensive_order
        except Exception as e:
            logger.error(f"Ошибка при получении статистики по сделкам: {e}")
            return 0, 0, 0, None

    @sync_to_async
    def get_financial_stats(self):
        try:
            paid_completed_orders = Order.objects.filter(status__in=['paid', 'completed'])
            total_income = sum(order.cost for order in paid_completed_orders)
            
            expenses = Expense.objects.all()
            total_expense = sum(expense.cost for expense in expenses)
            
            now = datetime.datetime.now()
            month_orders = Order.objects.filter(
                status__in=['paid', 'completed'],
                date__month=now.month,
                date__year=now.year
            )
            month_income = sum(order.cost for order in month_orders)
            
            month_expenses = Expense.objects.filter(
                date__month=now.month,
                date__year=now.year
            )
            month_expense = sum(expense.cost for expense in month_expenses)
            
            return total_income, total_expense, month_income, month_expense
        except Exception as e:
            logger.error(f"Ошибка при получении финансовой статистики: {e}")
            return 0, 0, 0, 0

    # ===== РАБОТА С КЛИЕНТАМИ =====
    async def get_client_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение имени клиента"""
        if update.message.text == ButtonText.BACK:
            await self.show_clients_menu(update, context)
            return State.CLIENTS_MENU.value
            
        context.user_data['client_name'] = update.message.text
        await update.message.reply_text("Введите контакты клиента:")
        return State.AWAITING_CLIENT_CONTACTS.value

    async def get_client_contacts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение контактов клиента"""
        if update.message.text == ButtonText.BACK:
            await self.show_clients_menu(update, context)
            return State.CLIENTS_MENU.value
            
        context.user_data['client_contacts'] = update.message.text
        await update.message.reply_text("Введите примечание (или 'пропустить' чтобы пропустить):")
        return State.AWAITING_CLIENT_NOTES.value

    async def get_client_notes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение примечания клиента"""
        if update.message.text == ButtonText.BACK:
            await self.show_clients_menu(update, context)
            return State.CLIENTS_MENU.value
            
        if update.message.text.lower() != ButtonText.SKIP:
            context.user_data['client_notes'] = update.message.text
        else:
            context.user_data['client_notes'] = ''
        
        client = await self.create_client(
            context.user_data['client_name'],
            context.user_data['client_contacts'],
            context.user_data.get('client_notes', '')
        )
        
        if client:
            await update.message.reply_text("✅ Клиент успешно добавлен!")
        else:
            await update.message.reply_text("❌ Ошибка при добавлении клиента. Возможно, клиент с таким именем уже существует.")
        
        context.user_data.clear()
        
        await self.show_clients_menu(update, context)
        return State.CLIENTS_MENU.value

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
            
            # Разделяем сообщение если оно слишком длинное
            if len(response) > 4096:
                for x in range(0, len(response), 4096):
                    await update.message.reply_text(response[x:x+4096])
            else:
                await update.message.reply_text(response)
        
        await self.show_clients_menu(update, context)

    # ===== РАБОТА СО СДЕЛКАМИ =====
    async def get_order_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение названия сделки"""
        if update.message.text == ButtonText.BACK:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
            
        context.user_data['order_name'] = update.message.text
        
        clients = await self.get_all_clients()
        if not clients:
            await update.message.reply_text("❌ Нет клиентов. Сначала добавьте клиента.")
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
        
        keyboard = [[client.name] for client in clients]
        keyboard.append([ButtonText.BACK])
        
        await update.message.reply_text(
            "Выберите клиента из списка:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return State.AWAITING_ORDER_CLIENT.value
    
    async def ask_order_id_to_complete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запрос ID сделки для завершения"""
        paid_orders = await self.get_paid_orders()
    
        if not paid_orders:
            await update.message.reply_text("❌ Нет оплаченных сделок для завершения.")
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
    
        response = "✅ Оплаченные сделки (готовые к завершению):\n\n"
        for order in paid_orders:
            response += f"ID: {order.id} - {order.name} ({order.client.name}) - {order.cost} руб\n"
    
        response += "\nВведите ID сделки для завершения:"
    
        await update.message.reply_text(response)
        return State.AWAITING_COMPLETE_ORDER.value

    async def process_complete_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка завершения сделки"""
        if update.message.text == ButtonText.BACK:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
    
        try:
            order_id = int(update.message.text)
            success, order = await self.update_order_status(order_id, 'completed')
    
            if success:
                # Используем sync_to_async для доступа к связанным полям
                order_name = await sync_to_async(lambda: order.name)()
                client_name = await sync_to_async(lambda: order.client.name)()
            
                await update.message.reply_text(
                    f"✅ Сделка '{order_name}' ({client_name}) успешно завершена и перемещена в архив."
                )
            else:
                await update.message.reply_text("❌ Неверный ID сделки или сделка уже завершена.")
    
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Введите число:")
            return State.AWAITING_COMPLETE_ORDER.value

    async def get_order_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение клиента для сделки"""
        if update.message.text == ButtonText.BACK:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
            
        client = await self.get_client_by_name(update.message.text)
        
        if client:
            context.user_data['order_client'] = client
            await update.message.reply_text(
                "Введите стоимость сделки (только число):",
                reply_markup=ReplyKeyboardRemove()
            )
            return State.AWAITING_ORDER_COST.value
        else:
            await update.message.reply_text("❌ Клиент не найден. Попробуйте еще раз:")
            return State.AWAITING_ORDER_CLIENT.value

    async def get_order_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение стоимости сделки"""
        if update.message.text == ButtonText.BACK:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
            
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
            
            dates_keyboard.append([ButtonText.BACK])
            
            await update.message.reply_text(
                "Выберите дату исполнения или введите свою (ДД.ММ.ГГГГ):",
                reply_markup=ReplyKeyboardMarkup(dates_keyboard, resize_keyboard=True)
            )
            return State.AWAITING_ORDER_DEADLINE.value
        except ValueError:
            await update.message.reply_text("❌ Неверный формат стоимости. Введите число:")
            return State.AWAITING_ORDER_COST.value

    async def get_order_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение дедлайна сделки"""
        if update.message.text == ButtonText.BACK:
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
            
        try:
            deadline = datetime.datetime.strptime(update.message.text, '%d.%m.%Y').date()
            
            order = await self.create_order(
                context.user_data['order_name'],
                context.user_data['order_client'],
                context.user_data['order_cost'],
                deadline
            )
            
            if order:
                await update.message.reply_text("✅ Сделка успешно создана!")
            else:
                await update.message.reply_text("❌ Ошибка при создании сделки.")
                
            context.user_data.clear()
            
            await self.show_orders_menu(update, context)
            return State.ORDERS_MENU.value
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ:")
            return State.AWAITING_ORDER_DEADLINE.value

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
        
            # Разделяем сообщение если оно слишком длинное
            if len(response) > 4096:
                for x in range(0, len(response), 4096):
                    await update.message.reply_text(response[x:x+4096])
            else:
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
                # Используем sync_to_async для доступа к связанным полям
                order_name = await sync_to_async(lambda: order.name)()
                client_name = await sync_to_async(lambda: order.client.name)()
                deadline_str = await sync_to_async(lambda: order.deadline.strftime('%d.%m.%Y') if order.deadline else "не указан")()
                date_str = await sync_to_async(lambda: order.date.strftime('%d.%m.%Y'))()
        
                response += f"● {order_name} ({client_name})\n"
                response += f"  Стоимость: {order.cost} руб\n"
                response += f"  Срок: {deadline_str}\n"
                response += f"  Дата создания: {date_str}\n\n"

            # Разделяем сообщение если оно слишком длинное
            if len(response) > 4096:
                for x in range(0, len(response), 4096):
                    await update.message.reply_text(response[x:x+4096])
            else:
                await update.message.reply_text(response)

        await self.show_orders_menu(update, context)

    # ===== ОПЕРАЦИИ =====
    async def add_income(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление дохода"""
        unpaid_orders = await self.get_unpaid_orders()
    
        if not unpaid_orders:
            await update.message.reply_text("❌ Нет неоплаченных сделок.")
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
    
        response = "💳 Неоплаченные сделки:\n\n"
        for order in unpaid_orders:
            response += f"ID: {order.id} - {order.name} ({order.client.name}) - {order.cost} руб\n"
    
        response += "\nВведите ID сделки для учета оплаты:"
    
        await update.message.reply_text(response)
        return State.AWAITING_INCOME_ORDER.value

    async def process_income(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка дохода"""
        if update.message.text == ButtonText.BACK:
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
        
        try:
            order_id = int(update.message.text)
            success, order = await self.update_order_status(order_id, 'paid')
        
            if success:
                # Используем sync_to_async для доступа к связанным полям
                order_name = await sync_to_async(lambda: order.name)()
                client_name = await sync_to_async(lambda: order.client.name)()
                
                await update.message.reply_text(
                    f"✅ Оплата учтена! Сделка '{order_name}' ({client_name}) перемещена в оплаченные."
                )
            else:
                await update.message.reply_text("❌ Неверный ID сделки или сделка уже оплачена.")
        
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID. Введите число:")
            return State.AWAITING_INCOME_ORDER.value

    async def get_expense_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение комментария расхода"""
        if update.message.text == ButtonText.BACK:
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
            
        context.user_data['expense_comment'] = update.message.text
        await update.message.reply_text("Введите сумму расхода (только число):")
        return State.AWAITING_EXPENSE_COST.value

    async def get_expense_cost(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение суммы расхода"""
        if update.message.text == ButtonText.BACK:
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
            
        try:
            cost = float(update.message.text)
            
            expense = await self.create_expense(
                context.user_data['expense_comment'],
                cost
            )
            
            if expense:
                await update.message.reply_text("✅ Расход успешно добавлен!")
            else:
                await update.message.reply_text("❌ Ошибка при добавлении расхода.")
                
            context.user_data.clear()
            
            await self.show_operations_menu(update, context)
            return State.OPERATIONS_MENU.value
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы. Введите число:")
            return State.AWAITING_EXPENSE_COST.value

    async def show_operations_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """История операций"""
        expenses = await self.get_all_expenses()
        paid_orders = await self.get_paid_orders()
        completed_orders = await self.get_completed_orders()
        
        if not expenses and not paid_orders and not completed_orders:
            await update.message.reply_text("📝 История операций пуста.")
        else:
            response = "📋 История операций:\n\n"
            
            if paid_orders or completed_orders:
                response += "💰 Доходы (оплаченные и завершенные сделки):\n"
                for order in paid_orders + completed_orders:
                    # Используем sync_to_async для доступа к связанным полям
                    order_name = await sync_to_async(lambda: order.name)()
                    date_str = await sync_to_async(lambda: order.date.strftime('%d.%m.%Y'))()
                    response += f"● {date_str} - {order_name} - +{order.cost} руб\n"
                response += "\n"
            
            if expenses:
                response += "💸 Расходы:\n"
                for expense in expenses:
                    date_str = await sync_to_async(lambda: expense.date.strftime('%d.%m.%Y'))()
                    response += f"● {date_str} - {expense.comment} - -{expense.cost} руб\n"
            
            # Итоги
            total_income = sum(order.cost for order in paid_orders + completed_orders)
            total_expense = sum(expense.cost for expense in expenses)
            balance = total_income - total_expense
            
            response += f"\n📊 Итоги:\n"
            response += f"Общий доход: {total_income} руб\n"
            response += f"Общий расход: {total_expense} руб\n"
            response += f"Баланс: {balance} руб"
            
            # Разделяем сообщение если оно слишком длинное
            if len(response) > 4096:
                for x in range(0, len(response), 4096):
                    await update.message.reply_text(response[x:x+4096])
            else:
                await update.message.reply_text(response)
        
        await self.show_operations_menu(update, context)

    # ===== СТАТИСТИКА =====
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика системы"""
        total_orders, active_orders, archived_orders, expensive_order = await self.get_order_stats()
        total_income, total_expense, month_income, month_expense = await self.get_financial_stats()
        
        clients_count = len(await self.get_all_clients())
        
        expensive_order_name = expensive_order.name if expensive_order else 'N/A'
        expensive_order_cost = expensive_order.cost if expensive_order else 0
        
        response = (
            f"📊 Статистика системы\n\n"
            f"👥 Клиенты: {clients_count}\n"
            f"📋 Всего сделок: {total_orders}\n"
            f"📈 Активных: {active_orders}\n"
            f"📁 В архиве: {archived_orders}\n"
            f"💰 Самая крупная сделка: {expensive_order_name} "
            f"({expensive_order_cost} руб)\n\n"
            f"💵 Общий доход: {total_income} руб\n"
            f"💸 Общий расход: {total_expense} руб\n"
            f"⚖️ Баланс: {total_income - total_expense} руб\n"
            f"📅 Доход за месяц: {month_income} руб\n"
            f"📅 Расход за месяц: {month_expense} руб\n"
            f"📅 Месячный баланс: {month_income - month_expense} руб"
        )
        
        await update.message.reply_text(response)
        await self.show_main_menu(update, context)
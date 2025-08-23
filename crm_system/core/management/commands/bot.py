import os
import datetime
import logging
import asyncio
from enum import Enum
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from django.core.exceptions import MultipleObjectsReturned

# Aiogram импорты
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command as AiogramCommand, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.enums import ParseMode

# Импорты для календаря
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

# Модели Django
from core.models import Client, Order, Expense

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

# Состояния FSM
class Form(StatesGroup):
    MAIN_MENU = State()
    CLIENTS_MENU = State()
    ORDERS_MENU = State()
    OPERATIONS_MENU = State()
    AWAITING_CLIENT_NAME = State()
    AWAITING_CLIENT_CONTACTS = State()
    AWAITING_CLIENT_NOTES = State()
    AWAITING_ORDER_NAME = State()
    AWAITING_ORDER_CLIENT = State()
    AWAITING_ORDER_COST = State()
    AWAITING_ORDER_DEADLINE = State()
    AWAITING_EXPENSE_COMMENT = State()
    AWAITING_EXPENSE_COST = State()

# ===== АСИНХРОННЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С БД =====
@sync_to_async
def create_client(name, contacts, notes=''):
    try:
        client = Client.objects.create(
            name=name,
            contacts=contacts,
            notes=notes
        )
        logger.info(f"Created client: {name}")
        return client
    except IntegrityError:
        logger.error(f"Error creating client: name '{name}' already exists")
        return None
    except Exception as e:
        logger.error(f"Error creating client: {e}")
        return None

@sync_to_async
def create_order(name, client, cost, deadline):
    try:
        order = Order.objects.create(
            name=name,
            client=client,
            cost=cost,
            deadline=deadline
        )
        logger.info(f"Created order: {name} for client {client.name}")
        return order
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        return None

@sync_to_async
def create_expense(comment, cost):
    try:
        expense = Expense.objects.create(
            comment=comment,
            cost=cost
        )
        logger.info(f"Created expense: {comment} - {cost}")
        return expense
    except Exception as e:
        logger.error(f"Error creating expense: {e}")
        return None

@sync_to_async
def get_client_by_name(name):
    try:
        return Client.objects.get(name=name)
    except Client.DoesNotExist:
        logger.warning(f"Client not found: {name}")
        return None
    except MultipleObjectsReturned:
        logger.warning(f"Multiple clients found with name: {name}")
        return Client.objects.filter(name=name).first()

@sync_to_async
def get_all_clients():
    return list(Client.objects.all())

@sync_to_async
def get_unpaid_orders():
    return list(Order.objects.filter(status='unpaid').select_related('client'))

@sync_to_async
def get_paid_orders():
    return list(Order.objects.filter(status='paid').select_related('client'))

@sync_to_async
def get_completed_orders():
    return list(Order.objects.filter(status='completed').select_related('client'))

@sync_to_async
def update_order_status(order_id, status):
    try:
        order = Order.objects.get(id=order_id)
        order.status = status
        order.save()
        logger.info(f"Updated order {order_id} status to {status}")
        return True, order
    except Order.DoesNotExist:
        logger.error(f"Order not found: {order_id}")
        return False, None
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return False, None

@sync_to_async
def get_order_stats():
    try:
        total_orders = Order.objects.count()
        active_orders = Order.objects.filter(status__in=['unpaid', 'paid']).count()
        archived_orders = Order.objects.filter(status='completed').count()
        expensive_order = Order.objects.order_by('-cost').first()
        
        return total_orders, active_orders, archived_orders, expensive_order
    except Exception as e:
        logger.error(f"Error getting order stats: {e}")
        return 0, 0, 0, None

@sync_to_async
def get_financial_stats():
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
        logger.error(f"Error getting financial stats: {e}")
        return 0, 0, 0, 0

# ===== ОБРАБОТЧИКИ =====

async def error_handler(update: types.Update, exception: Exception):
    """Обработчик ошибок для логгирования исключений."""
    logger.error(f"Exception while handling an update: {exception}", exc_info=True)

async def start(message: types.Message, state: FSMContext):
    """Запуск бота"""
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "🚀 Добро пожаловать в CRM систему!\n\n"
        "Доступные разделы:\n"
        "👥 Клиенты - управление клиентами\n"
        "📋 Сделки - работа с заказами\n"
        "💼 Операции - финансовые операции\n"
        "📊 Статистика - отчеты и аналитика"
    )
    
    await show_main_menu(message, state)

async def cancel(message: types.Message, state: FSMContext):
    """Отмена текущей операции"""
    logger.info(f"User {message.from_user.id} canceled operation")
    await message.answer(
        "Операция отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()
    
    await show_main_menu(message, state)

async def handle_main_menu(message: types.Message, state: FSMContext):
    """Обработка главного меню"""
    text = message.text
    logger.info(f"User {message.from_user.id} selected: {text}")
    
    if text == ButtonText.CLIENTS:
        await show_clients_menu(message, state)
    elif text == ButtonText.ORDERS:
        await show_orders_menu(message, state)
    elif text == ButtonText.OPERATIONS:
        await show_operations_menu(message, state)
    elif text == ButtonText.STATS:
        await show_stats(message, state)
    else:
        await message.answer("Пожалуйста, выберите один из вариантов меню:")
        await show_main_menu(message, state)

async def handle_clients_menu(message: types.Message, state: FSMContext):
    """Обработка меню клиентов"""
    text = message.text
    logger.info(f"User {message.from_user.id} selected in clients menu: {text}")
    
    if text == ButtonText.ADD_CLIENT:
        await message.answer(
            "Введите имя клиента:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Form.AWAITING_CLIENT_NAME)
    elif text == ButtonText.LIST_CLIENTS:
        await list_clients(message, state)
    elif text == ButtonText.BACK:
        await show_main_menu(message, state)
    else:
        await message.answer("Пожалуйста, выберите один из вариантов меню:")
        await show_clients_menu(message, state)

async def handle_orders_menu(message: types.Message, state: FSMContext):
    """Обработка меню сделок"""
    text = message.text
    logger.info(f"User {message.from_user.id} selected in orders menu: {text}")
    
    if text == ButtonText.ADD_ORDER:
        await message.answer(
            "Введите наименование сделки:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Form.AWAITING_ORDER_NAME)
    elif text == ButtonText.ACTIVE_ORDERS:
        await show_active_orders(message, state)
    elif text == ButtonText.ARCHIVED_ORDERS:
        await show_archived_orders(message, state)
    elif text == ButtonText.COMPLETE_ORDER:
        await show_orders_to_complete(message, state)
    elif text == ButtonText.BACK:
        await show_main_menu(message, state)
    else:
        await message.answer("Пожалуйста, выберите один из вариантов меню:")
        await show_orders_menu(message, state)

async def handle_operations_menu(message: types.Message, state: FSMContext):
    """Обработка меню операций"""
    text = message.text
    logger.info(f"User {message.from_user.id} selected in operations menu: {text}")
    
    if text == ButtonText.ADD_INCOME:
        await show_orders_for_income(message, state)
    elif text == ButtonText.ADD_EXPENSE:
        await message.answer(
            "Введите комментарий к расходу:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Form.AWAITING_EXPENSE_COMMENT)
    elif text == ButtonText.OPERATIONS_HISTORY:
        await show_operations_history(message, state)
    elif text == ButtonText.BACK:
        await show_main_menu(message, state)
    else:
        await message.answer("Пожалуйста, выберите один из вариантов меню:")
        await show_operations_menu(message, state)

# ===== ОСНОВНЫЕ МЕНЮ =====
async def show_main_menu(message: types.Message, state: FSMContext):
    """Главное меню"""
    keyboard = [
        [KeyboardButton(text=ButtonText.CLIENTS), KeyboardButton(text=ButtonText.ORDERS)],
        [KeyboardButton(text=ButtonText.OPERATIONS), KeyboardButton(text=ButtonText.STATS)]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    await state.set_state(Form.MAIN_MENU)
    await message.answer(
        "🏠 Главное меню\nВыберите раздел:",
        reply_markup=reply_markup
    )

async def show_clients_menu(message: types.Message, state: FSMContext):
    """Меню клиентов"""
    keyboard = [
        [KeyboardButton(text=ButtonText.ADD_CLIENT), KeyboardButton(text=ButtonText.LIST_CLIENTS)],
        [KeyboardButton(text=ButtonText.BACK)]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    await state.set_state(Form.CLIENTS_MENU)
    await message.answer(
        "👥 Управление клиентами\nВыберите действие:",
        reply_markup=reply_markup
    )

async def show_orders_menu(message: types.Message, state: FSMContext):
    """Меню сделок"""
    keyboard = [
        [KeyboardButton(text=ButtonText.ADD_ORDER)],
        [KeyboardButton(text=ButtonText.ACTIVE_ORDERS), KeyboardButton(text=ButtonText.ARCHIVED_ORDERS)],
        [KeyboardButton(text=ButtonText.COMPLETE_ORDER)],
        [KeyboardButton(text=ButtonText.BACK)]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    await state.set_state(Form.ORDERS_MENU)
    await message.answer(
        "📋 Управление сделками\nВыберите действие:",
        reply_markup=reply_markup
    )

async def show_operations_menu(message: types.Message, state: FSMContext):
    """Меню операций"""
    keyboard = [
        [KeyboardButton(text=ButtonText.ADD_INCOME), KeyboardButton(text=ButtonText.ADD_EXPENSE)],
        [KeyboardButton(text=ButtonText.OPERATIONS_HISTORY)],
        [KeyboardButton(text=ButtonText.BACK)]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    await state.set_state(Form.OPERATIONS_MENU)
    await message.answer(
        "💼 Финансовые операции\nВыберите действие:",
        reply_markup=reply_markup
    )

# ===== РАБОТА С КЛИЕНТАМИ =====
async def get_client_name(message: types.Message, state: FSMContext):
    """Получение имени клиента"""
    if message.text == ButtonText.BACK:
        await show_clients_menu(message, state)
        return
        
    await state.update_data(client_name=message.text)
    await message.answer("Введите контакты клиента:")
    await state.set_state(Form.AWAITING_CLIENT_CONTACTS)

async def get_client_contacts(message: types.Message, state: FSMContext):
    """Получение контакты клиента"""
    if message.text == ButtonText.BACK:
        await show_clients_menu(message, state)
        return
        
    await state.update_data(client_contacts=message.text)
    await message.answer("Введите примечание (или 'пропустить' чтобы пропустить):")
    await state.set_state(Form.AWAITING_CLIENT_NOTES)

async def get_client_notes(message: types.Message, state: FSMContext):
    """Получение примечания клиента"""
    if message.text == ButtonText.BACK:
        await show_clients_menu(message, state)
        return
        
    data = await state.get_data()
    
    if message.text.lower() != ButtonText.SKIP:
        client_notes = message.text
    else:
        client_notes = ''
    
    client = await create_client(
        data['client_name'],
        data['client_contacts'],
        client_notes
    )
    
    if client:
        await message.answer("✅ Клиент успешно добавлен!")
    else:
        await message.answer("❌ Ошибка при добавлении клиента. Возможно, клиент с таким именем уже существует.")
    
    await state.clear()
    await show_clients_menu(message, state)

async def list_clients(message: types.Message, state: FSMContext):
    """Список всех клиентов"""
    clients = await get_all_clients()
    if not clients:
        await message.answer("📝 Клиентов пока нет.")
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
                await message.answer(response[x:x+4096])
        else:
            await message.answer(response)
    
    await show_clients_menu(message, state)

# ===== РАБОТА СО СДЕЛКАМИ =====
async def get_order_name(message: types.Message, state: FSMContext):
    """Получение названия сделки"""
    if message.text == ButtonText.BACK:
        await show_orders_menu(message, state)
        return
        
    await state.update_data(order_name=message.text)
    
    clients = await get_all_clients()
    if not clients:
        await message.answer("❌ Нет клиентов. Сначала добавьте клиента.")
        await show_orders_menu(message, state)
        return
    
    keyboard = [[KeyboardButton(text=client.name)] for client in clients]
    keyboard.append([KeyboardButton(text=ButtonText.BACK)])
    
    await message.answer(
        "Выберите клиента из списка:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )
    await state.set_state(Form.AWAITING_ORDER_CLIENT)

async def show_orders_to_complete(message: types.Message, state: FSMContext):
    """Показать оплаченные сделки для завершения с инлайн-кнопками"""
    paid_orders = await get_paid_orders()

    if not paid_orders:
        await message.answer("❌ Нет оплаченных сделок для завершения.")
        return
    
    keyboard = []
    for order in paid_orders:
        button_text = f"{order.name} ({order.client.name}) - {order.cost} руб"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"complete_{order.id}")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        "✅ Выберите сделку для завершения:",
        reply_markup=reply_markup
    )

async def complete_order_button_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия на инлайн-кнопку завершения сделки"""
    order_id = int(callback_query.data.split('_')[1])
    success, order = await update_order_status(order_id, 'completed')

    if success:
        # Используем sync_to_async для доступа к связанным полям
        order_name = await sync_to_async(lambda: order.name)()
        client_name = await sync_to_async(lambda: order.client.name)()
        
        await callback_query.message.edit_text(
            f"✅ Сделка '{order_name}' ({client_name}) успешно завершена и перемещена в архив."
        )
    else:
        await callback_query.message.edit_text("❌ Ошибка при завершении сделки.")

    # Показываем меню заказов после завершения
    await show_orders_menu(callback_query.message, state)

async def get_order_client(message: types.Message, state: FSMContext):
    """Получение клиента для сделки"""
    if message.text == ButtonText.BACK:
        await show_orders_menu(message, state)
        return
        
    client = await get_client_by_name(message.text)
    
    if client:
        await state.update_data(order_client=client)
        await message.answer(
            "Введите стоимость сделки (только число):",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Form.AWAITING_ORDER_COST)
    else:
        await message.answer("❌ Клиент не найден. Попробуйте еще раз:")
        await state.set_state(Form.AWAITING_ORDER_CLIENT)

async def get_order_cost(message: types.Message, state: FSMContext):
    """Получение стоимости сделки"""
    if message.text == ButtonText.BACK:
        await show_orders_menu(message, state)
        return
        
    try:
        cost = float(message.text)
        await state.update_data(order_cost=cost)
        
        # Показываем календарь вместо списка дат
        await message.answer(
            "Выберите дату исполнения:",
            reply_markup=await SimpleCalendar().start_calendar()
        )
        await state.set_state(Form.AWAITING_ORDER_DEADLINE)
    except ValueError:
        await message.answer("❌ Неверный формат стоимости. Введите число:")
        await state.set_state(Form.AWAITING_ORDER_COST)

async def process_calendar_selection(callback_query: types.CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    """Обработка выбора даты из календаря"""
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    
    if selected:
        # Проверка что дата не в прошлом
        if date.date() < datetime.date.today():
            await callback_query.message.edit_text("❌ Дата не может быть в прошлом. Выберите другую дату:")
            await callback_query.message.answer(
                "Выберите дату исполнения:",
                reply_markup=await SimpleCalendar().start_calendar()
            )
            return
        
        await callback_query.message.edit_text(f"Выбрана дата: {date.strftime('%d.%m.%Y')}")
        
        data = await state.get_data()
        
        order = await create_order(
            data['order_name'],
            data['order_client'],
            data['order_cost'],
            date.date()
        )
        
        if order:
            await callback_query.message.answer("✅ Сделка успешно создана!")
        else:
            await callback_query.message.answer("❌ Ошибка при создании сделки.")
            
        await state.clear()
        await show_orders_menu(callback_query.message, state)

async def show_active_orders(message: types.Message, state: FSMContext):
    """Показать активные сделки"""
    active_orders = await get_unpaid_orders()
    paid_orders = await get_paid_orders()

    if not active_orders and not paid_orders:
        await message.answer("📝 Активных сделок нет.")
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
    
        response += "💳 Для оплата используйте меню 'Операции' -> 'Добавить доход'"
    
        # Разделяем сообщение если оно слишком длинное
        if len(response) > 4096:
            for x in range(0, len(response), 4096):
                await message.answer(response[x:x+4096])
        else:
            await message.answer(response)

    await show_orders_menu(message, state)

async def show_archived_orders(message: types.Message, state: FSMContext):
    """Показать архив сделок"""
    completed_orders = await get_completed_orders()

    if not completed_orders:
        await message.answer("📁 Архив сделок пуст.")
    else:
        response = "📁 Архив завершенных сделок:\n\n"
        for order in completed_orders:
            deadline_str = order.deadline.strftime('%d.%m.%Y') if order.deadline else "не указан"
            date_str = order.date.strftime('%d.%m.%Y')
    
            response += f"● {order.name} ({order.client.name})\n"
            response += f"  Стоимость: {order.cost} руб\n"
            response += f"  Срок: {deadline_str}\n"
            response += f"  Дата создания: {date_str}\n\n"

        # Разделяем сообщение если оно слишком длинное
        if len(response) > 4096:
            for x in range(0, len(response), 4096):
                await message.answer(response[x:x+4096])
        else:
            await message.answer(response)

    await show_orders_menu(message, state)

# ===== ОПЕРАЦИИ =====
async def show_orders_for_income(message: types.Message, state: FSMContext):
    """Показать неоплаченные сделки для добавления дохода с инлайн-кнопками"""
    unpaid_orders = await get_unpaid_orders()

    if not unpaid_orders:
        await message.answer("❌ Нет неоплаченных сделок.")
        return

    keyboard = []
    for order in unpaid_orders:
        button_text = f"{order.name} ({order.client.name}) - {order.cost} руб"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"income_{order.id}")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        "💳 Выберите сделку для учета оплаты:",
        reply_markup=reply_markup
    )

async def income_button_handler(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик нажатия на инлайн-кнопку добавления дохода"""
    order_id = int(callback_query.data.split('_')[1])
    success, order = await update_order_status(order_id, 'paid')

    if success:
        # Используем sync_to_async для доступа к связанным полям
        order_name = await sync_to_async(lambda: order.name)()
        client_name = await sync_to_async(lambda: order.client.name)()
        
        await callback_query.message.edit_text(
            f"✅ Оплата учтена! Сделка '{order_name}' ({client_name}) перемещена в оплаченные."
        )
    else:
        await callback_query.message.edit_text("❌ Ошибка при учете оплаты.")

    # Показываем меню операций после добавления дохода
    await show_operations_menu(callback_query.message, state)

async def get_expense_comment(message: types.Message, state: FSMContext):
    """Получение комментария расхода"""
    if message.text == ButtonText.BACK:
        await show_operations_menu(message, state)
        return
        
    await state.update_data(expense_comment=message.text)
    await message.answer("Введите сумму расхода (только число):")
    await state.set_state(Form.AWAITING_EXPENSE_COST)

async def get_expense_cost(message: types.Message, state: FSMContext):
    """Получение суммы расхода"""
    if message.text == ButtonText.BACK:
        await show_operations_menu(message, state)
        return
        
    try:
        cost = float(message.text)
        
        data = await state.get_data()
        expense = await create_expense(
            data['expense_comment'],
            cost
        )
        
        if expense:
            await message.answer("✅ Расход успешно добавлен!")
        else:
            await message.answer("❌ Ошибка при добавлении расхода.")
            
        await state.clear()
        await show_operations_menu(message, state)
    except ValueError:
        await message.answer("❌ Неверный формат суммы. Введите число:")
        await state.set_state(Form.AWAITING_EXPENSE_COST)

async def show_operations_history(message: types.Message, state: FSMContext):
    """История операций"""
    expenses = await sync_to_async(list)(Expense.objects.all())
    paid_orders = await get_paid_orders()
    completed_orders = await get_completed_orders()
    
    if not expenses and not paid_orders and not completed_orders:
        await message.answer("📝 История операций пуста.")
    else:
        response = "📋 История операций:\n\n"
        
        if paid_orders or completed_orders:
            response += "💰 Доходы (оплаченные и завершенные сделки):\n"
            for order in paid_orders + completed_orders:
                date_str = order.date.strftime('%d.%m.%Y')
                response += f"● {date_str} - {order.name} - +{order.cost} руб\n"
            response += "\n"
        
        if expenses:
            response += "💸 Расходы:\n"
            for expense in expenses:
                date_str = expense.date.strftime('%d.%m.%Y')
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
                await message.answer(response[x:x+4096])
        else:
            await message.answer(response)
    
    await show_operations_menu(message, state)

# ===== СТАТИСТИКА =====
async def show_stats(message: types.Message, state: FSMContext):
    """Статистика системы"""
    total_orders, active_orders, archived_orders, expensive_order = await get_order_stats()
    total_income, total_expense, month_income, month_expense = await get_financial_stats()
    
    clients_count = len(await get_all_clients())
    
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
    
    await message.answer(response)
    await show_main_menu(message, state)

class Command(BaseCommand):
    help = 'Запуск телеграм-бота CRM системы на aiogram'
    
    def handle(self, *args, **kwargs):
        TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
        if not TOKEN:
            self.stderr.write("Ошибка: Не задан TELEGRAM_BOT_TOKEN")
            return
        
        # Инициализация бота и диспетчера
        storage = MemoryStorage()
        bot = Bot(token=TOKEN)
        dp = Dispatcher(storage=storage)
        
        # Регистрация обработчиков
        dp.message.register(start, AiogramCommand("start"))
        dp.message.register(cancel, AiogramCommand("cancel"))
        
        # Главное меню
        dp.message.register(handle_main_menu, StateFilter(Form.MAIN_MENU))
        
        # Меню клиентов
        dp.message.register(handle_clients_menu, StateFilter(Form.CLIENTS_MENU))
        dp.message.register(get_client_name, StateFilter(Form.AWAITING_CLIENT_NAME))
        dp.message.register(get_client_contacts, StateFilter(Form.AWAITING_CLIENT_CONTACTS))
        dp.message.register(get_client_notes, StateFilter(Form.AWAITING_CLIENT_NOTES))
        
        # Меню сделок
        dp.message.register(handle_orders_menu, StateFilter(Form.ORDERS_MENU))
        dp.message.register(get_order_name, StateFilter(Form.AWAITING_ORDER_NAME))
        dp.message.register(get_order_client, StateFilter(Form.AWAITING_ORDER_CLIENT))
        dp.message.register(get_order_cost, StateFilter(Form.AWAITING_ORDER_COST))
        
        # Меню операций
        dp.message.register(handle_operations_menu, StateFilter(Form.OPERATIONS_MENU))
        dp.message.register(get_expense_comment, StateFilter(Form.AWAITING_EXPENSE_COMMENT))
        dp.message.register(get_expense_cost, StateFilter(Form.AWAITING_EXPENSE_COST))
        
        # Обработчики инлайн-кнопок
        dp.callback_query.register(income_button_handler, F.data.startswith("income_"))
        dp.callback_query.register(complete_order_button_handler, F.data.startswith("complete_"))
        
        # Обработчик календаря
        dp.callback_query.register(process_calendar_selection, SimpleCalendarCallback.filter(), StateFilter(Form.AWAITING_ORDER_DEADLINE))
        
        # Обработчик ошибок
        dp.errors.register(error_handler)
        
        self.stdout.write(self.style.SUCCESS('Бот на aiogram запущен...'))
        
        # Запуск бота
        asyncio.run(dp.start_polling(bot))
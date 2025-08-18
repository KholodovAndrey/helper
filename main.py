import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# Настройка
load_dotenv()
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("❌ Токен не найден в .env файле!")

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# База данных
conn = sqlite3.connect('finance.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы
cursor.executescript('''
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contact TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    client_id INTEGER,
    amount REAL,
    status TEXT DEFAULT 'Новая',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    deal_id INTEGER,
    amount REAL,
    method TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deal_id) REFERENCES deals(id)
);

CREATE TABLE IF NOT EXISTS finances (
    id INTEGER PRIMARY KEY,
    type TEXT CHECK(type IN ('Доход', 'Расход')),
    amount REAL,
    category TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
''')
conn.commit()

# Состояния
class ClientStates(StatesGroup):
    name = State()
    contact = State()
    notes = State()

class DealStates(StatesGroup):
    name = State()
    client_id = State()
    amount = State()

class PaymentStates(StatesGroup):
    deal_id = State()
    amount = State()
    method = State()

# Клавиатуры
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Сделки"), KeyboardButton(text="👥 Клиенты")],
            [KeyboardButton(text="💰 Платежи"), KeyboardButton(text="📊 Финансы")]
        ],
        resize_keyboard=True
    )

def deals_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая сделка"), KeyboardButton(text="📋 Список сделок")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def clients_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новый клиент"), KeyboardButton(text="📋 Список клиентов")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

# Команды
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "💼 Бот для учета сделок и клиентов\n"
        "Выберите действие:",
        reply_markup=main_kb()
    )

@dp.message(F.text == "🔙 Назад")
async def back(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_kb())

# Клиенты
@dp.message(F.text == "👥 Клиенты")
async def clients_menu(message: types.Message):
    await message.answer("Управление клиентами:", reply_markup=clients_kb())

@dp.message(F.text == "➕ Новый клиент")
async def add_client_start(message: types.Message, state: FSMContext):
    await state.set_state(ClientStates.name)
    await message.answer("Введите имя клиента:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(ClientStates.name)
async def process_client_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ClientStates.contact)
    await message.answer("Введите контактные данные:")

@dp.message(ClientStates.contact)
async def process_client_contact(message: types.Message, state: FSMContext):
    await state.update_data(contact=message.text)
    await state.set_state(ClientStates.notes)
    await message.answer("Добавьте заметки (необязательно):")

@dp.message(ClientStates.notes)
async def process_client_notes(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute(
        "INSERT INTO clients (name, contact, notes) VALUES (?, ?, ?)",
        (data['name'], data['contact'], message.text or "Нет заметок")
    )
    conn.commit()
    await state.clear()
    await message.answer("✅ Клиент добавлен!", reply_markup=main_kb())

@dp.message(F.text == "📋 Список клиентов")
async def list_clients(message: types.Message):
    cursor.execute("SELECT id, name, contact FROM clients")
    clients = cursor.fetchall()
    
    if not clients:
        await message.answer("Клиентов пока нет")
        return
    
    response = "📋 Клиенты:\n\n"
    for client in clients:
        response += f"🆔 {client[0]}\n👤 {client[1]}\n📞 {client[2]}\n\n"
    
    await message.answer(response)

# Сделки
@dp.message(F.text == "📝 Сделки")
async def deals_menu(message: types.Message):
    await message.answer("Управление сделками:", reply_markup=deals_kb())

@dp.message(F.text == "➕ Новая сделка")
async def add_deal_start(message: types.Message, state: FSMContext):
    await state.set_state(DealStates.name)
    await message.answer("Введите название сделки:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(DealStates.name)
async def process_deal_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(DealStates.client_id)
    await message.answer("Введите ID клиента (0 если нет):")

@dp.message(DealStates.client_id)
async def process_deal_client(message: types.Message, state: FSMContext):
    try:
        client_id = int(message.text)
        if client_id != 0:
            cursor.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,))
            if not cursor.fetchone():
                await message.answer("❌ Клиент не найден!")
                return
        
        await state.update_data(client_id=client_id if client_id != 0 else None)
        await state.set_state(DealStates.amount)
        await message.answer("Введите сумму сделки:")
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(DealStates.amount)
async def process_deal_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        
        cursor.execute(
            "INSERT INTO deals (name, client_id, amount) VALUES (?, ?, ?)",
            (data['name'], data['client_id'], amount)
        )
        conn.commit()
        
        await state.clear()
        await message.answer("✅ Сделка добавлена!", reply_markup=main_kb())
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(F.text == "📋 Список сделок")
async def list_deals(message: types.Message):
    cursor.execute('''
    SELECT d.id, d.name, c.name, d.amount, d.status 
    FROM deals d
    LEFT JOIN clients c ON d.client_id = c.id
    ''')
    deals = cursor.fetchall()
    
    if not deals:
        await message.answer("Сделок пока нет")
        return
    
    response = "📊 Сделки:\n\n"
    for deal in deals:
        response += (
            f"🆔 {deal[0]}\n"
            f"📌 {deal[1]}\n"
            f"👤 {deal[2] or 'Без клиента'}\n"
            f"💰 {deal[3]}\n"
            f"🟢 {deal[4]}\n\n"
        )
    
    await message.answer(response)

# Платежи
@dp.message(F.text == "💰 Платежи")
async def payments_menu(message: types.Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💳 Добавить платеж")],
                [KeyboardButton(text="🔙 Назад")]
            ],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "💳 Добавить платеж")
async def add_payment_start(message: types.Message, state: FSMContext):
    await state.set_state(PaymentStates.deal_id)
    await message.answer("Введите ID сделки:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(PaymentStates.deal_id)
async def process_payment_deal(message: types.Message, state: FSMContext):
    try:
        deal_id = int(message.text)
        cursor.execute("SELECT 1 FROM deals WHERE id = ?", (deal_id,))
        if not cursor.fetchone():
            await message.answer("❌ Сделка не найдена!")
            return
        
        await state.update_data(deal_id=deal_id)
        await state.set_state(PaymentStates.amount)
        await message.answer("Введите сумму платежа:")
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(PaymentStates.amount)
async def process_payment_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        await state.set_state(PaymentStates.method)
        await message.answer("Введите способ оплаты:")
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(PaymentStates.method)
async def process_payment_method(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    cursor.execute(
        "INSERT INTO payments (deal_id, amount, method) VALUES (?, ?, ?)",
        (data['deal_id'], data['amount'], message.text)
    )
    conn.commit()
    
    await state.clear()
    await message.answer("✅ Платеж добавлен!", reply_markup=main_kb())

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
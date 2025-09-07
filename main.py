import os
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime

# Импорты aiogram
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импорты Telethon
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,  # Изменено с SessionPasswordNeeded
    PhoneCodeInvalidError        # Изменено с PhoneCodeInvalid
)
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import MessageService

# Импорты для DeepSeek
import aiohttp
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация (замените на свои значения)
BOT_TOKEN = "8218868922:AAED40palWhHPhqcb3NgjdlHUHGty5tY360"  # Получите у @BotFather
API_ID = 13689314                  # Получите на my.telegram.org
API_HASH = "809d211f8457b863286b8a8c58977b1b"    # Получите на my.telegram.org
DEEPSEEK_API_KEY = "sk-b290a4dd2feb43979f19a3602a20de93"  # Получите на platform.deepseek.com

# ID администраторов (замените на свои)
ADMIN_IDS = [7246667404, 987654321]

# Глобальные переменные
user_sessions = {}
active_userbots = {}
user_phones = {}

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

# Класс для управления сессиями пользователей
class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.phone = None
        self.phone_code_hash = None
        self.client = None
        self.is_authenticated = False
        self.session_name = f"sessions/session_{user_id}"
        
        # Создаем папку для сессий, если её нет
        os.makedirs("sessions", exist_ok=True)
    
    async def send_code(self, phone: str):
        """Отправка кода подтверждения на телефон"""
        self.phone = phone
        self.client = TelegramClient(self.session_name, API_ID, API_HASH)
        await self.client.connect()
        
        sent_code = await self.client.send_code_request(phone)
        self.phone_code_hash = sent_code.phone_code_hash
        return True
    
    async def sign_in(self, code: str):
        """Авторизация с кодом из SMS"""
        try:
            await self.client.sign_in(
                phone=self.phone,
                code=code,
                phone_code_hash=self.phone_code_hash
            )
            self.is_authenticated = True
            return True, None
        except SessionPasswordNeeded:
            return False, "password"
        except PhoneCodeInvalid:
            return False, "invalid_code"
        except Exception as e:
            return False, str(e)
    
    async def sign_in_with_password(self, password: str):
        """Авторизация с двухфакторной аутентификацией"""
        try:
            await self.client.sign_in(password=password)
            self.is_authenticated = True
            return True
        except Exception as e:
            return False, str(e)
    
    async def disconnect(self):
        """Отключение клиента"""
        if self.client:
            await self.client.disconnect()
            self.client = None

# Класс для работы с DeepSeek API
class DeepSeekAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
    
    async def generate_response(self, message: str, context: List[Dict] = None) -> str:
        """Генерация ответа с помощью DeepSeek"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Формируем промпт в стиле "Суслика"
        system_prompt = """Ты - Суслик, весёлый и немного грубоватый бот в Telegram-чате.
Тебе не нравится слово "че" - ты всегда исправляешь его на "чо".
Если кто-то использует неправильные формы слов или делает ошибки, ты можешь материться, но в шутливой форме.
Ты уважаешь всех участников чата и часто хвалишь их.
Твой стиль общения: неформальный, дружелюбный, с юмором, иногда с сарказмом.
Отвечай кратко и естественно, как в обычном чате.
Не пиши слишком длинные сообщения.
Всегда отвечай от своего имени."""

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Добавляем контекст, если он есть
        if context:
            messages.extend(context)
        
        # Добавляем текущее сообщение
        messages.append({"role": "user", "content": message})
        
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 150,
            "stream": False
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content'].strip()
                    else:
                        return "Чё-то я туплю... Напиши еще раз, а?"
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return "У меня лапки... Давай попробуем еще раз?"

# Инициализация DeepSeek
deepseek = DeepSeekAPI(DEEPSEEK_API_KEY)

# Обработчики команд для бота-авторизации
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас нет доступа к этому боту!")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔗 Подключить бота", callback_data="connect_bot")
    
    await message.answer(
        "Привет! Я бот для управления Сусликом.\n"
        "Нажми кнопку ниже, чтобы подключить его к твоему аккаунту.",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(F.data == "connect_bot")
async def connect_bot(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Нет доступа!")
        return
    
    await callback.message.answer("Введите номер телефона (в международном формате, например: +79123456789):")
    await state.set_state(AuthStates.waiting_for_phone)
    await callback.answer()

@dp.message(AuthStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    
    # Простая валидация номера
    if not phone.startswith('+') or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer("❌ Неверный формат номера. Попробуйте еще раз (например: +79123456789):")
        return
    
    user_id = message.from_user.id
    
    # Создаем сессию пользователя
    user_session = UserSession(user_id)
    user_sessions[user_id] = user_session
    
    try:
        # Отправляем код
        await user_session.send_code(phone)
        user_phones[user_id] = phone
        
        await message.answer("✅ Код отправлен! Введите код из SMS:")
        await state.set_state(AuthStates.waiting_for_code)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

@dp.message(AuthStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.answer("❌ Сессия не найдена. Начните заново с /start")
        await state.clear()
        return
    
    user_session = user_sessions[user_id]
    
    try:
        success, error = await user_session.sign_in(code)
        
        if success:
            await message.answer("✅ Авторизация успешна! Бот запущен.")
            
            # Запускаем userbot в фоновом режиме
            asyncio.create_task(run_userbot(user_session.client, user_id))
            
            active_userbots[user_id] = user_session
            await state.clear()
            
        elif error == "password":
            await message.answer("🔐 Введите пароль двухфакторной аутентификации:")
            await state.set_state(AuthStates.waiting_for_password)
        else:
            await message.answer(f"❌ Ошибка: {error}. Попробуйте еще раз:")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

@dp.message(AuthStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.answer("❌ Сессия не найдена. Начните заново с /start")
        await state.clear()
        return
    
    user_session = user_sessions[user_id]
    
    try:
        success, error = await user_session.sign_in_with_password(password)
        
        if success:
            await message.answer("✅ Авторизация успешна! Бот запущен.")
            
            # Запускаем userbot в фоновом режиме
            asyncio.create_task(run_userbot(user_session.client, user_id))
            
            active_userbots[user_id] = user_session
            await state.clear()
        else:
            await message.answer(f"❌ Ошибка: {error}. Начните заново с /start")
            await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

# Функция для запуска userbot
async def run_userbot(client, user_id):
    """Запуск userbot для прослушивания сообщений"""
    @client.on(events.NewMessage)
    async def handler(event):
        # Игнорируем служебные сообщения и собственные сообщения
        if isinstance(event.message, MessageService) or event.message.out:
            return
        
        # Проверяем команду .ss для активации
        if event.message.text and event.message.text.startswith('.ss'):
            # Активируем бота в этом чате
            chat_id = event.chat_id
            if user_id not in active_chats:
                active_chats[user_id] = set()
            active_chats[user_id].add(chat_id)
            
            await event.reply("Суслик активирован! 🐹")
            return
        
        # Проверяем, активирован ли бот в этом чате
        if user_id in active_chats and event.chat_id in active_chats[user_id]:
            # Исправляем "че" на "чо"
            message_text = event.message.text
            if message_text:
                if " че " in message_text.lower() or message_text.lower().startswith("че "):
                    corrected_text = message_text.lower().replace(" че ", " чо ").replace("че ", "чо ")
                    await event.reply(f"Исправляю: {corrected_text}")
                    return
            
            # Генерируем ответ с помощью DeepSeek
            response = await deepseek.generate_response(message_text)
            
            # Отправляем ответ
            await event.reply(response)
    
    # Запускаем клиент
    await client.start()
    await client.run_until_disconnected()

# Глобальные переменные для активных чатов
active_chats = {}

# Запуск бота
async def main():
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

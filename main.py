import os
import asyncio
import logging
import random
import aiohttp
import json

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.types import MessageService
from telethon import events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8218868922:AAED40palWhHPhqcb3NgjdlHUHGty5tY360"
API_ID = 13689314
API_HASH = "809d211f8457b863286b8a8c58977b1b"

ADMIN_IDS = [7246667404]

user_sessions = {}
active_userbots = {}
user_phones = {}
active_chats = set()

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

class NeuralNetworkAPI:
    def __init__(self):
        # Используем более стабильные API endpoints
        self.api_endpoints = [
            "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium",
            "https://api-inference.huggingface.co/models/tinkoff-ai/ruDialoGPT-medium",
            "https://api-inference.huggingface.co/models/microsoft/DialoGPT-small",
            "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-ru-en",
        ]
        self.current_endpoint_index = 0
        self.fallback_responses = [
            "Чо? Я тут! 🐹",
            "Ага, понял... 🤔",
            "Интересно! 🧐",
            "Ну и чо? 😏",
            "Продолжайте, я слушаю! 👂",
            "Мда... 🤨",
            "Чо-то скучновато... 🥱",
            "Ахаха, хорош! 😄",
            "Ну ты даешь! 😅",
            "Чо-то я не понял... Объясни? 🤷"
        ]
        
    def get_current_endpoint(self):
        return self.api_endpoints[self.current_endpoint_index]
    
    def switch_endpoint(self):
        self.current_endpoint_index = (self.current_endpoint_index + 1) % len(self.api_endpoints)
        logger.info(f"Переключились на endpoint: {self.get_current_endpoint()}")
    
    async def generate_response(self, message: str, chat_id: str, username: str = None) -> str:
        try:
            api_url = self.get_current_endpoint()
            
            # Упрощенный промпт для лучшей работы
            prompt = f"""Ты - Суслик, Telegram бот. Отвечай кратко и естественно.

Человек: {message}
Суслик:"""
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 60,
                    "temperature": 0.8,
                    "do_sample": True,
                    "top_p": 0.9,
                    "return_full_text": False
                }
            }
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        api_url, 
                        json=payload, 
                        timeout=5  # Уменьшаем таймаут
                    ) as response:
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            if isinstance(data, list) and len(data) > 0:
                                generated_text = data[0].get('generated_text', '')
                                
                                if generated_text:
                                    # Очищаем ответ
                                    response_text = generated_text.replace(prompt, '').strip()
                                    
                                    if response_text and len(response_text) > 2:
                                        # Исправляем "че" на "чо"
                                        response_text = response_text.replace(' че ', ' чо ').replace('Че ', 'Чо ')
                                        return response_text
                        
                        # Если статус не 200, пробуем другой endpoint
                        self.switch_endpoint()
                        return random.choice(self.fallback_responses)
                        
                except asyncio.TimeoutError:
                    logger.warning("Timeout при запросе к API")
                    self.switch_endpoint()
                    return random.choice(self.fallback_responses)
                    
        except Exception as e:
            logger.error(f"API error: {e}")
            self.switch_endpoint()
            return random.choice(self.fallback_responses)

# Инициализируем нейросеть
neural_api = NeuralNetworkAPI()

class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.phone = None
        self.phone_code_hash = None
        self.client = None
        self.is_authenticated = False
        self.session_name = f"sessions/session_{user_id}"
        
        os.makedirs("sessions", exist_ok=True)
    
    async def send_code(self, phone: str):
        self.phone = phone
        self.client = TelegramClient(self.session_name, API_ID, API_HASH)
        await self.client.connect()
        
        sent_code = await self.client.send_code_request(phone)
        self.phone_code_hash = sent_code.phone_code_hash
        return True
    
    async def sign_in(self, code: str):
        try:
            await self.client.sign_in(
                phone=self.phone,
                code=code,
                phone_code_hash=self.phone_code_hash
            )
            self.is_authenticated = True
            return True, None
        except SessionPasswordNeededError:
            return False, "password"
        except PhoneCodeInvalidError:
            return False, "invalid_code"
        except Exception as e:
            return False, str(e)
    
    async def sign_in_with_password(self, password: str):
        try:
            await self.client.sign_in(password=password)
            self.is_authenticated = True
            return True
        except Exception as e:
            return False, str(e)
    
    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None

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
    
    if not phone.startswith('+') or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer("❌ Неверный формат номера. Попробуйте еще раз (например: +79123456789):")
        return
    
    user_id = message.from_user.id
    
    user_session = UserSession(user_id)
    user_sessions[user_id] = user_session
    
    try:
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
            
            asyncio.create_task(run_userbot(user_session.client, user_id))
            
            active_userbots[user_id] = user_session
            await state.clear()
        else:
            await message.answer(f"❌ Ошибка: {error}. Начните заново с /start")
            await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

async def run_userbot(client, user_id):
    @client.on(events.NewMessage)
    async def handler(event):
        if isinstance(event.message, MessageService) or event.message.out:
            return
        
        message_text = event.message.text or ""
        chat_id = event.chat_id
        
        # Активация по команде .ss
        if message_text.startswith('.ss'):
            active_chats.add(chat_id)
            await event.reply("✅ Суслик активирован для всего чата! 🐹")
            return
        
        # Деактивация
        if message_text.startswith('.stop'):
            if chat_id in active_chats:
                active_chats.remove(chat_id)
                await event.reply("❌ Суслик деактивирован 🐹")
            return
        
        # Проверяем, активирован ли бот
        if chat_id not in active_chats:
            return
        
        # Исправляем "че" на "чо"
        if " че " in message_text.lower() or message_text.lower().startswith("че "):
            corrected_text = message_text.lower().replace(" че ", " чо ").replace("че ", "чо ")
            await event.reply(f"🤬 Исправляю: {corrected_text}")
            return
        
        # Генерируем ответ через нейросеть
        response = await neural_api.generate_response(message_text, str(chat_id))
        await event.reply(response)
    
    try:
        await client.start()
        logger.info(f"Userbot для пользователя {user_id} запущен")
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"Ошибка в userbot: {e}")

async def main():
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

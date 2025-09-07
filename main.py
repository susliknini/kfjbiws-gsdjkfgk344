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
active_chats = {}

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

class HuggingFaceAPI:
    def __init__(self):
        self.models = [
            "microsoft/DialoGPT-medium",
            "tinkoff-ai/ruDialoGPT-medium", 
            "microsoft/DialoGPT-small"
        ]
        self.current_model_index = 0
        self.fallback_responses = {
            "че": [
                "Опять это 'че'! Говори 'чо', будь человеком! 😠",
                'Чё? "Чо" надо говорить! 🤬',
                "Исправляю: чо... Всегда это 'че' достало! 😤",
                "Че? Серьезно? Говори 'чо', балбес! 🤦‍♂️"
            ],
            "суслик": [
                "Чо надо? Я занят! 🐹",
                "Суслик на связи! Чо там? 😎",
                "Меня звали? Я тут! 🐭",
                "А? Кто? Я? Ну чо? 🤔",
                "Да-да, я здесь, чо хотел? 🦫"
            ],
            "привет": [
                "Ну привет, чо 😏",
                "Здарова, чо как? 👋", 
                "Приветствую, смертный! 😈",
                "О, привет! Чо нового? 🐿️"
            ],
            "как дела": [
                "Да нормально, чо ты спрашиваешь? А у тебя? 🐹",
                "Пока не сдох, чо 😅",
                "Лучше всех, чо еще! 🎉",
                "Отлично! Чо у тебя? 🌟"
            ],
            "default": [
                "Интересно... 🤔",
                "Ну это ты загнул! 😂",
                "Чо? Серьезно? 😲",
                "Я бы поспорил, но лень... 😴",
                "Хм, а ты не дурак! 👍",
                "Это пипец как интересно... 🧐",
                "Чо-то я не понял... Объясни? 🤷",
                "Ахаха, хорош! 😄",
                "Ну ты даешь! 😅",
                "Чо-то скучно... Развлеки меня! 🎭",
                "Мда... 🤨",
                "Ну и чо? 🐿️",
                "Продолжай, я слушаю... 👂",
                "Блин, я проголодался... 🥜",
                "Чо-то устал я сегодня... 😪"
            ]
        }
    
    def get_current_model(self):
        return self.models[self.current_model_index]
    
    def switch_model(self):
        self.current_model_index = (self.current_model_index + 1) % len(self.models)
        logger.info(f"Переключились на модель: {self.get_current_model()}")
    
    async def generate_response(self, message: str) -> str:
        message_lower = message.lower()
        
        # Приоритетные ответы
        if " че " in message_lower or message_lower.startswith("че "):
            return random.choice(self.fallback_responses["че"])
        
        if "суслик" in message_lower:
            return random.choice(self.fallback_responses["суслик"])
        
        if "привет" in message_lower:
            return random.choice(self.fallback_responses["привет"])
        
        if "как дела" in message_lower or "как ты" in message_lower:
            return random.choice(self.fallback_responses["как дела"])
        
        # Пробуем получить ответ от Hugging Face API
        try:
            api_url = f"https://api-inference.huggingface.co/models/{self.get_current_model()}"
            
            # Формируем промпт в стиле Суслика
            prompt = f"""Ты - Суслик, весёлый и немного грубоватый бот в Telegram-чате.
Тебе не нравится слово "че" - ты всегда исправляешь его на "чо".
Твой стиль общения: неформальный, дружелюбный, с юмором, иногда с сарказмом.
Отвечай кратко и естественно, как в обычном чате.

Человек: {message}
Суслик:"""
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 80,
                    "temperature": 0.9,
                    "do_sample": True,
                    "top_p": 0.9,
                    "repetition_penalty": 1.1,
                    "return_full_text": False
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, 
                    json=payload, 
                    timeout=8
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        if isinstance(data, list) and len(data) > 0:
                            generated_text = data[0].get('generated_text', '')
                            
                            # Очищаем ответ
                            if generated_text:
                                # Убираем повторения промпта
                                response_text = generated_text.replace(prompt, '').strip()
                                
                                # Убираем лишние символы
                                response_text = response_text.split('\n')[0].split('Человек:')[0].strip()
                                
                                if response_text and len(response_text) > 3:
                                    # Исправляем "че" на "чо" в ответе
                                    response_text = response_text.replace(' че ', ' чо ').replace('Че ', 'Чо ')
                                    return response_text
                    
                    # Если что-то пошло не так, пробуем другую модель
                    self.switch_model()
                    return random.choice(self.fallback_responses["default"])
                    
        except Exception as e:
            logger.error(f"HuggingFace API error: {e}")
            self.switch_model()
            return random.choice(self.fallback_responses["default"])

# Инициализируем генератор ответов
response_generator = HuggingFaceAPI()

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
            if user_id not in active_chats:
                active_chats[user_id] = set()
            active_chats[user_id].add(chat_id)
            await event.reply("Суслик активирован! 🐹")
            return
        
        # Проверяем, активирован ли бот в этом чате
        if user_id not in active_chats or chat_id not in active_chats[user_id]:
            return
        
        # Исправляем "че" на "чо"
        if " че " in message_text.lower() or message_text.lower().startswith("че "):
            corrected_text = message_text.lower().replace(" че ", " чо ").replace("че ", "чо ")
            await event.reply(f"Исправляю: {corrected_text}")
            return
        
        # Отвечаем если упоминают суслика (всегда)
        if "суслик" in message_text.lower():
            response = await response_generator.generate_response(message_text)
            await event.reply(response)
            return
        
        # Случайные ответы (каждое 3-7 сообщение)
        if random.randint(1, 5) == 1:
            response = await response_generator.generate_response(message_text)
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

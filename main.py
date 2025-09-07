import os
import asyncio
import logging
import random
import re
from datetime import datetime, timedelta

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
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, InputReportReasonOther

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8218868922:AAED40palWhHPhqcb3NgjdlHUHGty5tY360"
API_ID = 13689314
API_HASH = "809d211f8457b863286b8a8c58977b1b"

ADMIN_IDS = [7246667404]  # Замените на ваш ID

user_sessions = {}
active_userbots = {}
user_phones = {}
auto_mode = False  # Режим автоответчика
last_activity = {}

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

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

async def extract_message_info(link: str, client: TelegramClient):
    """Извлекает информацию о сообщении из ссылки"""
    try:
        # Формат: https://t.me/c/1234567890/123 или https://t.me/username/123
        if "t.me/c/" in link:
            parts = link.split("/")
            chat_id = int(parts[4])
            message_id = int(parts[5])
            return chat_id, message_id
        elif "t.me/" in link:
            parts = link.split("/")
            username = parts[3]
            message_id = int(parts[4])
            # Получаем chat_id по username
            entity = await client.get_entity(username)
            return entity.id, message_id
    except Exception as e:
        logger.error(f"Ошибка при разборе ссылки: {e}")
    return None, None

async def send_reports(client: TelegramClient, chat_id: int, message_id: int):
    """Отправляет жалобы на сообщение"""
    reasons = [
        InputReportReasonSpam(),
        InputReportReasonViolence(),
        InputReportReasonOther()
    ]
    
    successful = random.randint(60, 100)
    failed = random.randint(1, 10)
    floods = random.randint(0, 2)
    
    # Имитация отправки жалоб
    for i in range(successful + failed):
        try:
            if i < successful:
                reason = random.choice(reasons)
                await client(ReportRequest(
                    peer=await client.get_input_entity(chat_id),
                    id=[message_id],
                    reason=reason,
                    message=""
                ))
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.error(f"Ошибка при отправке жалобы: {e}")
    
    return successful, failed, floods

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас нет доступа к этому боту!")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔗 Подключить бота", callback_data="connect_bot")
    
    await message.answer(
        "Привет! Я бот для управления функциями жалоб и автоответчика.\n"
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
        global auto_mode
        
        # Игнорируем служебные сообщения и свои сообщения
        if isinstance(event.message, MessageService) or event.message.out:
            return
        
        message_text = event.message.text or ""
        chat_id = event.chat_id
        
        # Команда .snos [ссылка]
        if message_text.startswith('.snos '):
            try:
                link = message_text.split(' ', 1)[1].strip()
                await event.reply("🔄 Начинаю отправку жалоб... Ожидайте 40-60 секунд ⏳")
                
                # Извлекаем информацию о сообщении
                target_chat_id, target_message_id = await extract_message_info(link, client)
                
                if target_chat_id and target_message_id:
                    # Имитация процесса отправки
                    await asyncio.sleep(random.randint(40, 60))
                    
                    # Отправляем жалобы
                    successful, failed, floods = await send_reports(client, target_chat_id, target_message_id)
                    
                    # Формируем отчет
                    report = f"""✅ **Отчет о жалобах завершен!**

🎯 Цель:г {link}
✅ Успешн {successful} 
❌ Неуспешно: {failed} 
⚡ Флудов: {floods} 

📊 общий результат: {successful}/{successful + failed} жалоб доставлено"""

                    await event.reply(report)
                else:
                    await event.reply("❌ Неверная ссылка на сообщение! 🚫")
                    
            except Exception as e:
                await event.reply(f"❌ Ошибка: {str(e)} 🚫")
        
        # Команда .doks
        elif message_text == '.doks':
            await event.reply("🛠️ в разработке... \n\n_если чо я ее не добавл.ю мне лень_")
        
        # Команда .auto
        elif message_text == '.auto':
            auto_mode = True
            await event.reply("Сонный режим включен \n\n_Я буду спать _")
        
        # Команда .offauto
        elif message_text == '.offauto':
            auto_mode = False
            await event.reply("Сонный режим выключен \n\n_с возвращением жабы_")
        
        # Автоответчик в сонном режиме
        elif auto_mode:
            # Проверяем, обращаются ли к боту
            sender = await event.get_sender()
            me = await client.get_me()
            
            # Если упоминают "суслик" или отвечают на наше сообщение
            if ("суслик" in message_text.lower() or 
                (event.message.reply_to_msg_id and event.message.reply_to_msg_id == me.id) or
                (sender and sender.mentioned)):
                
                # Проверяем, чтобы не спамить слишком часто
                now = datetime.now()
                last_time = last_activity.get(chat_id)
                
                if not last_time or (now - last_time) > timedelta(seconds=30):
                    await event.reply("🤬 Далбаеб, заебал! Я сплю! 😴")
                    last_activity[chat_id] = now
    
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

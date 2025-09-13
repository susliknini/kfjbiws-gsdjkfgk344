import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode

# Настройки бота
BOT_TOKEN = "8378889437:AAGRVHAnH690fDmanXxQdme837Z0B6jiR9g"
ADMIN_IDS = [8312135656, 1637959612]  # Замените на реальные ID админов
INVITE_LINK = "потом поставлю"  # Ваша ссылка для вступления

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Callback data классы
class FormCallback:
    APPLY = "apply"
    CASTE = "caste_"
    ADMIN_ACCEPT = "admin_accept"
    ADMIN_REJECT = "admin_reject"
    CANCEL = "cancel"

# Класс состояний FSM
class Form(StatesGroup):
    waiting_nickname = State()
    waiting_experience = State()
    waiting_year = State()
    waiting_caste = State()

# Inline клавиатуры
def get_start_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="падать заявку", callback_data=FormCallback.APPLY)
    builder.button(text="отмена", callback_data=FormCallback.CANCEL)
    builder.adjust(1)
    return builder.as_markup()

def get_caste_keyboard():
    builder = InlineKeyboardBuilder()
    castes = [
        "Снос", 
        "Докс", 
        "Осинт", 
        "Сват", 
        "Троль", 
        "Другое"
    ]
    for caste in castes:
        builder.button(text=caste, callback_data=f"{FormCallback.CASTE}{caste.split()[1]}")
    builder.button(text="🔙 Назад 🔙", callback_data=FormCallback.CANCEL)
    builder.adjust(2)
    return builder.as_markup()

def get_admin_keyboard(user_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять ✅", callback_data=f"{FormCallback.ADMIN_ACCEPT}_{user_id}")
    builder.button(text="❌ Отклонить ❌", callback_data=f"{FormCallback.ADMIN_REJECT}_{user_id}")
    return builder.as_markup()

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        photo = InputFile("start.jpg")
        await message.answer_photo(
            photo=photo,
            caption="Привет!\n\nПодай заявку в легендарный клан **Легион Защиты**!\n\nПрисоединяйся к лучшим",
            reply_markup=get_start_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    except FileNotFoundError:
        await message.answer(
            "Привета\n\nПодай заявку в легендарный клан **Легион Защиты**\n\nПрисоединяйся к лучшим",
            reply_markup=get_start_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

# Обработчик отмены
@router.callback_query(F.data == FormCallback.CANCEL)
async def process_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено ❌\n\n🔄 Используйте /start чтобы начать заново 🔄",
        reply_markup=None
    )
    await callback.answer("🚫 Отменено 🚫")

# Обработчик кнопки "Подать заявку"
@router.callback_query(F.data == FormCallback.APPLY)
async def process_apply(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_nickname)
    await callback.message.edit_text(
        "Введите вашу основную лику в км: \n\n📛 Пример: далбаеб228",
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода ника
@router.message(Form.waiting_nickname)
async def process_nickname(message: Message, state: FSMContext):
    if len(message.text) > 50:
        await message.answer("❌ Слишком болшой! !!Максимум 50 символов ❌")
        return
        
    await state.update_data(nickname=message.text)
    await state.set_state(Form.waiting_experience)
    await message.answer(
        "📖 Теперь подробно опишите ваш опыт работы в этой сфере: \n\n"
        "💼 Расскажите о ваших навыках и достижениях 💼\n"
        "⭐ Чем вы можете быть полезны клану? ⭐"
    )

# Обработчик ввода опыта
@router.message(Form.waiting_experience)
async def process_experience(message: Message, state: FSMContext):
    if len(message.text) < 10:
        await message.answer("❌ Слишком короткое описание! Расскажите подробнее ❌")
        return
        
    await state.update_data(experience=message.text)
    await state.set_state(Form.waiting_year)
    await message.answer(
        "📅 С какого года вы находитесь в КМ? \n\n"
        "🗓️ Пример: 2020, 2018, 2022 🗓️\n"
        "указывай правильно что бы я не ебался с этим"
    )

# Обработчик ввода года
@router.message(Form.waiting_year)
async def process_year(message: Message, state: FSMContext):
    await state.update_data(year=message.text)
    await state.set_state(Form.waiting_caste)
    await message.answer(
        "🎯 Выберите вашу касту: \n\n"
        "🏷️ Укажите основное направление деятельности в км 🏷️",
        reply_markup=get_caste_keyboard()
    )

# Обработчик выбора касты
@router.callback_query(F.data.startswith(FormCallback.CASTE))
async def process_caste(callback: CallbackQuery, state: FSMContext):
    caste = callback.data.replace(FormCallback.CASTE, "")
    await state.update_data(caste=caste)
    
    # Получаем все данные из FSM
    data = await state.get_data()
    
    # Формируем сообщение для админов
    admin_message = (
        f"🎯 **Новая заявка в Легион Защиты!** 🎯\n\n"
        f"👤 **Ник:** {data['nickname']}\n"
        f"📖 **Опыт:** {data['experience']}\n"
        f"📅 **В КМ с:** {data['year']}\n"
        f"🏷️ **Каста:** {caste}\n\n"
        f"🆔 **ID пользователя:** {callback.from_user.id}\n"
        f"👁️ **Username:** @{callback.from_user.username if callback.from_user.username else 'Нет'}"
    )
    
    # Отправляем всем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                admin_message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_keyboard(callback.from_user.id)
            )
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")
    
    await callback.message.edit_text(
        "✅ **Заявка отправлена!** ✅\n\n"
        "⏳ Ожидайте рассмотрения вашей заявки администрацией ⏳\n"
        "📧 Вы получите уведомление о решении 📧",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.clear()
    await callback.answer(f"🎉 Каста выбрана: {caste} 🎉")

# Обработчик принятия заявки админом
@router.callback_query(F.data.startswith(FormCallback.ADMIN_ACCEPT))
async def process_admin_accept(callback: CallbackQuery):
    user_id = int(callback.data.split('_')[-1])
    
    try:
        await bot.send_message(
            user_id,
            "🎉 **ваша заявка принята!** 🎉\n\n"
            "🛡️ для начала пройди првоерку 🛡️\n\n"
            f"🔗 проверка по ссылке: {INVITE_LINK}\n"
            "⚔️ для практики и обучения ⚔️\n\n"
            "удачи",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.message.edit_text(
            f"✅ **Заявка принята!** ✅\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"📧 Уведомление отправлено 📧",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ **Ошибка отправки уведомления!** ❌\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"⚠️ Возможно, пользователь заблокировал бота ⚠️",
            parse_mode=ParseMode.MARKDOWN
        )
    
    await callback.answer("✅ Заявка принята ✅")

# Обработчик отклонения заявки админом
@router.callback_query(F.data.startswith(FormCallback.ADMIN_REJECT))
async def process_admin_reject(callback: CallbackQuery):
    user_id = int(callback.data.split('_')[-1])
    
    try:
        await bot.send_message(
            user_id,
            "❌ **Ваша заявка отклонена.** ❌\n\n"
            "😔 К сожалению, ваша заявка не была одобрена.\n"
            "📋 Возможно, не хватило опыта или информации.\n\n"
            "🔄 Вы можете подать заявку снова через некоторое время 🔄\n"
            "💪 Улучшите свои навыки и попробуйте снова! 💪",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.message.edit_text(
            f"❌ **Заявка отклонена** ❌\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"📧 Уведомление отправлено 📧",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ **Заявка отклонена** ❌\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"⚠️ Но не удалось отправить уведомление пользователю ⚠️",
            parse_mode=ParseMode.MARKDOWN
        )
    
    await callback.answer("❌ Заявка отклонена ❌")

# Обработчик любых сообщений не в FSM
@router.message(StateFilter(None))
async def handle_other_messages(message: Message):
    await message.answer(
        "🤖 **Легион Защиты Бот** 🤖\n\n"
        "🛡️ Для подачи заявки используйте команду /start 🛡️\n\n"
        "⚔️ Присоединяйся к легендарному клану! ⚔️",
        parse_mode=ParseMode.MARKDOWN
    )

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

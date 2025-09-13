import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode

# Настройки бота
BOT_TOKEN = "8378889437:AAGRVHAnH690fDmanXxQdme837Z0B6jiR9g"
ADMIN_IDS = [8312135656, 1637959612]
INVITE_LINK = "потом поставлю"

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
    builder.button(text="Подать заявку", callback_data=FormCallback.APPLY)
    builder.button(text="Отмена", callback_data=FormCallback.CANCEL)
    builder.adjust(1)
    return builder.as_markup()

def get_caste_keyboard():
    builder = InlineKeyboardBuilder()
    castes = ["Снос", "Докс", "Осинт", "Сват", "Троль", "Другое"]
    for caste in castes:
        builder.button(text=caste, callback_data=f"{FormCallback.CASTE}{caste}")
    builder.button(text="Назад", callback_data=FormCallback.CANCEL)
    builder.adjust(2)
    return builder.as_markup()

def get_admin_keyboard(user_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="Принять", callback_data=f"{FormCallback.ADMIN_ACCEPT}_{user_id}")
    builder.button(text="Отклонить", callback_data=f"{FormCallback.ADMIN_REJECT}_{user_id}")
    return builder.as_markup()

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        # Исправлено: используем FSInputFile вместо InputFile
        photo = FSInputFile("start.jpg")
        await message.answer_photo(
            photo=photo,
            caption="Привет! Подай заявку в легендарный клан Легион Защиты",
            reply_markup=get_start_keyboard()
        )
    except FileNotFoundError:
        await message.answer(
            "Привет! Подай заявку в легендарный клан Легион Защиты",
            reply_markup=get_start_keyboard()
        )

# Обработчик отмены
@router.callback_query(F.data == FormCallback.CANCEL)
async def process_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Действие отменено. Используйте /start чтобы начать заново",
        reply_markup=None
    )
    await callback.answer("Отменено")

# Обработчик кнопки "Подать заявку"
@router.callback_query(F.data == FormCallback.APPLY)
async def process_apply(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_nickname)
    await callback.message.edit_text(
        "Введите вашу основную лику в км: Пример: далбаеб228",
        reply_markup=None
    )
    await callback.answer()

# Обработчик ввода ника
@router.message(Form.waiting_nickname)
async def process_nickname(message: Message, state: FSMContext):
    if len(message.text) > 50:
        await message.answer("Слишком большой! Максимум 50 символов")
        return
        
    await state.update_data(nickname=message.text)
    await state.set_state(Form.waiting_experience)
    await message.answer("Теперь подробно опишите ваш опыт работы в этой сфере:")

# Обработчик ввода опыта
@router.message(Form.waiting_experience)
async def process_experience(message: Message, state: FSMContext):
    if len(message.text) < 10:
        await message.answer("Слишком короткое описание! Расскажите подробнее")
        return
        
    await state.update_data(experience=message.text)
    await state.set_state(Form.waiting_year)
    await message.answer("С какого года вы находитесь в КМ? Пример: 2020, 2018, 2022")

# Обработчик ввода года
@router.message(Form.waiting_year)
async def process_year(message: Message, state: FSMContext):
    await state.update_data(year=message.text)
    await state.set_state(Form.waiting_caste)
    await message.answer(
        "Выберите вашу касту:",
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
        f"Новая заявка в Легион Защиты!\n\n"
        f"Ник: {data['nickname']}\n"
        f"Опыт: {data['experience']}\n"
        f"В КМ с: {data['year']}\n"
        f"Каста: {caste}\n\n"
        f"ID пользователя: {callback.from_user.id}\n"
        f"Username: @{callback.from_user.username if callback.from_user.username else 'Нет'}"
    )
    
    # Отправляем всем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                admin_message,
                reply_markup=get_admin_keyboard(callback.from_user.id)
            )
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")
    
    await callback.message.edit_text(
        "Заявка отправлена! Ожидайте рассмотрения вашей заявки администрацией"
    )
    await state.clear()
    await callback.answer(f"Каста выбрана: {caste}")

# Обработчик принятия заявки админом
@router.callback_query(F.data.startswith(FormCallback.ADMIN_ACCEPT))
async def process_admin_accept(callback: CallbackQuery):
    user_id = int(callback.data.split('_')[-1])
    
    try:
        await bot.send_message(
            user_id,
            f"Ваша заявка принята! Для начала пройди проверку по ссылке: {INVITE_LINK} для практики и обучения. Удачи!"
        )
        await callback.message.edit_text(
            f"Заявка принята! Пользователь: {user_id}, уведомление отправлено"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"Ошибка отправки уведомления! Пользователь: {user_id}, возможно заблокировал бота"
        )
    
    await callback.answer("Заявка принята")

# Обработчик отклонения заявки админом
@router.callback_query(F.data.startswith(FormCallback.ADMIN_REJECT))
async def process_admin_reject(callback: CallbackQuery):
    user_id = int(callback.data.split('_')[-1])
    
    try:
        await bot.send_message(
            user_id,
            "Ваша заявка отклонена. К сожалению, ваша заявка не была одобрена. Вы можете подать заявку снова через некоторое время"
        )
        await callback.message.edit_text(
            f"Заявка отклонена. Пользователь: {user_id}, уведомление отправлено"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"Заявка отклонена. Пользователь: {user_id}, но не удалось отправить уведомление"
        )
    
    await callback.answer("Заявка отклонена")

# Обработчик любых сообщений не в FSM
@router.message(StateFilter(None))
async def handle_other_messages(message: Message):
    await message.answer("Для подачи заявки используйте команду /start")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

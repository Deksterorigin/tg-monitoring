from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db_manager
from bot.keyboards.inline import get_admins_keyboard, get_back_keyboard
from bot.filters.admin_filter import IsAdminFilter
from config import settings

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class AdminStates(StatesGroup):
    waiting_for_add = State()
    waiting_for_remove = State()

async def get_admins_list_text() -> str:
    """Формирует список ID администраторов."""
    admins = await db_manager.get_admins()
    text = "👥 <b>Список администраторов:</b>\n\n"
    for idx, admin_id in enumerate(admins, 1):
        is_main = " (Главный)" if admin_id == settings.FIRST_ADMIN_ID else ""
        text += f"{idx}. <code>{admin_id}</code>{is_main}\n"
    return text

@router.callback_query(F.data == "menu_admins")
async def show_admins_menu(callback: CallbackQuery):
    """Показывает меню управления администраторами."""
    list_text = await get_admins_list_text()
    await callback.message.edit_text(
        list_text,
        parse_mode="HTML",
        reply_markup=get_admins_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "add_admin_prompt")
async def add_admin_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос Telegram ID нового администратора."""
    await state.set_state(AdminStates.waiting_for_add)
    await callback.message.edit_text(
        "📝 <b>Введите Telegram ID нового администратора:</b>\n"
        "ID должен состоять только из цифр.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_admins")
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_add)
async def process_add_admin(message: Message, state: FSMContext):
    """Добавление администратора в БД."""
    text = message.text.strip()
    try:
        admin_id = int(text)
        success = await db_manager.add_admin(admin_id)
        
        if success:
            await state.clear()
            await message.answer(
                f"✅ Администратор <code>{admin_id}</code> успешно добавлен!",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("menu_admins")
            )
        else:
            await message.answer(
                f"❌ Администратор с ID <code>{admin_id}</code> уже существует или произошла ошибка.",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("menu_admins")
            )
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b> Введите корректный числовой Telegram ID.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_admins")
        )

@router.callback_query(F.data == "remove_admin_prompt")
async def remove_admin_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос Telegram ID для удаления."""
    await state.set_state(AdminStates.waiting_for_remove)
    await callback.message.edit_text(
        "📝 <b>Введите Telegram ID администратора, которого нужно удалить:</b>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_admins")
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_remove)
async def process_remove_admin(message: Message, state: FSMContext):
    """Удаление администратора из БД."""
    text = message.text.strip()
    try:
        admin_id = int(text)
        
        if admin_id == settings.FIRST_ADMIN_ID:
            await message.answer(
                "❌ Нельзя удалить главного администратора!",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("menu_admins")
            )
            return

        success = await db_manager.remove_admin(admin_id)
        if success:
            await state.clear()
            await message.answer(
                f"✅ Администратор <code>{admin_id}</code> успешно удален.",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("menu_admins")
            )
        else:
            await message.answer(
                f"❌ Не удалось найти или удалить администратора с ID <code>{admin_id}</code>.",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("menu_admins")
            )
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b> Введите корректный числовой Telegram ID.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_admins")
        )

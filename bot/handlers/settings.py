from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db_manager
from bot.keyboards.inline import get_settings_keyboard, get_back_keyboard
from bot.filters.admin_filter import IsAdminFilter

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class SettingsStates(StatesGroup):
    waiting_for_price = State()
    waiting_for_keywords = State()

@router.callback_query(F.data == "menu_settings")
async def show_settings_menu(callback: CallbackQuery):
    """Показывает меню настроек поиска."""
    max_price = await db_manager.get_setting("max_price_usd", "10.0")
    keywords = await db_manager.get_setting("keywords", "Не заданы")
    
    text = (
        f"⚙️ <b>Настройки поиска подписок</b>\n\n"
        f"💵 Текущая максимальная цена: <code>{max_price} $</code>\n"
        f"🔍 Ключевые слова: <code>{keywords}</code>\n\n"
        f"Выберите пункт меню для изменения:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard())
    await callback.answer()

@router.callback_query(F.data == "set_max_price")
async def set_max_price_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод максимальной цены."""
    await state.set_state(SettingsStates.waiting_for_price)
    await callback.message.edit_text(
        "💵 <b>Введите новую максимальную цену в долларах ($):</b>\n"
        "Например: <code>15</code> или <code>7.5</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_price)
async def process_max_price(message: Message, state: FSMContext):
    """Сохранение новой максимальной цены."""
    text = message.text.replace(",", ".").strip()
    try:
        price = float(text)
        if price <= 0:
            raise ValueError()
        
        await db_manager.set_setting("max_price_usd", str(price))
        await state.clear()
        
        await message.answer(
            f"✅ Максимальная цена успешно изменена на <b>{price} $</b>!",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b> Введите корректное положительное число.\n"
            "Пример: <code>10.5</code>",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )

@router.callback_query(F.data == "set_keywords")
async def set_keywords_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод ключевых слов."""
    await state.set_state(SettingsStates.waiting_for_keywords)
    current_keywords = await db_manager.get_setting("keywords", "")
    await callback.message.edit_text(
        f"🔍 <b>Введите ключевые слова через запятую:</b>\n\n"
        f"Текущие: <code>{current_keywords}</code>\n\n"
        f"Пример: <code>ChatGPT, Claude, Midjourney, Perplexity</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_keywords)
async def process_keywords(message: Message, state: FSMContext):
    """Сохранение новых ключевых слов."""
    keywords_raw = message.text.strip()
    # Чистим пробелы вокруг слов
    keywords = ",".join([k.strip() for k in keywords_raw.split(",") if k.strip()])
    
    if not keywords:
        await message.answer(
            "❌ <b>Ошибка!</b> Список ключевых слов не может быть пустым.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return

    await db_manager.set_setting("keywords", keywords)
    await state.clear()
    
    await message.answer(
        f"✅ Ключевые слова успешно обновлены:\n<code>{keywords}</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )

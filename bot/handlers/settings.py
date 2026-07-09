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
    waiting_for_min_price = State()
    waiting_for_price = State()
    waiting_for_keywords = State()
    waiting_for_minus_words = State()
    waiting_for_min_reviews = State()
    waiting_for_dnd_start = State()
    waiting_for_dnd_end = State()

@router.callback_query(F.data == "menu_settings")
async def show_settings_menu(callback: CallbackQuery, state: FSMContext = None):
    """Показывает меню настроек поиска."""
    if state:
        await state.clear()
    min_price = await db_manager.get_setting("min_price_usd", "0.0")
    max_price = await db_manager.get_setting("max_price_usd", "10.0")
    min_reviews = await db_manager.get_setting("min_reviews", "10")
    keywords = await db_manager.get_setting("keywords", "Не заданы")
    minus_words = await db_manager.get_setting("minus_words", "")
    minus_display = minus_words if minus_words else "Нет"
    
    text = (
        f"⚙️ <b>Настройки поиска подписок</b>\n\n"
        f"📉 Минимальная цена: <code>{min_price} $</code>\n"
        f"📈 Максимальная цена: <code>{max_price} $</code>\n"
        f"⭐ Мин. отзывы продавца: <code>{min_reviews}</code>\n"
        f"🔍 Ключевые слова: <code>{keywords}</code>\n"
        f"🚫 Минус-слова: <code>{minus_display}</code>\n\n"
        f"Выберите пункт меню для изменения:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard())
    await callback.answer()

@router.callback_query(F.data == "set_min_price")
async def set_min_price_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод минимальной цены."""
    await state.set_state(SettingsStates.waiting_for_min_price)
    await callback.message.edit_text(
        "📉 <b>Введите новую минимальную цену в долларах ($):</b>\n"
        "Например: <code>0</code> или <code>2.5</code>\n"
        "<i>Установите 0, чтобы отключить фильтр по нижней границе.</i>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_min_price)
async def process_min_price(message: Message, state: FSMContext):
    """Сохранение новой минимальной цены."""
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с минимальной ценой.",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return
    text = message.text.replace(",", ".").strip()
    try:
        price = float(text)
        if price < 0:
            raise ValueError()
        
        await db_manager.set_setting("min_price_usd", str(price))
        await state.clear()
        
        await message.answer(
            f"✅ Минимальная цена успешно изменена на <b>{price} $</b>!",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b> Введите корректное число (>= 0).\n"
            "Пример: <code>2.5</code>",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )

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
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с максимальной ценой.",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return
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

@router.callback_query(F.data == "set_min_reviews")
async def set_min_reviews_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод минимального числа отзывов."""
    await state.set_state(SettingsStates.waiting_for_min_reviews)
    await callback.message.edit_text(
        "⭐ <b>Введите минимальное количество отзывов продавца:</b>\n"
        "Например: <code>10</code> или <code>0</code> (чтобы отключить)\n\n"
        "<i>Товары от продавцов с меньшим числом отзывов будут игнорироваться.</i>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_min_reviews)
async def process_min_reviews(message: Message, state: FSMContext):
    """Сохранение минимального количества отзывов."""
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с количеством отзывов.",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return
    text = message.text.strip()
    try:
        reviews = int(text)
        if reviews < 0:
            raise ValueError()
        
        await db_manager.set_setting("min_reviews", str(reviews))
        await state.clear()
        
        await message.answer(
            f"✅ Мин. количество отзывов успешно изменено на <b>{reviews}</b>!",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_settings")
        )
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b> Введите корректное целое число (>= 0).\n"
            "Пример: <code>10</code>",
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
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с ключевыми словами.",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return
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

@router.callback_query(F.data == "set_minus_words")
async def set_minus_words_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод минус-слов."""
    await state.set_state(SettingsStates.waiting_for_minus_words)
    current_minus = await db_manager.get_setting("minus_words", "")
    await callback.message.edit_text(
        f"🚫 <b>Введите минус-слова через запятую:</b>\n\n"
        f"Товары, содержащие эти слова в названии, будут игнорироваться.\n\n"
        f"Текущие: <code>{current_minus if current_minus else 'Нет'}</code>\n\n"
        f"Пример: <code>общий, аренда, shared</code>\n"
        f"<i>Чтобы очистить список, отправьте 0 или -</i>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_minus_words)
async def process_minus_words(message: Message, state: FSMContext):
    """Сохранение новых минус-слов."""
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с минус-словами.",
            reply_markup=get_back_keyboard("menu_settings")
        )
        return
    raw_text = message.text.strip()
    
    if raw_text in ["0", "-"]:
        minus_words = ""
    else:
        # Чистим пробелы вокруг слов и приводим к нижнему регистру
        minus_words = ",".join([k.strip().lower() for k in raw_text.split(",") if k.strip()])
    
    await db_manager.set_setting("minus_words", minus_words)
    await state.clear()
    
    display = minus_words if minus_words else "Очищены (фильтр отключен)"
    await message.answer(
        f"✅ Минус-слова успешно обновлены:\n<code>{display}</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_settings")
    )

from bot.keyboards.inline import get_dnd_keyboard
import re

@router.callback_query(F.data == "menu_dnd")
async def show_dnd_menu(callback: CallbackQuery, state: FSMContext = None):
    """Показывает меню настроек Тихого часа."""
    if state:
        await state.clear()
    dnd_enabled = await db_manager.get_setting("dnd_enabled", "0") == "1"
    dnd_start = await db_manager.get_setting("dnd_start", "23:00")
    dnd_end = await db_manager.get_setting("dnd_end", "08:00")
    
    status = "🟢 Включен" if dnd_enabled else "🔴 Выключен"
    
    text = (
        f"🌙 <b>Настройки Тихого часа (Do Not Disturb)</b>\n\n"
        f"Статус: {status}\n"
        f"Начало (не беспокоить с): <code>{dnd_start}</code>\n"
        f"Конец (отправить дайджест в): <code>{dnd_end}</code>\n\n"
        f"<i>Время указано по часовому поясу Германии (Europe/Berlin).</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_dnd_keyboard(dnd_enabled))
    await callback.answer()

@router.callback_query(F.data == "toggle_dnd")
async def toggle_dnd(callback: CallbackQuery):
    dnd_enabled = await db_manager.get_setting("dnd_enabled", "0") == "1"
    new_status = "0" if dnd_enabled else "1"
    await db_manager.set_setting("dnd_enabled", new_status)
    
    # Обновляем задачу дайджеста
    from services.digest import update_digest_job
    await update_digest_job()
    
    await show_dnd_menu(callback)

@router.callback_query(F.data == "set_dnd_start")
async def set_dnd_start_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_dnd_start)
    await callback.message.edit_text(
        "🌙 <b>Введите время начала Тихого часа (HH:MM):</b>\n"
        "Например: <code>23:00</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_dnd")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_dnd_start)
async def process_dnd_start(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с временем начала Тихого часа.",
            reply_markup=get_back_keyboard("menu_dnd")
        )
        return
    text = message.text.strip()
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", text):
        await message.answer(
            "❌ Неверный формат времени! Используйте HH:MM (от 00:00 до 23:59).",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_dnd")
        )
        return
        
    # Нормализуем 1:30 -> 01:30
    parts = text.split(":")
    text = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    
    await db_manager.set_setting("dnd_start", text)
    await state.clear()
    await message.answer(f"✅ Время начала Тихого часа установлено на <b>{text}</b>", parse_mode="HTML", reply_markup=get_back_keyboard("menu_dnd"))

@router.callback_query(F.data == "set_dnd_end")
async def set_dnd_end_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_dnd_end)
    await callback.message.edit_text(
        "🌅 <b>Введите время окончания Тихого часа (HH:MM):</b>\n"
        "В это время будет отправляться утренний дайджест.\n"
        "Например: <code>08:00</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_dnd")
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_dnd_end)
async def process_dnd_end(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое сообщение с временем окончания Тихого часа.",
            reply_markup=get_back_keyboard("menu_dnd")
        )
        return
    text = message.text.strip()
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", text):
        await message.answer(
            "❌ Неверный формат времени! Используйте HH:MM (от 00:00 до 23:59).",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_dnd")
        )
        return
        
    parts = text.split(":")
    text = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    
    await db_manager.set_setting("dnd_end", text)
    await state.clear()
    
    # Пересоздаем задачу дайджеста
    from services.digest import update_digest_job
    await update_digest_job()
    
    await message.answer(f"✅ Время окончания Тихого часа установлено на <b>{text}</b>", parse_mode="HTML", reply_markup=get_back_keyboard("menu_dnd"))

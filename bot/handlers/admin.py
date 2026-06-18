from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
import json
from database import db_manager
from bot.keyboards.inline import get_main_menu_keyboard, get_back_keyboard, get_categories_keyboard, get_back_to_categories_keyboard
from bot.filters.admin_filter import IsAdminFilter
from services.monitor import toggle_monitoring_job

router = Router()
# Применяем фильтр админа ко всем хендлерам в этом роутере
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

async def get_dashboard_text() -> str:
    """Формирует текст панели управления с текущими настройками."""
    max_price = await db_manager.get_setting("max_price_usd", "10.0")
    keywords = await db_manager.get_setting("keywords", "Не заданы")
    interval = await db_manager.get_setting("interval_minutes", "60")
    monitoring_enabled = await db_manager.get_setting("monitoring_enabled", "1")
    
    status_emoji = "🟢 ЗАПУЩЕН" if monitoring_enabled == "1" else "🔴 ОСТАНОВЛЕН"
    
    # Статистика по прокси
    proxies = await db_manager.get_all_proxies()
    total_proxies = len(proxies)
    active_proxies = sum(1 for p in proxies if p[1] == 1)

    text = (
        f"👑 <b>Панель управления мониторингом</b>\n\n"
        f"<b>Статус:</b> {status_emoji}\n\n"
        f"<b>Параметры поиска:</b>\n"
        f"💵 Макс. цена: <code>{max_price} $</code>\n"
        f"🔍 Ключевые слова: <code>{keywords}</code>\n"
        f"⏱ Интервал парсинга: <code>{interval} мин.</code>\n\n"
        f"<b>Прокси-серверы:</b>\n"
        f"🌐 Всего добавлено: <code>{total_proxies}</code>\n"
        f"✅ Рабочих прокси: <code>{active_proxies}</code>"
    )
    return text

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Отправка главного меню администратора."""
    text = await get_dashboard_text()
    monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(monitoring_enabled))

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню из подменю."""
    text = await get_dashboard_text()
    monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=get_main_menu_keyboard(monitoring_enabled)
    )
    await callback.answer()

@router.callback_query(F.data == "toggle_monitoring")
async def toggle_monitoring(callback: CallbackQuery):
    """Включение/выключение мониторинга."""
    current_status = await db_manager.get_setting("monitoring_enabled", "1")
    new_status = "0" if current_status == "1" else "1"
    await db_manager.set_setting("monitoring_enabled", new_status)
    
    # Управляем задачей в планировщике
    toggle_monitoring_job(new_status == "1")
    
    text = await get_dashboard_text()
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=get_main_menu_keyboard(new_status == "1")
    )
    await callback.answer(f"Мониторинг {'запущен' if new_status == '1' else 'остановлен'}")

@router.callback_query(F.data == "show_current_deals")
async def show_current_deals(callback: CallbackQuery):
    """Отображает список доступных категорий для лучших цен."""
    snapshot_json = await db_manager.get_latest_snapshot()
    if not snapshot_json:
        await callback.answer("Данных пока нет, дождитесь окончания парсинга.", show_alert=True)
        return
        
    try:
        snapshot = json.loads(snapshot_json)
    except Exception as e:
        await callback.answer("Ошибка при чтении данных.", show_alert=True)
        return
        
    if not snapshot:
        await callback.answer("Данных пока нет, дождитесь окончания парсинга.", show_alert=True)
        return
        
    # Собираем уникальные категории
    categories = sorted(list(set(item['ai_category'] for item in snapshot)))
    
    text = "📊 <b>Текущие лучшие цены</b>\n\nВыберите категорию:"
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_categories_keyboard(categories)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("show_cat_"))
async def show_category_deals(callback: CallbackQuery):
    """Отображает лучшие цены для выбранной категории."""
    category_name = callback.data[len("show_cat_"):]
    
    snapshot_json = await db_manager.get_latest_snapshot()
    if not snapshot_json:
        await callback.answer("Данных пока нет.", show_alert=True)
        return
        
    try:
        snapshot = json.loads(snapshot_json)
    except Exception:
        await callback.answer("Ошибка при чтении данных.", show_alert=True)
        return
        
    # Группируем данные для выбранной категории: duration -> list of items
    from collections import defaultdict
    grouped = defaultdict(list)
    for item in snapshot:
        if item['ai_category'] == category_name:
            grouped[item['duration']].append(item)
            
    if not grouped:
        await callback.answer("Нет данных для этой категории.", show_alert=True)
        return
        
    lines = [f"📊 <b>Лучшие цены:</b> 🤖 {category_name}\n"]
    for duration in sorted(grouped.keys()):
        lines.append(f"  ⏳ <i>{duration}</i>")
        for item in sorted(grouped[duration], key=lambda x: x['price_usd']):
            drop_text = f" 📉 (Упало на {item['price_drop']} $)" if item.get('price_drop', 0) > 0 else ""
            lines.append(f"    • {item['platform']}: {item['price_rub']} ₽ (~{item['price_usd']}$){drop_text} - <a href='{item['url']}'>Ссылка</a>")
        lines.append("")
        
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (данные обрезаны)"
        
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_back_to_categories_keyboard()
    )
    await callback.answer()

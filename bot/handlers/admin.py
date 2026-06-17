from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from database import db_manager
from bot.keyboards.inline import get_main_menu_keyboard
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

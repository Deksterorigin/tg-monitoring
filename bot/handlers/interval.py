from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import db_manager
from bot.keyboards.inline import get_interval_keyboard, get_back_keyboard
from bot.filters.admin_filter import IsAdminFilter
from services.monitor import update_monitoring_job

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

@router.callback_query(F.data == "menu_interval")
async def show_interval_menu(callback: CallbackQuery):
    """Показывает меню выбора интервала мониторинга."""
    current_interval = await db_manager.get_setting("interval_minutes", "60")
    
    text = (
        f"⏱ <b>Интервал парсинга маркетплейсов</b>\n\n"
        f"Текущая частота проверок: <b>раз в {current_interval} мин.</b>\n\n"
        f"Выберите новый интервал ниже:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_interval_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("interval_"))
async def set_interval(callback: CallbackQuery):
    """Устанавливает новый интервал парсинга и обновляет планировщик."""
    try:
        minutes = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка ввода")
        return
        
    await db_manager.set_setting("interval_minutes", str(minutes))
    
    # Обновляем задачу в планировщике
    update_monitoring_job(minutes)
    
    await callback.message.edit_text(
        f"✅ Частота проверки успешно изменена на <b>раз в {minutes} мин.</b>!",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("back_to_main")
    )
    await callback.answer(f"Интервал изменен на {minutes} мин.")

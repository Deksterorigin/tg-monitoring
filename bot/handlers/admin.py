from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
import json
from database import db_manager
from bot.keyboards.inline import get_main_menu_keyboard, get_back_keyboard, get_categories_keyboard, get_back_to_categories_keyboard
from bot.filters.admin_filter import IsAdminFilter
from services.monitor import toggle_monitoring_job, trigger_manual_monitoring
from services.currency import currency_service

router = Router()
# Применяем фильтр админа ко всем хендлерам в этом роутере
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

async def get_dashboard_text() -> str:
    """Формирует текст панели управления с текущими настройками."""
    min_price = await db_manager.get_setting("min_price_usd", "0.0")
    max_price = await db_manager.get_setting("max_price_usd", "10.0")
    keywords = await db_manager.get_setting("keywords", "Не заданы")
    interval = await db_manager.get_setting("interval_minutes", "60")
    monitoring_enabled = await db_manager.get_setting("monitoring_enabled", "1")
    
    status_emoji = "🟢 ЗАПУЩЕН (Авто)" if monitoring_enabled == "1" else "🔴 ОСТАНОВЛЕН (Авто)"
    
    # Статистика по прокси
    proxies = await db_manager.get_all_proxies()
    total_proxies = len(proxies)
    active_proxies = sum(1 for p in proxies if p[1] == 1)

    text = (
        f"👑 <b>Панель управления мониторингом</b>\n\n"
        f"<b>Статус:</b> {status_emoji}\n\n"
        f"🎯 <b>Параметры поиска:</b>\n"
        f"💵 Фильтр цен: <code>{min_price} $ - {max_price} $</code>\n"
        f"🔍 Ключевые слова: <code>{keywords}</code>\n"
        f"⏱ Интервал проверки: <code>{interval} мин.</code>\n\n"
        f"🌐 <b>Прокси-серверы:</b>\n"
        f"• Всего в системе: <code>{total_proxies}</code>\n"
        f"• Активных: <code>{active_proxies}</code>"
    )
    return text

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext = None):
    """Отправка главного меню администратора."""
    if state:
        await state.clear()
    text = await get_dashboard_text()
    monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(monitoring_enabled))

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Сброс FSM-состояния по команде /cancel."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=get_back_keyboard("back_to_main"))
    else:
        text = await get_dashboard_text()
        monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(monitoring_enabled))

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext = None):
    """Возврат в главное меню из подменю с очисткой FSM-состояния."""
    if state:
        await state.clear()
    text = await get_dashboard_text()
    monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=get_main_menu_keyboard(monitoring_enabled)
    )
    await callback.answer()

@router.callback_query(F.data == "run_manual_parse")
async def run_manual_parse(callback: CallbackQuery):
    """Ручной мгновенный запуск цикла мониторинга."""
    started, msg = await trigger_manual_monitoring()
    await callback.answer(msg, show_alert=True)
    if started:
        text = await get_dashboard_text()
        monitoring_enabled = (await db_manager.get_setting("monitoring_enabled", "1")) == "1"
        await callback.message.edit_text(
            f"⚡ <b>Парсинг запущен в фоновом режиме!</b>\nРезультаты обновятся в меню «Текущие лучшие цены» после завершения.\n\n" + text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(monitoring_enabled)
        )

@router.callback_query(F.data == "show_analytics")
async def show_analytics(callback: CallbackQuery):
    """Отображает подробную аналитику работы бота."""
    analytics = await db_manager.get_analytics_summary()
    await currency_service.update_rates()
    
    usd_rate = 1.0 / currency_service.rub_to_usd_rate if currency_service.rub_to_usd_rate > 0 else 90.0
    eur_rate = currency_service.eur_to_rub_rate

    text = (
        f"📈 <b>Аналитика и статус системы</b>\n\n"
        f"⏱ <b>Последний запуск:</b> <code>{analytics['last_parse_time']}</code>\n"
        f"⏳ <b>Длительность цикла:</b> <code>{analytics['last_parse_duration']} сек.</code>\n"
        f"📦 <b>Сделок найдено за запуск:</b> <code>{analytics['last_parse_items']}</code>\n"
        f"🔔 <b>Уведомлений отправлено:</b> <code>{analytics['last_parse_notifications']}</code>\n\n"
        f"💾 <b>Всего сохраненных объявлений:</b> <code>{analytics['total_seen_items']}</code>\n"
        f"📁 <b>Размер базы данных:</b> <code>{analytics['db_size_mb']} МБ</code>\n\n"
        f"💱 <b>Курсы ЦБ РФ:</b>\n"
        f"• 1 USD = <code>{usd_rate:.2f} ₽</code>\n"
        f"• 1 EUR = <code>{eur_rate:.2f} ₽</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard("back_to_main"))
    await callback.answer()

@router.callback_query(F.data == "toggle_monitoring")
async def toggle_monitoring(callback: CallbackQuery):
    """Включение/выключение авто-мониторинга."""
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
    await callback.answer(f"Авто-парсинг {'запущен' if new_status == '1' else 'остановлен'}")

@router.callback_query(F.data == "show_current_deals")
async def show_current_deals(callback: CallbackQuery):
    """Отображает список доступных категорий для лучших цен."""
    snapshot_json = await db_manager.get_latest_snapshot()
    if not snapshot_json:
        await callback.answer("Данных пока нет. Нажмите «⚡ Запустить парсинг сейчас».", show_alert=True)
        return
        
    try:
        snapshot = json.loads(snapshot_json)
    except Exception:
        await callback.answer("Ошибка при чтении данных.", show_alert=True)
        return
        
    if not snapshot:
        await callback.answer("Данных пока нет. Нажмите «⚡ Запустить парсинг сейчас».", show_alert=True)
        return
        
    # Собираем уникальные категории
    categories = sorted(list(set(item['ai_category'] for item in snapshot)))
    
    text = (
        f"📊 <b>Текущие лучшие цены по категориям</b>\n\n"
        f"Найдено категорий: <code>{len(categories)}</code>\n"
        f"Выберите нейросеть для просмотра предложений:"
    )
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
        
    lines = [f"📊 <b>Лучшие предложения:</b> 🤖 {category_name}\n"]
    for duration in sorted(grouped.keys()):
        lines.append(f"⏳ <b>{duration}:</b>")
        for item in sorted(grouped[duration], key=lambda x: x['price_usd']):
            drop_text = f" 📉 (Упало на {item['price_drop']} $)" if item.get('price_drop', 0) > 0 else ""
            lines.append(f"  • <b>{item['platform']}</b>: {item['price_rub']} ₽ (~{item['price_usd']}$){drop_text} — <a href='{item['url']}'>🔗 Ссылка</a>")
        lines.append("")
        
    text = "\n".join(lines)
    if len(text) > 4000:
        # Обрезаем по целым строкам, чтобы не ломать HTML-теги
        lines_list = text.split("\n")
        truncated = ""
        for line in lines_list:
            if len(truncated) + len(line) + 1 > 3900:
                break
            truncated += line + "\n"
        text = truncated + "\n... (показаны первые предложения)"
        
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_back_to_categories_keyboard()
    )
    await callback.answer()

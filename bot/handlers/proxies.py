import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db_manager
from bot.keyboards.inline import get_proxies_keyboard, get_back_keyboard
from bot.filters.admin_filter import IsAdminFilter
from services.proxy_checker import ProxyChecker

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class ProxyStates(StatesGroup):
    waiting_for_proxies = State()

async def get_proxy_list_text() -> str:
    """Формирует список прокси и их статус."""
    proxies = await db_manager.get_all_proxies()
    if not proxies:
        return "🌐 <b>Список прокси пуст.</b>"

    text = "🌐 <b>Список прокси-серверов:</b>\n\n"
    for idx, (proxy, status) in enumerate(proxies, 1):
        status_emoji = "✅" if status == 1 else "❌"
        # Маскируем пароль прокси для безопасности
        parts = proxy.split(":")
        if len(parts) == 4:
            masked_proxy = f"{parts[0]}:{parts[1]}:{parts[2]}:****"
        else:
            masked_proxy = proxy
        text += f"{idx}. <code>{masked_proxy}</code> {status_emoji}\n"
    return text

@router.callback_query(F.data == "menu_proxies")
async def show_proxies_menu(callback: CallbackQuery):
    """Показывает меню управления прокси."""
    list_text = await get_proxy_list_text()
    
    text = (
        f"{list_text}\n"
        f"Формат для добавления прокси:\n"
        f"<code>IP:PORT</code> или <code>IP:PORT:USER:PASS</code>\n"
        f"Каждый прокси с новой строки."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_proxies_keyboard())
    await callback.answer()

@router.callback_query(F.data == "add_proxy_prompt")
async def add_proxy_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос ввода прокси-серверов."""
    await state.set_state(ProxyStates.waiting_for_proxies)
    await callback.message.edit_text(
        "📝 <b>Отправьте список прокси.</b>\n"
        "Каждый прокси должен быть на новой строке в формате:\n"
        "<code>IP:PORT</code> или <code>IP:PORT:USER:PASS</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_proxies")
    )
    await callback.answer()

@router.message(ProxyStates.waiting_for_proxies)
async def process_add_proxies(message: Message, state: FSMContext):
    """Добавление прокси в БД."""
    lines = message.text.strip().split("\n")
    added_count = 0
    ignored_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split(":")
        if len(parts) in (2, 4):
            success = await db_manager.add_proxy(line)
            if success:
                added_count += 1
            else:
                ignored_count += 1
        else:
            ignored_count += 1

    await state.clear()
    await message.answer(
        f"✅ <b>Добавление завершено:</b>\n"
        f"Добавлено прокси: <code>{added_count}</code>\n"
        f"Некорректных/дубликатов: <code>{ignored_count}</code>",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_proxies")
    )

@router.callback_query(F.data == "check_proxies")
async def check_proxies_callback(callback: CallbackQuery):
    """Запуск проверки всех прокси."""
    proxies = await db_manager.get_all_proxies()
    if not proxies:
        await callback.answer("Нет прокси для проверки!", show_alert=True)
        return

    await callback.message.edit_text(
        "🔄 <b>Запущена проверка прокси...</b>\nПожалуйста, подождите, это может занять до минуты.",
        parse_mode="HTML"
    )
    await callback.answer()

    valid_count = 0
    invalid_count = 0

    # Проверяем все прокси асинхронно
    async def check_and_update(proxy_str: str):
        nonlocal valid_count, invalid_count
        is_valid = await ProxyChecker.check(proxy_str)
        status = 1 if is_valid else 0
        await db_manager.update_proxy_status(proxy_str, status)
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

    tasks = [check_and_update(p[0]) for p in proxies]
    await asyncio.gather(*tasks)

    # Показываем результат
    result_text = (
        f"✅ <b>Проверка прокси завершена!</b>\n\n"
        f"Проверено всего: <code>{len(proxies)}</code>\n"
        f"Рабочих: <code>{valid_count}</code>\n"
        f"Нерабочих: <code>{invalid_count}</code>"
    )
    await callback.message.answer(
        result_text,
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_proxies")
    )

@router.callback_query(F.data == "delete_dead_proxies")
async def delete_dead_proxies_callback(callback: CallbackQuery):
    """Удаляет нерабочие прокси из БД."""
    proxies = await db_manager.get_all_proxies()
    dead_proxies = [p for p in proxies if p[1] == 0]
    
    await db_manager.delete_dead_proxies()
    
    await callback.message.edit_text(
        f"✅ Удалено нерабочих прокси: <b>{len(dead_proxies)}</b>.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_proxies")
    )
    await callback.answer(f"Удалено {len(dead_proxies)} нерабочих прокси.")

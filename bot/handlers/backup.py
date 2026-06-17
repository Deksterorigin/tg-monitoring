import os
import shutil
import sqlite3
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config import settings
from bot.keyboards.inline import get_backup_keyboard, get_back_keyboard, get_main_menu_keyboard
from bot.filters.admin_filter import IsAdminFilter

logger = logging.getLogger(__name__)
router = Router()

# Применяем фильтр админа
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

class BackupStates(StatesGroup):
    waiting_for_db_file = State()

@router.callback_query(F.data == "menu_backup")
async def show_backup_menu(callback: CallbackQuery, state: FSMContext):
    """Отображает меню резервного копирования."""
    await state.clear()  # Очищаем состояние на случай, если зашли повторно
    
    text = (
        "💾 <b>Резервное копирование базы данных</b>\n\n"
        "Здесь вы можете экспортировать или восстановить конфигурацию бота:\n\n"
        "📥 <b>Скачать БД</b> — выгрузит текущий файл SQLite базы данных (настройки, админы, прокси, история найденного).\n"
        "📤 <b>Восстановить БД</b> — загрузите ранее сохраненный файл базы данных, чтобы перезаписать текущие настройки.\n\n"
        "⚠️ <i>Внимание: восстановление базы данных полностью сотрет текущие настройки, прокси и список администраторов!</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_backup_keyboard())
    await callback.answer()

@router.callback_query(F.data == "download_db")
async def download_db(callback: CallbackQuery):
    """Отправляет файл базы данных администратору."""
    db_file_path = settings.DATABASE_PATH
    
    if not os.path.exists(db_file_path):
        await callback.message.answer("⚠️ Файл базы данных не найден на сервере.")
        await callback.answer()
        return

    try:
        document = FSInputFile(db_file_path, filename="bot_database.db")
        await callback.message.answer_document(
            document=document, 
            caption="💾 Резервная копия базы данных SQLite.\nСохраните этот файл для восстановления."
        )
        await callback.answer("База данных успешно выгружена")
    except Exception as e:
        logger.error(f"Ошибка при выгрузке БД: {e}")
        await callback.message.answer(f"❌ Ошибка при отправке файла: {e}")
        await callback.answer()

@router.callback_query(F.data == "restore_db")
async def restore_db_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на загрузку файла для восстановления базы данных."""
    await state.set_state(BackupStates.waiting_for_db_file)
    await callback.message.edit_text(
        "📤 <b>Отправьте файл резервной копии базы данных (.db):</b>\n\n"
        "Бот проверит структуру файла и примет его, если он валиден.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_backup")
    )
    await callback.answer()

@router.message(BackupStates.waiting_for_db_file, F.document)
async def process_db_restore(message: Message, state: FSMContext):
    """Обработка загруженного файла базы данных, его валидация и перезапись текущей БД."""
    document = message.document
    
    # 1. Проверяем расширение файла
    if not document.file_name.endswith(('.db', '.sqlite', '.sqlite3')):
        await message.answer(
            "⚠️ Файл должен иметь расширение .db, .sqlite или .sqlite3.\n"
            "Пожалуйста, отправьте правильный файл или нажмите 'Назад'.",
            reply_markup=get_back_keyboard("menu_backup")
        )
        return

    temp_path = "bot_database_temp.db"
    
    try:
        # 2. Скачиваем файл во временное хранилище
        await message.bot.download(document, destination=temp_path)
        
        # 3. Валидация файла базы данных
        conn = sqlite3.connect(temp_path)
        cursor = conn.cursor()
        
        # Проверяем целостность SQLite
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("Проверка целостности (integrity check) файла SQLite завершилась ошибкой.")
        
        # Проверяем наличие обязательных таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        required_tables = ["admins", "settings", "proxies", "seen_items"]
        
        for table in required_tables:
            if table not in tables:
                raise ValueError(f"В базе данных отсутствует необходимая таблица: '{table}'.")
        
        # Проверяем, что есть хотя бы один администратор
        cursor.execute("SELECT COUNT(*) FROM admins;")
        admin_count = cursor.fetchone()[0]
        if admin_count == 0:
            raise ValueError("Таблица администраторов (admins) пуста. Восстановление заблокировано во избежание потери доступа.")
            
        conn.close()
        
    except Exception as e:
        if 'conn' in locals():
            try:
                conn.close()
            except Exception:
                pass
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        logger.error(f"Ошибка валидации загруженного файла бэкапа: {e}")
        await message.answer(
            f"❌ <b>Ошибка валидации файла:</b>\n"
            f"<code>{str(e)}</code>\n\n"
            f"База данных не была заменена. Пожалуйста, попробуйте еще раз.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("menu_backup")
        )
        return

    # 4. Перезапись оригинального файла БД
    db_file_path = settings.DATABASE_PATH
    try:
        # Пытаемся заменить файл
        shutil.move(temp_path, db_file_path)
        await state.clear()
        
        await message.answer(
            "✅ <b>Резервная копия успешно восстановлена!</b>\n\n"
            "Все настройки, список администраторов и прокси успешно применены.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(monitoring_enabled=True) # Показываем меню с кнопками
        )
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error(f"Ошибка при перезаписи файла БД: {e}")
        await message.answer(
            f"❌ Ошибка при перезаписи файла базы данных на сервере: {e}\n"
            f"Попробуйте заново или обратитесь к разработчику.",
            reply_markup=get_back_keyboard("menu_backup")
        )

@router.message(BackupStates.waiting_for_db_file)
async def process_db_restore_invalid(message: Message):
    """Обработка некорректного ввода (если отправлен не документ)."""
    await message.answer(
        "⚠️ Пожалуйста, отправьте файл резервной копии (.db) в виде <b>документа</b> (файла), "
        "или нажмите кнопку 'Назад' для отмены.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("menu_backup")
    )

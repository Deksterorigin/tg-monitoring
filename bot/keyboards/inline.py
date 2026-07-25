from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard(monitoring_enabled: bool) -> InlineKeyboardMarkup:
    # Динамическая кнопка старт/стоп
    toggle_text = "⏸ Стоп авто-парсинга" if monitoring_enabled else "▶️ Старт авто-парсинга"
    
    buttons = [
        [
            InlineKeyboardButton(text="⚡ Запустить парсинг сейчас", callback_data="run_manual_parse")
        ],
        [
            InlineKeyboardButton(text="📊 Текущие лучшие цены", callback_data="show_current_deals"),
            InlineKeyboardButton(text="📈 Аналитика & Статус", callback_data="show_analytics")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки поиска", callback_data="menu_settings"),
            InlineKeyboardButton(text="⏱ Интервал парсинга", callback_data="menu_interval")
        ],
        [
            InlineKeyboardButton(text="🛡 Прокси-менеджер", callback_data="menu_proxies"),
            InlineKeyboardButton(text="👥 Админы", callback_data="menu_admins")
        ],
        [
            InlineKeyboardButton(text=toggle_text, callback_data="toggle_monitoring"),
            InlineKeyboardButton(text="💾 Бэкап БД", callback_data="menu_backup")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_backup_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📥 Скачать БД", callback_data="download_db"),
            InlineKeyboardButton(text="📤 Восстановить БД", callback_data="restore_db")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📉 Изменить мин. цену ($)", callback_data="set_min_price"),
            InlineKeyboardButton(text="📈 Изменить макс. цену ($)", callback_data="set_max_price")
        ],
        [
            InlineKeyboardButton(text="⭐ Мин. отзывы продавца", callback_data="set_min_reviews"),
            InlineKeyboardButton(text="📉 Порог демпинга ($)", callback_data="set_min_price_drop")
        ],
        [
            InlineKeyboardButton(text="🔍 Ключевые слова", callback_data="set_keywords"),
            InlineKeyboardButton(text="🚫 Минус-слова", callback_data="set_minus_words")
        ],
        [
            InlineKeyboardButton(text="🌙 Тихий час (DND)", callback_data="menu_dnd")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_interval_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="15 минут", callback_data="interval_15"),
            InlineKeyboardButton(text="30 минут", callback_data="interval_30")
        ],
        [
            InlineKeyboardButton(text="1 час", callback_data="interval_60"),
            InlineKeyboardButton(text="4 часа", callback_data="interval_240")
        ],
        [
            InlineKeyboardButton(text="12 часов", callback_data="interval_720"),
            InlineKeyboardButton(text="24 часа", callback_data="interval_1440")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_proxies_keyboard(auto_proxies_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🌐 Авто-прокси (GitHub): Вкл" if auto_proxies_enabled else "🌐 Авто-прокси (GitHub): Выкл"
    buttons = [
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_auto_proxies")],
        [InlineKeyboardButton(text="➕ Добавить прокси", callback_data="add_proxy_prompt")],
        [InlineKeyboardButton(text="🔄 Проверить все прокси", callback_data="check_proxies")],
        [InlineKeyboardButton(text="❌ Удалить мертвые прокси", callback_data="delete_dead_proxies")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admins_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin_prompt")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="remove_admin_prompt")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard(back_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_categories_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    # Категории расположим в 2 колонки для компактности
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=f"🤖 {cat}", callback_data=f"show_cat_{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="📊 Скачать Excel отчет (.xlsx)", callback_data="export_deals_excel")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📊 Скачать Excel отчет (.xlsx)", callback_data="export_deals_excel")],
        [InlineKeyboardButton(text="🔙 К списку категорий", callback_data="show_current_deals")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_dnd_keyboard(dnd_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить Тихий час" if dnd_enabled else "🟢 Включить Тихий час"
    buttons = [
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_dnd")],
        [
            InlineKeyboardButton(text="⏰ Начало (DND)", callback_data="set_dnd_start"),
            InlineKeyboardButton(text="🌅 Конец (Дайджест)", callback_data="set_dnd_end")
        ],
        [InlineKeyboardButton(text="🔙 В настройки", callback_data="menu_settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# bot.py
import os
import json
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

# ================= ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ BOTHOST =================
API_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = os.getenv('ADMIN_ID', None)  # Берем админа из переменных BotHost
CONFIG_FILE = os.getenv('CONFIG_FILE', 'config.json')

# Проверяем, что админ установлен
if not ADMIN_ID:
    logging.warning("⚠️ ADMIN_ID не установлен в переменных окружения BotHost!")
    logging.warning("Добавьте переменную ADMIN_ID с вашим Telegram ID")

# ================= КОНФИГ ПО УМОЛЧАНИЮ =================
DEFAULT_CONFIG = {
    "mode": 1,
    "sponsors": [],
    "min_clicks": 0,
    "admin_id": ADMIN_ID  # Сохраняем админа из переменных
}

MODE_MESSAGES = {
    1: "✅ Бот активирован! Можете приступать к использованию.",
    2: "✅ Бот активирован! Пожалуйста, сделайте скриншот и отправьте его админу.",
    3: "✅ Бот активирован! Для подтверждения отправьте скриншот администратору."
}

logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# ================= ЗАГРУЗКА/СОХРАНЕНИЕ КОНФИГА =================
def load_config():
    """Загружает конфиг из файла, а админа всегда берет из переменной"""
    config = DEFAULT_CONFIG.copy()
    
    # Загружаем остальные настройки из файла
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                # Не перезаписываем admin_id из файла, используем переменную
                if 'admin_id' in file_config:
                    del file_config['admin_id']
                config.update(file_config)
                logging.info(f"✅ Конфиг загружен из файла: {CONFIG_FILE}")
        except Exception as e:
            logging.error(f"❌ Ошибка загрузки конфига: {e}")
    
    # Всегда используем ADMIN_ID из переменных окружения
    config['admin_id'] = ADMIN_ID
    config['min_clicks'] = len(config.get('sponsors', []))
    
    return config

def save_config(config):
    """Сохраняет конфиг в файл (без admin_id)"""
    try:
        # Создаем копию без admin_id
        save_data = config.copy()
        if 'admin_id' in save_data:
            del save_data['admin_id']
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        logging.info(f"✅ Конфиг сохранен в файл: {CONFIG_FILE}")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения конфига: {e}")
        return False

# Загружаем конфиг
config = load_config()

# ================= СОСТОЯНИЯ FSM =================
class AdminStates(StatesGroup):
    waiting_for_sponsor_link = State()
    waiting_for_edit_sponsor = State()

class UserStates(StatesGroup):
    waiting_for_confirm = State()

# ================= ХРАНИЛИЩЕ ДАННЫХ =================
user_data = {}

# ================= КЛАВИАТУРЫ =================

def get_admin_panel():
    """Главная админ-панель"""
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Добавить спонсора", callback_data="admin_add_sponsor")],
        [InlineKeyboardButton(text="📋 Список спонсоров", callback_data="admin_list_sponsors")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📝 Режимы сообщений", callback_data="admin_modes")],
        [InlineKeyboardButton(text="🔄 Обновить данные", callback_data="admin_refresh")],
        [InlineKeyboardButton(text="🔙 Выйти из админки", callback_data="admin_exit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_sponsors_list_keyboard():
    """Клавиатура со списком спонсоров"""
    keyboard = []
    sponsors = config.get('sponsors', [])
    
    if not sponsors:
        keyboard.append([InlineKeyboardButton(text="📭 Список пуст", callback_data="empty")])
    else:
        for idx, sponsor in enumerate(sponsors, 1):
            display_text = sponsor[:30] + "..." if len(sponsor) > 30 else sponsor
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{idx}. {display_text}",
                    callback_data=f"sponsor_view_{idx-1}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=f"sponsor_edit_{idx-1}"
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"sponsor_delete_{idx-1}"
                )
            ])
            if idx < len(sponsors):
                keyboard.append([InlineKeyboardButton(text="─" * 20, callback_data="separator")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_mode_keyboard():
    """Клавиатура выбора режима"""
    current_mode = config.get('mode', 1)
    keyboard = []
    
    for mode_id, text in MODE_MESSAGES.items():
        check = "✅ " if mode_id == current_mode else ""
        keyboard.append([
            InlineKeyboardButton(
                text=f"{check}Режим {mode_id}",
                callback_data=f"mode_set_{mode_id}"
            )
        ])
        # Показываем текст режима
        keyboard.append([
            InlineKeyboardButton(
                text=f"📝 {text[:30]}...",
                callback_data=f"mode_preview_{mode_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_settings_keyboard():
    """Клавиатура настроек"""
    min_clicks = config.get('min_clicks', 0)
    sponsors_count = len(config.get('sponsors', []))
    
    keyboard = [
        [InlineKeyboardButton(
            text=f"📌 Мин. кликов: {min_clicks}",
            callback_data="settings_min_clicks"
        )],
        [InlineKeyboardButton(
            text=f"📢 Спонсоров: {sponsors_count}",
            callback_data="settings_sponsors_count"
        )],
        [InlineKeyboardButton(
            text=f"👑 Админ: {ADMIN_ID or 'Не установлен'}",
            callback_data="settings_admin"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_activation_keyboard(sponsors_count):
    """Клавиатура активации для пользователя"""
    keyboard = []
    sponsors = config.get('sponsors', [])
    
    for idx, link in enumerate(sponsors, 1):
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 Подписаться на канал {idx}",
                callback_data=f"sponsor_click_{idx-1}",
                url=link  # Открываем ссылку сразу
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="✅ Подтвердить подписку",
            callback_data="confirm_subscribe"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_keyboard():
    """Главное меню пользователя"""
    keyboard = [
        [InlineKeyboardButton(text="🚀 Активировать бота", callback_data="activate")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================= ПРОВЕРКА АДМИНА =================
def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)

# ================= ОБРАБОТЧИКИ КОМАНД =================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    # Если пользователь админ - показываем админ-панель
    if is_admin(user_id):
        await message.answer(
            "👋 Добро пожаловать в админ-панель!\n\n"
            f"👑 Ваш ID: {user_id}\n"
            f"📢 Спонсоров: {len(config.get('sponsors', []))}\n"
            f"📝 Режим: {config.get('mode', 1)}",
            reply_markup=get_admin_panel()
        )
        return
    
    # Обычный пользователь
    if user_data[user_id]['activated']:
        await message.answer("✅ Бот уже активирован!")
        return
    
    sponsors = config.get('sponsors', [])
    if not sponsors:
        await message.answer(
            "⏳ Бот еще настраивается администратором.\n"
            "Пожалуйста, подождите."
        )
        return
    
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Для активации бота необходимо подписаться на все каналы ниже.\n"
        "После подписки нажмите кнопку 'Подтвердить подписку'.\n\n"
        f"📌 Всего каналов: {len(sponsors)}",
        reply_markup=get_activation_keyboard(len(sponsors))
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        await message.answer("⛔ Доступ запрещен! Вы не являетесь администратором.")
        return
    
    await message.answer(
        "🔐 Админ-панель",
        reply_markup=get_admin_panel()
    )

@dp.message(Command("id"))
async def cmd_id(message: Message):
    """Показывает ID пользователя (для настройки админа)"""
    await message.answer(
        f"🆔 Ваш Telegram ID: <code>{message.from_user.id}</code>\n\n"
        "Если вы хотите стать администратором, добавьте этот ID "
        "в переменную ADMIN_ID в настройках BotHost.",
        parse_mode="HTML"
    )

# ================= ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ =================

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "🔐 Админ-панель",
        reply_markup=get_admin_panel()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.delete()
    await callback.message.answer("👋 До свидания!")
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    total_users = len(user_data)
    activated = sum(1 for u in user_data.values() if u['activated'])
    sponsors_count = len(config.get('sponsors', []))
    
    stats_text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"✅ Активировано: <b>{activated}</b>\n"
        f"❌ Не активировано: <b>{total_users - activated}</b>\n"
        f"📢 Спонсоров: <b>{sponsors_count}</b>\n"
        f"📝 Текущий режим: <b>{config.get('mode', 1)}</b>\n"
        f"👑 Админ: <b>{ADMIN_ID or 'Не установлен'}</b>\n"
        f"🕐 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    
    await callback.message.edit_text(stats_text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_refresh")
async def admin_refresh(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    global config
    config = load_config()
    
    await callback.message.edit_text(
        "🔄 Данные обновлены!\n\n"
        f"📢 Спонсоров: {len(config.get('sponsors', []))}\n"
        f"📝 Режим: {config.get('mode', 1)}",
        reply_markup=get_admin_panel()
    )
    await callback.answer("✅ Обновлено!")

@dp.callback_query(F.data == "admin_add_sponsor")
async def admin_add_sponsor(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "📝 Введите ссылку на канал/спонсора:\n\n"
        "Пример: https://t.me/channel_name\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_sponsor_link)
    await callback.answer()

@dp.message(AdminStates.waiting_for_sponsor_link)
async def process_sponsor_link(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        await message.answer("⛔ Доступ запрещен!")
        await state.clear()
        return
    
    link = message.text.strip()
    
    # Валидация ссылки
    if not link.startswith(('https://t.me/', 'http://t.me/', 'https://www.t.me/')):
        await message.answer(
            "❌ Неверный формат ссылки!\n"
            "Ссылка должна начинаться с https://t.me/\n"
            "Попробуйте снова или отправьте /cancel"
        )
        return
    
    # Добавляем спонсора
    if 'sponsors' not in config:
        config['sponsors'] = []
    
    config['sponsors'].append(link)
    config['min_clicks'] = len(config['sponsors'])
    
    if save_config(config):
        await message.answer(
            f"✅ Ссылка добавлена!\n\n"
            f"📢 Всего спонсоров: {len(config['sponsors'])}\n"
            f"🎯 Мин. кликов: {config['min_clicks']}",
            reply_markup=get_admin_panel()
        )
    else:
        await message.answer("❌ Ошибка сохранения!", reply_markup=get_admin_panel())
    
    await state.clear()

@dp.callback_query(F.data == "admin_list_sponsors")
async def admin_list_sponsors(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    sponsors = config.get('sponsors', [])
    
    if not sponsors:
        await callback.message.edit_text(
            "📋 Список спонсоров пуст!\n\n"
            "Используйте '➕ Добавить спонсора' для добавления.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]
            )
        )
        await callback.answer()
        return
    
    text = "📋 <b>Список спонсоров:</b>\n\n"
    for idx, link in enumerate(sponsors, 1):
        text += f"{idx}. {link}\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_sponsors_list_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("sponsor_edit_"))
async def sponsor_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    idx = int(callback.data.split("_")[2])
    sponsors = config.get('sponsors', [])
    
    if idx >= len(sponsors):
        await callback.answer("❌ Спонсор не найден!")
        return
    
    await state.update_data(edit_index=idx)
    await callback.message.edit_text(
        f"✏️ Редактирование спонсора #{idx+1}\n\n"
        f"Текущая ссылка:\n{sponsors[idx]}\n\n"
        f"Введите новую ссылку или отправьте /cancel",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_edit_sponsor)
    await callback.answer()

@dp.message(AdminStates.waiting_for_edit_sponsor)
async def process_edit_sponsor(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        await message.answer("⛔ Доступ запрещен!")
        await state.clear()
        return
    
    data = await state.get_data()
    idx = data.get('edit_index')
    sponsors = config.get('sponsors', [])
    
    if idx is None or idx >= len(sponsors):
        await message.answer("❌ Ошибка: спонсор не найден", reply_markup=get_admin_panel())
        await state.clear()
        return
    
    new_link = message.text.strip()
    
    if not new_link.startswith(('https://t.me/', 'http://t.me/')):
        await message.answer(
            "❌ Неверный формат ссылки!\n"
            "Попробуйте снова или отправьте /cancel"
        )
        return
    
    config['sponsors'][idx] = new_link
    
    if save_config(config):
        await message.answer(
            f"✅ Ссылка обновлена!\n\n"
            f"Новая ссылка: {new_link}",
            reply_markup=get_admin_panel()
        )
    else:
        await message.answer("❌ Ошибка сохранения!", reply_markup=get_admin_panel())
    
    await state.clear()

@dp.callback_query(F.data.startswith("sponsor_delete_"))
async def sponsor_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    idx = int(callback.data.split("_")[2])
    sponsors = config.get('sponsors', [])
    
    if idx >= len(sponsors):
        await callback.answer("❌ Спонсор не найден!")
        return
    
    deleted = sponsors.pop(idx)
    config['min_clicks'] = len(sponsors)
    
    if save_config(config):
        await callback.answer(f"🗑 Ссылка удалена: {deleted[:30]}...")
        
        if sponsors:
            text = "📋 <b>Список спонсоров:</b>\n\n"
            for i, link in enumerate(sponsors, 1):
                text += f"{i}. {link}\n"
            
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_sponsors_list_keyboard()
            )
        else:
            await callback.message.edit_text(
                "📋 Список спонсоров пуст!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]
                )
            )
    else:
        await callback.answer("❌ Ошибка удаления!")

@dp.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "⚙️ <b>Настройки бота</b>\n\n"
        "Здесь вы можете просмотреть текущие параметры.\n"
        "Для изменения некоторых параметров используйте переменные в BotHost:",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_admin")
async def settings_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.answer(
        f"👑 Текущий админ: {ADMIN_ID or 'Не установлен'}\n\n"
        "Чтобы изменить админа, измените переменную ADMIN_ID\n"
        "в настройках BotHost и перезапустите бота.",
        show_alert=True
    )

@dp.callback_query(F.data == "settings_min_clicks")
async def settings_min_clicks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.answer(
        f"📌 Минимальное кол-во кликов: {config.get('min_clicks', 0)}\n"
        f"(Автоматически равно количеству спонсоров)",
        show_alert=True
    )

@dp.callback_query(F.data == "settings_sponsors_count")
async def settings_sponsors_count(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.answer(
        f"📢 Количество спонсоров: {len(config.get('sponsors', []))}",
        show_alert=True
    )

@dp.callback_query(F.data == "admin_modes")
async def admin_modes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    text = "📝 <b>Выберите режим сообщения</b>\n\n"
    text += "🔹 <b>Режим 1</b>: Стандартное сообщение\n"
    text += "🔹 <b>Режим 2</b>: С просьбой отправить скрин\n"
    text += "🔹 <b>Режим 3</b>: С явной ссылкой на админа\n\n"
    text += f"Текущий режим: <b>{config.get('mode', 1)}</b>"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_mode_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mode_set_"))
async def mode_set(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    mode = int(callback.data.split("_")[2])
    config['mode'] = mode
    
    if save_config(config):
        await callback.answer(f"✅ Режим {mode} установлен!")
        await admin_modes(callback)
    else:
        await callback.answer("❌ Ошибка сохранения!")

@dp.callback_query(F.data.startswith("mode_preview_"))
async def mode_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    mode = int(callback.data.split("_")[2])
    admin = ADMIN_ID or 'администратору'
    
    if mode == 1:
        msg = "✅ Бот активирован! Можете приступать к использованию."
    elif mode == 2:
        msg = f"✅ Бот активирован! Пожалуйста, сделайте скриншот и отправьте его {admin}"
    elif mode == 3:
        msg = f"✅ Бот активирован! Для подтверждения отправьте скриншот администратору: {admin}"
    else:
        msg = "✅ Бот активирован!"
    
    await callback.answer(f"📝 Режим {mode}:\n{msg}", show_alert=True)

# ================= ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ =================

@dp.callback_query(F.data == "activate")
async def activate_user(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    if user_data[user_id]['activated']:
        await callback.answer("✅ Бот уже активирован!")
        return
    
    sponsors = config.get('sponsors', [])
    if not sponsors:
        await callback.answer("⏳ Бот еще настраивается. Подождите.")
        return
    
    await callback.message.delete()
    await callback.message.answer(
        "📢 Подпишитесь на все каналы и нажмите 'Подтвердить'",
        reply_markup=get_activation_keyboard(len(sponsors))
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("sponsor_click_"))
async def process_sponsor_click(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    if user_data[user_id]['activated']:
        await callback.answer("⚠️ Бот уже активирован!")
        return
    
    idx = int(callback.data.split("_")[2])
    
    if idx not in user_data[user_id]['clicks']:
        user_data[user_id]['clicks'].add(idx)
        sponsors = config.get('sponsors', [])
        await callback.answer(
            f"✅ Канал {idx+1} отмечен! ({len(user_data[user_id]['clicks'])}/{len(sponsors)})"
        )
    else:
        await callback.answer("ℹ️ Вы уже кликали на этот канал")

@dp.callback_query(F.data == "confirm_subscribe")
async def confirm_subscribe(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    if user_data[user_id]['activated']:
        await callback.answer("⚠️ Бот уже активирован!")
        return
    
    clicks = len(user_data[user_id]['clicks'])
    sponsors = config.get('sponsors', [])
    required = len(sponsors)
    
    if required == 0:
        await callback.answer("⏳ Бот еще настраивается. Подождите.")
        return
    
    if clicks >= required:
        user_data[user_id]['activated'] = True
        
        mode = config.get('mode', 1)
        admin = ADMIN_ID or 'администратору'
        
        if mode == 1:
            msg = "✅ Бот активирован! Можете приступать к использованию."
        elif mode == 2:
            msg = f"✅ Бот активирован! Пожалуйста, сделайте скриншот и отправьте его {admin}"
        elif mode == 3:
            msg = f"✅ Бот активирован! Для подтверждения отправьте скриншот администратору: {admin}"
        else:
            msg = "✅ Бот активирован!"
        
        await callback.message.delete()
        await callback.message.answer(msg)
        
        # Уведомление админу
        try:
            if ADMIN_ID:
                await bot.send_message(
                    ADMIN_ID,
                    f"🔔 <b>Новая активация!</b>\n\n"
                    f"👤 Пользователь: {callback.from_user.full_name}\n"
                    f"🆔 Username: @{callback.from_user.username or 'Нет юзернейма'}\n"
                    f"🆔 ID: <code>{callback.from_user.id}</code>\n"
                    f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                    parse_mode="HTML"
                )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление админу: {e}")
        
        await callback.answer("🎉 Активация успешна!")
    else:
        await callback.answer(
            f"❌ Вы отметили только {clicks} из {required} каналов!\n"
            f"Пожалуйста, пройдите по всем ссылкам.",
            show_alert=True
        )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    
    if is_admin(message.from_user.id):
        await message.answer(
            "❌ Действие отменено",
            reply_markup=get_admin_panel()
        )
    else:
        await message.answer("❌ Действие отменено")

# ================= ЗАПУСК =================
async def main():
    print("=" * 50)
    print("🚀 Telegram Activation Bot")
    print("=" * 50)
    print(f"👑 Админ ID: {ADMIN_ID or '❌ НЕ УСТАНОВЛЕН'}")
    print(f"📢 Спонсоров: {len(config.get('sponsors', []))}")
    print(f"📝 Режим: {config.get('mode', 1)}")
    print(f"📁 Конфиг: {CONFIG_FILE}")
    print("=" * 50)
    
    if not ADMIN_ID:
        print("⚠️ ВНИМАНИЕ: ADMIN_ID не установлен!")
        print("Добавьте переменную ADMIN_ID в настройках BotHost")
        print("Узнать свой ID можно командой /id в боте")
        print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

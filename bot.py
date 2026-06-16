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

# ================= КОНФИГУРАЦИЯ =================
API_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CONFIG_FILE = os.getenv('CONFIG_FILE', 'config.json')

# Настройки по умолчанию
DEFAULT_CONFIG = {
    "mode": 1,
    "sponsors": [],
    "admin_id": None,
    "min_clicks": 0
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
    """Загружает конфиг из файла или переменных окружения"""
    config = DEFAULT_CONFIG.copy()
    
    # Пробуем загрузить из файла
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
                logging.info(f"Конфиг загружен из файла: {CONFIG_FILE}")
        except Exception as e:
            logging.error(f"Ошибка загрузки конфига из файла: {e}")
    
    # Переменные окружения имеют приоритет
    if 'BOT_CONFIG' in os.environ:
        try:
            env_config = json.loads(os.environ['BOT_CONFIG'])
            config.update(env_config)
            logging.info("Конфиг загружен из переменной BOT_CONFIG")
        except Exception as e:
            logging.error(f"Ошибка загрузки конфига из переменных: {e}")
    
    return config

def save_config(config):
    """Сохраняет конфиг в файл"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logging.info(f"Конфиг сохранен в файл: {CONFIG_FILE}")
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения конфига: {e}")
        return False

config = load_config()

# ================= СОСТОЯНИЯ FSM =================
class AdminStates(StatesGroup):
    waiting_for_admin_id = State()
    waiting_for_sponsor_link = State()
    waiting_for_edit_sponsor = State()

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
        [InlineKeyboardButton(text="🔙 Выйти из админки", callback_data="admin_exit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_sponsors_list_keyboard():
    """Клавиатура со списком спонсоров"""
    keyboard = []
    
    for idx, sponsor in enumerate(config['sponsors'], 1):
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_settings_keyboard():
    """Клавиатура настроек"""
    min_clicks = config.get('min_clicks', 0)
    keyboard = [
        [InlineKeyboardButton(
            text=f"📌 Мин. кликов: {min_clicks}",
            callback_data="settings_min_clicks"
        )],
        [InlineKeyboardButton(
            text=f"👑 Админ: {config.get('admin_id', 'Не установлен')}",
            callback_data="settings_admin_id"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_activation_keyboard(sponsors_count):
    """Клавиатура активации"""
    keyboard = []
    
    for idx, link in enumerate(config['sponsors'], 1):
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 Канал {idx}",
                callback_data=f"sponsor_click_{idx-1}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="✅ Подтвердить подписку",
            callback_data="confirm_subscribe"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================= ПРОВЕРКА АДМИНА =================
def is_admin(user_id):
    admin_id = config.get('admin_id')
    if not admin_id:
        return False
    return str(user_id) == str(admin_id)

# ================= ОБРАБОТЧИКИ =================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    if is_admin(user_id):
        await message.answer(
            "👋 Добро пожаловать в админ-панель!",
            reply_markup=get_admin_panel()
        )
    else:
        if user_data[user_id]['activated']:
            await message.answer("✅ Бот уже активирован!")
            return
        
        if not config['sponsors']:
            await message.answer("⏳ Бот еще настраивается. Подождите.")
            return
        
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для активации нажмите на все кнопки ниже и 'Подтвердить'.",
            reply_markup=get_activation_keyboard(len(config['sponsors']))
        )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!")
        return
    
    await message.answer(
        "🔐 Админ-панель",
        reply_markup=get_admin_panel()
    )

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔐 Админ-панель",
        reply_markup=get_admin_panel()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery):
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
    
    stats_text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"✅ Активировано: <b>{activated}</b>\n"
        f"📢 Спонсоров: <b>{len(config['sponsors'])}</b>\n"
        f"📝 Режим: <b>{config.get('mode', 1)}</b>\n"
        f"👑 Админ: <b>{config.get('admin_id', 'Не установлен')}</b>"
    )
    
    await callback.message.edit_text(stats_text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_add_sponsor")
async def admin_add_sponsor(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "📝 Введите ссылку на канал:\n"
        "Пример: https://t.me/channel_name\n\n"
        "<i>Отмена: /cancel</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_sponsor_link)
    await callback.answer()

@dp.message(AdminStates.waiting_for_sponsor_link)
async def process_sponsor_link(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!")
        await state.clear()
        return
    
    link = message.text.strip()
    
    if not link.startswith(('https://t.me/', 'http://t.me/')):
        await message.answer("❌ Неверный формат! Ссылка должна начинаться с https://t.me/")
        return
    
    config['sponsors'].append(link)
    config['min_clicks'] = len(config['sponsors'])
    
    if save_config(config):
        await message.answer(
            f"✅ Ссылка добавлена!\nВсего: {len(config['sponsors'])}",
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
    
    if not config['sponsors']:
        await callback.message.edit_text(
            "📋 Список пуст!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]
            )
        )
        await callback.answer()
        return
    
    text = "📋 <b>Список спонсоров:</b>\n\n"
    for idx, link in enumerate(config['sponsors'], 1):
        text += f"{idx}. {link}\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_sponsors_list_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("sponsor_delete_"))
async def sponsor_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    idx = int(callback.data.split("_")[2])
    if idx >= len(config['sponsors']):
        await callback.answer("❌ Не найден!")
        return
    
    config['sponsors'].pop(idx)
    config['min_clicks'] = len(config['sponsors'])
    
    if save_config(config):
        await callback.answer("🗑 Удалено!")
        await admin_list_sponsors(callback)
    else:
        await callback.answer("❌ Ошибка!")

@dp.callback_query(F.data.startswith("sponsor_edit_"))
async def sponsor_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    idx = int(callback.data.split("_")[2])
    await state.update_data(edit_index=idx)
    
    await callback.message.edit_text(
        f"✏️ Редактирование #{idx+1}\n\n"
        f"Текущая: {config['sponsors'][idx]}\n\n"
        f"Введите новую ссылку",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_edit_sponsor)
    await callback.answer()

@dp.message(AdminStates.waiting_for_edit_sponsor)
async def process_edit_sponsor(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!")
        await state.clear()
        return
    
    data = await state.get_data()
    idx = data.get('edit_index')
    
    if idx is None or idx >= len(config['sponsors']):
        await message.answer("❌ Ошибка!", reply_markup=get_admin_panel())
        await state.clear()
        return
    
    new_link = message.text.strip()
    
    if not new_link.startswith(('https://t.me/', 'http://t.me/')):
        await message.answer("❌ Неверный формат!")
        return
    
    config['sponsors'][idx] = new_link
    
    if save_config(config):
        await message.answer("✅ Обновлено!", reply_markup=get_admin_panel())
    else:
        await message.answer("❌ Ошибка!", reply_markup=get_admin_panel())
    
    await state.clear()

@dp.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "settings_admin_id")
async def settings_admin_id(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    await callback.message.edit_text(
        "👑 Введите ID администратора:\n"
        "Пример: 123456789 или @username\n\n"
        "<i>Отмена: /cancel</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_admin_id)
    await callback.answer()

@dp.message(AdminStates.waiting_for_admin_id)
async def process_admin_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!")
        await state.clear()
        return
    
    admin_id = message.text.strip()
    
    if not (admin_id.isdigit() or admin_id.startswith('@')):
        await message.answer("❌ Неверный формат!")
        return
    
    config['admin_id'] = admin_id
    
    if save_config(config):
        await message.answer(f"✅ Админ установлен: {admin_id}", reply_markup=get_admin_panel())
    else:
        await message.answer("❌ Ошибка!", reply_markup=get_admin_panel())
    
    await state.clear()

@dp.callback_query(F.data == "admin_modes")
async def admin_modes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return
    
    text = "📝 <b>Выберите режим</b>\n\n"
    text += "1: Стандартное сообщение\n"
    text += "2: С просьбой о скрине\n"
    text += "3: С ссылкой на админа\n\n"
    text += f"Текущий: <b>{config.get('mode', 1)}</b>"
    
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
        await callback.answer("❌ Ошибка!")

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
        await callback.answer(
            f"✅ Канал {idx+1} отмечен! ({len(user_data[user_id]['clicks'])}/{len(config['sponsors'])})"
        )
    else:
        await callback.answer("ℹ️ Уже кликали")

@dp.callback_query(F.data == "confirm_subscribe")
async def confirm_subscribe(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {'clicks': set(), 'activated': False}
    
    if user_data[user_id]['activated']:
        await callback.answer("⚠️ Бот уже активирован!")
        return
    
    clicks = len(user_data[user_id]['clicks'])
    required = len(config['sponsors'])
    
    if clicks >= required and required > 0:
        user_data[user_id]['activated'] = True
        
        mode = config.get('mode', 1)
        admin = config.get('admin_id', 'администратору')
        
        if mode == 1:
            msg = "✅ Бот активирован!"
        elif mode == 2:
            msg = f"✅ Бот активирован! Отправьте скриншот {admin}"
        elif mode == 3:
            msg = f"✅ Бот активирован! Отправьте скриншот: {admin}"
        else:
            msg = "✅ Бот активирован!"
        
        await callback.message.delete()
        await callback.message.answer(msg)
        
        # Уведомление админу
        try:
            admin_id = config.get('admin_id')
            if admin_id:
                await bot.send_message(
                    admin_id,
                    f"🔔 Новая активация!\n"
                    f"👤 {callback.from_user.full_name}\n"
                    f"🆔 @{callback.from_user.username or 'Нет юзернейма'}"
                )
        except:
            pass
        
        await callback.answer("🎉 Активация успешна!")
    else:
        await callback.answer(
            f"❌ Отмечено {clicks} из {required} каналов!",
            show_alert=True
        )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено")

# ================= ЗАПУСК =================
async def main():
    print("🚀 Бот запущен!")
    print(f"📊 Режим: {config.get('mode', 1)}")
    print(f"📢 Спонсоров: {len(config['sponsors'])}")
    print(f"👑 Админ: {config.get('admin_id', 'Не установлен')}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

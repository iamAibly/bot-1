# bot.py
import os
import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ================= КОНФИГУРАЦИЯ (РЕЖИМЫ) =================
# Режим 1: Стандартное сообщение об активации
# Режим 2: Сообщение с просьбой отправить скрин админу
# Режим 3: Сообщение с ссылкой на админа и просьбой о скрине

MODE_MESSAGES = {
    1: "✅ Бот активирован! Можете приступать к использованию.",
    2: "✅ Бот активирован! Пожалуйста, сделайте скриншот и отправьте его админу @admin",
    3: "✅ Бот активирован! Для подтверждения отправьте скриншот администратору: @admin"
}

# Настройки по умолчанию (будут перезаписаны из переменных BotHost)
DEFAULT_CONFIG = {
    "mode": 1,                  # Режим сообщения (1, 2 или 3)
    "sponsors": [               # Список каналов/ссылок для подписки
        "https://t.me/channel1",
        "https://t.me/channel2",
        "https://t.me/channel3"
    ],
    "admin_id": "admin",        # ID или юзернейм админа
    "min_clicks": 3,            # Минимальное количество кликов для активации (обычно = кол-ву спонсоров)
    "activation_text": "🎉 Поздравляем! Вы успешно активировали бота."
}

# ================= ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ BOTHOST =================
def load_config():
    """Загружает конфиг из переменных BotHost или из локального файла"""
    config = DEFAULT_CONFIG.copy()
    
    # Попытка загрузить из переменных BotHost
    if 'BOTHOST_VARS' in os.environ:
        try:
            vars_data = json.loads(os.environ['BOTHOST_VARS'])
            if 'bot_config' in vars_data:
                config.update(json.loads(vars_data['bot_config']))
        except:
            pass
    
    # Если нет переменных, пробуем загрузить из локального файла (для тестов)
    elif os.path.exists('config.json'):
        with open('config.json', 'r') as f:
            config.update(json.load(f))
    
    return config

# ================= ИНИЦИАЛИЗАЦИЯ =================
API_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
config = load_config()

logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# ================= СОСТОЯНИЯ FSM =================
class ActivationStates(StatesGroup):
    waiting_for_confirm = State()

# ================= ХРАНИЛИЩЕ ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ =================
# В реальном проекте лучше использовать БД, но для примера - словарь
user_data = {}

# ================= КЛАВИАТУРЫ =================
def get_sponsors_keyboard():
    """Генерирует клавиатуру со спонсорами"""
    keyboard = []
    for idx, link in enumerate(config['sponsors'], 1):
        keyboard.append([
            InlineKeyboardButton(
                text=f"📢 Подписаться на канал {idx}", 
                url=link
            )
        ])
    
    # Кнопка подтверждения
    keyboard.append([
        InlineKeyboardButton(
            text="✅ Подтвердить подписку", 
            callback_data="confirm_subscribe"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================= ОБРАБОТЧИКИ КОМАНД =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    
    # Инициализация пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'clicks': 0,
            'activated': False,
            'clicked_links': set()
        }
    
    # Проверка, активирован ли уже
    if user_data[user_id]['activated']:
        await message.answer("⚠️ Вы уже активировали бота.")
        return
    
    # Приветственное сообщение с клавиатурой
    welcome_text = (
        "👋 Добро пожаловать!\n\n"
        "Для активации бота необходимо подписаться на все каналы ниже "
        "и нажать кнопку 'Подтвердить подписку'.\n\n"
        f"📌 Всего каналов: {len(config['sponsors'])}"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_sponsors_keyboard()
    )

@dp.callback_query(F.data.startswith("sponsor_"))
async def process_sponsor_click(callback: types.CallbackQuery):
    """Обработчик кликов по спонсорским ссылкам"""
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        await callback.answer("❌ Пожалуйста, начните с команды /start")
        return
    
    if user_data[user_id]['activated']:
        await callback.answer("⚠️ Бот уже активирован")
        return
    
    # Получаем индекс спонсора из callback_data
    idx = int(callback.data.split("_")[1])
    
    # Проверяем, кликал ли уже пользователь на эту ссылку
    if idx not in user_data[user_id]['clicked_links']:
        user_data[user_id]['clicked_links'].add(idx)
        user_data[user_id]['clicks'] += 1
        
        await callback.answer(f"✅ Ссылка {idx} отмечена! ({user_data[user_id]['clicks']}/{len(config['sponsors'])})")
    else:
        await callback.answer("ℹ️ Вы уже кликали на эту ссылку")

@dp.callback_query(F.data == "confirm_subscribe")
async def process_confirm(callback: types.CallbackQuery):
    """Обработчик подтверждения подписки"""
    user_id = str(callback.from_user.id)
    
    if user_id not in user_data:
        await callback.answer("❌ Пожалуйста, начните с команды /start")
        return
    
    if user_data[user_id]['activated']:
        await callback.answer("⚠️ Бот уже активирован")
        return
    
    # Проверяем количество кликов
    clicks = user_data[user_id]['clicks']
    required = len(config['sponsors'])  # Или config['min_clicks']
    
    if clicks >= required:
        # Активируем пользователя
        user_data[user_id]['activated'] = True
        
        # Выбираем сообщение в зависимости от режима
        mode = config.get('mode', 1)
        admin = config.get('admin_id', '@admin')
        
        # Формируем сообщение с учетом режима
        if mode == 1:
            msg = "✅ Бот активирован! Можете приступать к использованию."
        elif mode == 2:
            msg = f"✅ Бот активирован! Пожалуйста, сделайте скриншот и отправьте его админу {admin}"
        elif mode == 3:
            msg = f"✅ Бот активирован! Для подтверждения отправьте скриншот администратору: {admin}"
        else:
            msg = MODE_MESSAGES.get(mode, "✅ Бот активирован!")
        
        # Отправляем сообщение
        await callback.message.delete()
        await callback.message.answer(msg)
        
        # Уведомление админу (опционально)
        try:
            await bot.send_message(
                admin if admin.startswith('@') else admin,
                f"🔔 Пользователь {callback.from_user.full_name} (@{callback.from_user.username}) активировал бота!"
            )
        except:
            pass
        
        await callback.answer("🎉 Активация успешна!")
    else:
        await callback.answer(
            f"❌ Вы подписались только на {clicks} из {required} каналов.\n"
            f"Пожалуйста, подпишитесь на все каналы и нажмите подтвердить снова.",
            show_alert=True
        )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Админ-панель (только для админа)"""
    admin_id = config.get('admin_id', 'admin')
    user_id = str(message.from_user.id)
    
    # Простая проверка (можно улучшить)
    if user_id != admin_id and f"@{user_id}" != admin_id:
        await message.answer("⛔ Доступ запрещен")
        return
    
    stats = f"📊 Статистика бота:\n\n"
    stats += f"👥 Всего пользователей: {len(user_data)}\n"
    stats += f"✅ Активировано: {sum(1 for u in user_data.values() if u['activated'])}\n"
    stats += f"📝 Режим: {config.get('mode', 1)}\n"
    stats += f"📢 Каналов: {len(config['sponsors'])}"
    
    await message.answer(stats)

# ================= ЗАПУСК =================
async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

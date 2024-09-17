import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import asyncio
import asyncpg
import re  # Додано для перевірки адрес гаманців

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Telegram bot token
API_TOKEN = '7262008673:AAG3sP9XN2q4oVAGRz4TnKbt7N3rZiMqD6k'  # Замініть на ваш токен бота

# Налаштування бази даних
DB_CONFIG = {
    'user': 'mycomp1',
    'password': 'Matrix89',
    'database': 'matrix89',
    'host': '127.0.0.1',
    'port': 5432,
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Список каналів для перевірки
CHANNELS = [
    '@Vexelman_W3B', '@W3B_Digest', '@W3B_Education', '@vexel_token', 
    '@W3B_Events', '@W3B_Signals', '@W3B_RWA_RealWorldAssets', '@w3b_otc', 
    '@W3B_Invest', '@w3b_farm', '@W3B_Charity', '@W3B_Ventures', 
    '@crypto_liquid_loan', '@W3B_Games', '@W3B_Selection', '@crypto_scam_detect', 
    '@W3B_Algo'
]


# Створення клавіатур
daily_button = InlineKeyboardButton(text='🎁 DAILY', callback_data='daily')
referral_button = InlineKeyboardButton(text='👥 Реферали', callback_data='referrals')
wallet_button = InlineKeyboardButton(text='👛 Підключення гаманця', callback_data='wallet')
tasks_button = InlineKeyboardButton(text='📋 Завдання', callback_data='tasks')  # Нова кнопка "Завдання"

main_menu = InlineKeyboardMarkup(inline_keyboard=[[daily_button], [referral_button], [wallet_button], [tasks_button]])

# Клавіатура для кнопки "Назад" з вкладки "Завдання"
back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
tasks_menu = InlineKeyboardMarkup(inline_keyboard=[[back_button]])

# Зберігання ID поточного і попереднього повідомлень, тексту і клавіатури для кожного користувача
user_messages = {}  # {'user_id': {'current': <message_id>, 'previous': <message_id>, 'text': <text>, 'markup': <markup>}}

async def create_pool():
    return await asyncpg.create_pool(**DB_CONFIG)

async def add_user(pool, user_id, referrer_id=None):
    async with pool.acquire() as connection:
        await connection.execute("""
            INSERT INTO users (user_id, last_claim, streak, balance, referrals, referrer_id, referral_bonus, wallet)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id) DO NOTHING
        """, int(user_id), datetime.now() - timedelta(days=1), 0, 0, 0, int(referrer_id) if referrer_id else None, 0, None)

async def get_user(pool, user_id):
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            "SELECT last_claim, streak, balance, referrals, referrer_id, referral_bonus, wallet FROM users WHERE user_id = $1",
            int(user_id)
        )

async def update_user(pool, user_id, last_claim=None, streak=None, balance=None, referrals=None, referral_bonus=None, wallet=None):
    async with pool.acquire() as connection:
        query = "UPDATE users SET"
        params = []
        counter = 1

        if last_claim is not None:
            query += f" last_claim = ${counter},"
            params.append(last_claim)
            counter += 1
        if streak is not None:
            query += f" streak = ${counter},"
            params.append(int(streak))
            counter += 1
        if balance is not None:
            query += f" balance = ${counter},"
            params.append(float(balance))
            counter += 1
        if referrals is not None:
            query += f" referrals = ${counter},"
            params.append(int(referrals))
            counter += 1
        if referral_bonus is not None:
            query += f" referral_bonus = ${counter},"
            params.append(float(referral_bonus))
            counter += 1
        if wallet is not None:
            query += f" wallet = ${counter},"
            params.append(wallet)
            counter += 1

        query = query.rstrip(",")
        query += f" WHERE user_id = ${counter}"
        params.append(int(user_id))

        await connection.execute(query, *params)

# Генерація реферального посилання
def generate_referral_link(user_id):
    return f"https://t.me/VEXELtokenbot?start={user_id}"

# Функція для перевірки валідності TON гаманця
def validate_wallet(wallet_address):
    # Перевірка для TON-адрес, що починаються з 'EQ', 'UQ', або інших варіацій і мають 48 символів
    return bool(re.match(r'^[A-Za-z0-9_-]{48}$', wallet_address))

# Функція для редагування повідомлення, якщо його зміст або клавіатура змінюються
async def edit_message_if_changed(chat_id, message_id, new_text, new_markup):
    user_data = user_messages.get(chat_id, {})
    current_text = user_data.get("text", "")
    current_markup = user_data.get("markup", None)

    # Перевіряємо, чи змінюється текст або розмітка
    if current_text != new_text or current_markup != new_markup:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            parse_mode='Markdown',
            reply_markup=new_markup
        )
        # Оновлюємо дані в user_messages після редагування
        user_data["text"] = new_text
        user_data["markup"] = new_markup

# Функція для перевірки підписки на всі канали
async def is_user_subscribed(user_id):
    subscribed_to_all = True
    for channel in CHANNELS:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ['member', 'administrator', 'creator']:
                subscribed_to_all = False
                break
        except Exception as e:
            logging.error(f"Помилка перевірки для каналу {channel}: {e}")
            subscribed_to_all = False
            break

    # Після перевірки оновлюємо статус в базі
    pool = await create_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE users SET is_subscribed = $1 WHERE user_id = $2",
            subscribed_to_all, user_id
        )
    await pool.close()

    return subscribed_to_all

# Оновлення бази даних для зберігання статусу підписки
async def update_subscription_status(user_id):
    is_subscribed = await is_user_subscribed(user_id)
    pool = await create_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE users SET is_subscribed = $1 WHERE user_id = $2",
            is_subscribed, user_id
        )
    await pool.close()

# Додаємо функцію для перевірки груп, де бот доданий
async def check_group_presence():
    group_list = []
    for group_name in CHANNELS:
        try:
            chat = await bot.get_chat(group_name)
            group_list.append(chat)
        except Exception as e:
            logging.error(f"Не вдалося отримати інформацію про групу {group_name}: {e}")
    return group_list

# Функція для аналізу наявності певних назв
async def check_group_for_name(target_names):
    group_list = await check_group_presence()
    found_groups = []

    for group in group_list:
        for name in target_names:
            if name.lower() in group.title.lower():
                found_groups.append(group.title)
    
    if found_groups:
        logging.info(f"Знайдено групи: {', '.join(found_groups)}")
    else:
        logging.info("Жодної з вказаних назв не знайдено.")
    return found_groups

# Хендлер для команди /check_names
@dp.message(F.text.startswith('/check_names'))
async def check_names_in_groups(message: types.Message):
    target_names = ['W3B | Chat', 'Vexelman | W3B 💹', 'W3B | Digest', 'W3B | Education', '$VEXEL', 'W3B | Charity', 'Crypto Credit | Liquid Loan', 'W3B | Games', 'W3B | Investment', 'W3B | Signals', 'W3B | Algotrading', 'OTC💱P2P', 'W3B | Ventures', 'W3B | Real World Assets', 'W3B | Events', 'W3B | Selection', '⛔️SСАМ Detect', 'W3B | Mining + Farming']  # Замініть на потрібні назви
    found_groups = await check_group_for_name(target_names)
    
    if found_groups:
        await message.answer(f"Знайдено групи з вашими назвами: {', '.join(found_groups)}")
    else:
        await message.answer("Жодної з вказаних назв не знайдено.")

# Хендлер для команди /start
@dp.message(F.text.startswith('/start'))
async def start(message: types.Message):
    pool = await create_pool()
    user_id = message.from_user.id
    referrer_id = None

    if len(message.text.split()) > 1:
        referrer_id = int(message.text.split()[1])  # Отримуємо реферальний ID

    existing_user = await get_user(pool, user_id)
    if existing_user is None:
        await add_user(pool, user_id, referrer_id)
        if referrer_id:
            referrer = await get_user(pool, referrer_id)
            if referrer:
                new_balance = referrer['balance'] + 10000  # Нараховуємо бонус за реферала
                new_referrals = referrer['referrals'] + 1
                new_referral_bonus = referrer['referral_bonus'] + 10000
                await update_user(pool, referrer_id, balance=new_balance, referrals=new_referrals, referral_bonus=new_referral_bonus)

    await pool.close()

    response_text = "👋 Привіт! \n🎁 Натискай на кнопку 'DAILY' і збирай свої нагороди щодня! 💰"
    welcome_message = await message.answer(response_text, reply_markup=main_menu)

    user_messages[user_id] = {
        "current": welcome_message.message_id, 
        "previous": None, 
        "text": response_text, 
        "markup": main_menu
    }

@dp.callback_query(F.data == 'daily')
async def daily_claim(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    pool = await create_pool()
    user = await get_user(pool, user_id)

    if user:
        last_claim, streak, balance = user['last_claim'], user['streak'], user['balance']
        now = datetime.now()

        if now - last_claim < timedelta(hours=24):
            response_text = f"⚠️ Ти вже отримав свою нагороду сьогодні! 🕒 Почекай ще трохи... \n\n💰 Твій поточний баланс: {balance} токенів. \n⏳ Повторити можна через 24 години."
        else:
            reward = random.randint(50, 120)
            if streak == 6:
                reward *= 4
                streak = 0
                response_text = f"🎉 Ура! Ти зірвав джекпот на 7-й день! 🔥 Сьогодні ти отримуєш аж `{reward} токенів!`"
            else:
                streak += 1
                response_text = f"🎁 Ще одна перемога! \nТвоя сьогоднішня нагорода: `{reward} токенів!`"
            balance += reward
            await update_user(pool, user_id, last_claim=now, streak=streak, balance=balance)

        response_text += f"\n\n 🤑 Продовжуй збирати щоденні бонуси!"

        # Додайте більше логів для перевірки
        print(f"Editing message for user {user_id}, current_message_id: {user_messages[user_id].get('current')}")
        
        if user_id in user_messages:
            current_message_id = user_messages[user_id].get('current')
            if current_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=callback_query.message.chat.id,
                        message_id=current_message_id,
                        text=response_text,
                        reply_markup=main_menu
                    )
                except Exception as e:
                    print(f"Error editing message: {e}")

    await pool.close()



    
# Хендлер Реферали👥 
@dp.callback_query(F.data == 'referrals')
async def referral_info(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        pool = await create_pool()
        user = await get_user(pool, user_id)
        if user:
            referrals = user['referrals']
            referral_bonus = user['referral_bonus']
            referral_link = generate_referral_link(user_id)

            response_text = (
                f"👥 **Твоя реферальна статистика:**\n➖➖➖➖➖➖➖➖➖➖\n"
                f"👤 **Запрошено друзів**: {referrals}\n"
                f"💸 **Отримано за рефералів**: {referral_bonus} токенів\n➖➖➖➖➖➖➖➖➖➖\n"
                f"🔗 **Твоє реферальне посилання**:\n\n"
                f"{referral_link}\n➖➖➖➖➖➖➖➖➖➖\n"
                f"🎯 Запроси своїх друзів та отримай 10,000 токенів за кожного! "
                f"Якщо вони почнуть натискати кнопку '🎁 DAILY', ти отримаєш винагороду! 💰"
            )

            back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
            referral_menu = InlineKeyboardMarkup(inline_keyboard=[[back_button]])

            await bot.edit_message_text(
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                text=response_text,
                parse_mode='Markdown',
                reply_markup=referral_menu
            )

            user_messages[user_id]["previous"] = user_messages[user_id]["current"]
        await pool.close()
    except Exception as e:
        logging.error(f"Помилка обробки кнопки 'Реферали': {e}")


# Хендлер для кнопки '👛 Підключення гаманця'
@dp.callback_query(F.data == 'wallet')
async def wallet_connect(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    pool = await create_pool()
    user = await get_user(pool, user_id)
    wallet_address = user['wallet'] if user else None

    if wallet_address:
        response_text = (
            f"✅ **Ваш гаманець підключений:**\n`{wallet_address}`\n\n"
            "Якщо хочете змінити гаманець, введіть нову адресу або натисніть 'Редагувати'."
        )
        edit_button = InlineKeyboardButton(text='✏️ Редагувати гаманець', callback_data='edit_wallet')
        back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
        wallet_menu = InlineKeyboardMarkup(inline_keyboard=[[edit_button], [back_button]])
    else:
        response_text = (
            "❌ **Ваш гаманець не підключений.**\n\n"
            "Введіть адресу свого TON гаманця:\n"
            "`EQxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n"
            "або\n"
            "`UQxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`"
        )
        connect_button = InlineKeyboardButton(text='🔗 Підключити гаманець', callback_data='edit_wallet')
        back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
        wallet_menu = InlineKeyboardMarkup(inline_keyboard=[[connect_button], [back_button]])

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=response_text,
        parse_mode='Markdown',
        reply_markup=wallet_menu
    )

    await pool.close()

# Хендлер для редагування або підключення гаманця
@dp.callback_query(F.data == 'edit_wallet')
async def wallet_edit(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    response_text = "✏️ Введіть нову адресу свого TON гаманця."
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=response_text,
        parse_mode='Markdown'
    )

    user_messages[user_id] = user_messages.get(user_id, {})
    user_messages[user_id]["editing_wallet"] = True

# Хендлер для збереження нового гаманця
@dp.message(F.text)
async def wallet_save(message: types.Message):
    user_id = message.from_user.id
    wallet_address = message.text.strip()

    try_again_button = InlineKeyboardButton(text='🔄 Спробувати знову', callback_data='edit_wallet')
    back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
    error_wallet_menu = InlineKeyboardMarkup(inline_keyboard=[[try_again_button], [back_button]])

    if user_id in user_messages and user_messages[user_id].get("editing_wallet"):
        if validate_wallet(wallet_address):
            pool = await create_pool()
            await update_user(pool, user_id, wallet=wallet_address)
            await pool.close()

            response_text = f"✅ **Ваш гаманець оновлено:**\n`{wallet_address}`"
            await message.answer(response_text, parse_mode='Markdown')

            response_text = (
                f"✅ **Ваш гаманець підключений:**\n`{wallet_address}`\n\n"
                "Якщо хочете змінити гаманець, введіть нову адресу або натисніть 'Редагувати'."
            )
            edit_button = InlineKeyboardButton(text='✏️ Редагувати гаманець', callback_data='edit_wallet')
            back_button = InlineKeyboardButton(text='🔙 Назад до головного меню', callback_data='back_to_main')
            wallet_menu = InlineKeyboardMarkup(inline_keyboard=[[edit_button], [back_button]])

            await bot.send_message(message.chat.id, response_text, parse_mode='Markdown', reply_markup=wallet_menu)

            user_messages[user_id]["editing_wallet"] = False
        else:
            response_text = (
                "❌ **Некоректна адреса гаманця.**\n"
                "Будь ласка, введіть правильну адресу TON гаманця.\n"
                "Натисніть 'Спробувати знову' для повторної спроби або 'Назад' для виходу."
            )
            await message.answer(response_text, parse_mode='Markdown', reply_markup=error_wallet_menu)

# Хендлер для кнопки '🔙 Назад до головного меню'
@dp.callback_query(F.data == 'back_to_main')
async def back_to_main_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    response_text = "👋 Привіт! \n🎁 Натискай на кнопку 'DAILY' і збирай свої нагороди щодня! 💰"
    
    # Оновлюємо current ID повідомлення
    if user_id in user_messages:
        user_messages[user_id]["previous"] = user_messages[user_id]["current"]
        user_messages[user_id]["current"] = callback_query.message.message_id

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=response_text,
        reply_markup=main_menu
    )



# Хендлер для кнопки '📋 Завдання'
@dp.callback_query(F.data == 'tasks')
async def check_subscription(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    subscribed = await is_user_subscribed(user_id)

    activity_message = (
        "🚀 **Щоб отримати максимум від нашого бота, будьте активними на наших каналах!**\n\n"
        "Пам’ятайте, активність на каналах — це ваш шлях до більших нагород:\n\n"
        "1. **Ставте реакції:** реагуйте на публікації та поділіться своєю думкою.\n"
        "2. **Коментуйте:** залишайте коментарі під постами.\n"
        "3. **Репостіть:** діліться цікавими публікаціями з друзями.\n\n"
        "📊 **Чому це важливо?**\n\n"
        "- Ваші дії допомагають заробити більше токенів.\n"
        "- За активність ви можете отримувати додаткові бонуси.\n"
        "- Ми слідкуємо за вашим активом.\n\n"
        "Чим активніші ви на каналах, тим більше можливостей для вас! 🎉"
    )

    if subscribed:
        response_text = "✅ Ви підписані на всі необхідні канали!\n\n" + activity_message
    else:
        response_text = (
            "❌ Ви не підписані на всі необхідні канали. Будь ласка, підпишіться на всі канали за посиланням: "
            "[Підписатися](https://t.me/addlist/XfraDnp2lr01Yzcy)\n\n" + activity_message
        )

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=response_text,
        parse_mode='Markdown',
        reply_markup=tasks_menu
    )

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

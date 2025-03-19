import json
import logging
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect('tool_rental.db', check_same_thread=False)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    username TEXT,
                    orders_count INTEGER DEFAULT 0,
                    total_spent REAL DEFAULT 0.0,
                    join_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_admin INTEGER DEFAULT 0)''')
    
    # Таблица заказов
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    items TEXT NOT NULL,
                    date TEXT NOT NULL,
                    total REAL NOT NULL,
                    address TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Таблица инструментов
    c.execute('''CREATE TABLE IF NOT EXISTS tools (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    description TEXT,
                    image TEXT,
                    available INTEGER DEFAULT 1)''')
    
    # Индексы для оптимизации
    c.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_id ON users (id)')
    
    # Добавление начальных данных (10 реальных инструментов)
    c.execute('SELECT COUNT(*) FROM tools')
    if c.fetchone()[0] == 0:
        initial_tools = [
            ("tool1", "Дрель Bosch GSB 13 RE", 20.0, "Компактная дрель с ударом", "https://www.bosch-professional.com/by/media/images/GSB_13_RE_Professional_product_main_1200x1200.png", 1),
            ("tool2", "Шуруповерт Makita DF331D", 15.0, "Легкий и мощный шуруповерт", "https://cdn.makitatools.com/media/catalog/product/cache/1/image/9df78eab33525d08d6e5fb8d27136e95/d/f/df331d_1.jpg", 1),
            ("tool3", "Болгарка DeWalt DWE4233", 30.0, "Угловая шлифовальная машина", "https://www.dewalt.com/NAG/PRODUCT/IMAGES/HIRES/DWE4233/DWE4233_1.jpg?resize=530,530", 1),
            ("tool4", "Перфоратор Hilti TE 30-AVR", 40.0, "Мощный перфоратор для бетона", "https://www.hilti.by/medias/sys_master/images/hb3/hc9/9792581132318/TE-30-AVR-110V-2119170-Main-Image-Product-Image-518x345.jpg", 1),
            ("tool5", "Лобзик Festool PS 420", 25.0, "Точный лобзик для резки", "https://www.festoolusa.com/-/media/festool/us/products/cordless-jigsaws/ps-420-ebq-plus/ps-420-ebq-plus_561603_main.png", 1),
            ("tool6", "Пила циркулярная Metabo KS 55", 35.0, "Надежная циркулярная пила", "https://www.metabo.com/medias/600855000-KS-55-518x345.png", 1),
            ("tool7", "Шлифмашина Ryobi ROS300", 18.0, "Орбитальная шлифмашина", "https://images.thdstatic.com/product/image/ryobi-300w-random-orbit-sander-ros300-518x345.jpg", 1),
            ("tool8", "Триммер Stihl FS 55", 45.0, "Бензиновый триммер для травы", "https://www.stihl.com/p/media/images/products/fs_55_r_518x345.jpg", 1),
            ("tool9", "Генератор Honda EU22i", 60.0, "Инверторный генератор", "https://www.honda.co.uk/content/dam/central/power-products/generators/EU22i/EU22i-main.png", 1),
            ("tool10", "Компрессор Fubag VDC 400", 50.0, "Воздушный компрессор", "https://www.fubag.ru/upload/iblock/518/518x345_vdc_400_50_cm3.jpg", 1)
        ]
        c.executemany('INSERT INTO tools (id, name, price, description, image, available) VALUES (?, ?, ?, ?, ?, ?)', initial_tools)
        logger.info("Добавлены 10 начальных инструментов в базу данных")
    
    conn.commit()
    conn.close()

# Функция приветствия
async def greet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    conn = sqlite3.connect('tool_rental.db', check_same_thread=False)
    c = conn.cursor()
    
    ADMIN_ID = 6226570057  # Ваш Telegram ID
    c.execute('SELECT * FROM users WHERE id = ?', (user.id,))
    if not c.fetchone():
        c.execute('INSERT INTO users (id, name, username, is_admin, join_date) VALUES (?, ?, ?, ?, ?)',
                 (user.id, user.full_name, user.username, 1 if user.id == ADMIN_ID else 0, time.strftime('%Y-%m-%d')))
        conn.commit()
        logger.info(f"Создан новый пользователь: {user.id}, админ: {user.id == ADMIN_ID}")
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("Открыть каталог", web_app={"url": "https://sait-vugf.onrender.com"})],
        [InlineKeyboardButton("История заказов", callback_data='history')],
        [InlineKeyboardButton("Профиль", callback_data='profile')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\nДобро пожаловать в премиум прокат инструментов.",
        reply_markup=reply_markup
    )

# Обработка данных из Web App
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        data = json.loads(update.effective_message.web_app_data.data)
        action = data.get('action')
        if not action:
            raise ValueError("Отсутствует поле 'action' в данных")
        
        logger.info(f"Получен запрос от Web App: {action}, пользователь: {user_id}")
        
        conn = sqlite3.connect('tool_rental.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        if not user:
            c.execute('INSERT INTO users (id, name, username, is_admin, join_date) VALUES (?, ?, ?, ?, ?)',
                     (user_id, update.effective_user.full_name, update.effective_user.username, 0, time.strftime('%Y-%m-%d')))
            conn.commit()
            logger.info(f"Создан новый пользователь в обработке Web App: {user_id}")
        is_admin = bool(user[0] if user else 0)

        if action == 'fetch_catalog':
            c.execute('SELECT id, name, price, description, image, available FROM tools')
            tools = [
                {
                    'id': row[0],
                    'name': row[1],
                    'price': float(row[2]),
                    'description': row[3] or '',
                    'image': row[4] or 'https://via.placeholder.com/150?text=Tool',
                    'available': bool(row[5]),
                    'rating': 4.8  # Фиксированный рейтинг (можно добавить в БД позже)
                } for row in c.fetchall()
            ]
            response = {'action': 'catalog_data', 'tools': tools}
            logger.info(f"Отправка каталога: {len(tools)} инструментов")
            await context.bot.send_message(chat_id=user_id, text=json.dumps(response, ensure_ascii=False))

        elif action == 'check_admin':
            logger.info(f"Проверка статуса администратора для {user_id}: {is_admin}")
            await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'admin_status', 'is_admin': is_admin}))

        elif action == 'add_tool' and is_admin:
            tool = data
            required_fields = ['name', 'price', 'description', 'image']
            if not all(field in tool for field in required_fields):
                raise ValueError("Отсутствуют обязательные поля для добавления инструмента")
            tool_id = f"tool_{int(time.time())}"
            c.execute('INSERT INTO tools (id, name, price, description, image, available) VALUES (?, ?, ?, ?, ?, ?)',
                     (tool_id, tool['name'], float(tool['price']), tool['description'], tool['image'], 1))
            conn.commit()
            logger.info(f"Добавлен инструмент: {tool_id}")
            await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'tool_added'}))

        elif action == 'edit_tool' and is_admin:
            tool = data
            required_fields = ['id', 'name', 'price', 'description', 'image', 'available']
            if not all(field in tool for field in required_fields):
                raise ValueError("Отсутствуют обязательные поля для редактирования инструмента")
            c.execute('UPDATE tools SET name = ?, price = ?, description = ?, image = ?, available = ? WHERE id = ?',
                     (tool['name'], float(tool['price']), tool['description'], tool['image'], int(tool['available']), tool['id']))
            if c.rowcount == 0:
                raise ValueError(f"Инструмент с ID {tool['id']} не найден")
            conn.commit()
            logger.info(f"Отредактирован инструмент: {tool['id']}")
            await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'tool_edited'}))

        elif action == 'delete_tool' and is_admin:
            tool_id = data.get('id')
            if not tool_id:
                raise ValueError("Отсутствует ID инструмента для удаления")
            c.execute('DELETE FROM tools WHERE id = ?', (tool_id,))
            if c.rowcount == 0:
                raise ValueError(f"Инструмент с ID {tool_id} не найден")
            conn.commit()
            logger.info(f"Удален инструмент: {tool_id}")
            await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'tool_deleted'}))

        elif action == 'place_order':
            order_id = data.get('id')
            items = data.get('items')
            total = float(data.get('total', 0))
            date = data.get('date')
            address = data.get('address', 'Не указан')
            user_data = data.get('user', {})

            if not all([order_id, items, total, date]):
                raise ValueError("Отсутствуют обязательные поля для создания заказа")

            # Проверка доступности инструментов и обновление статуса
            unavailable_tools = []
            for item in items:
                c.execute('SELECT available FROM tools WHERE id = ?', (item['tool_id'],))
                result = c.fetchone()
                if not result or not result[0]:
                    unavailable_tools.append(item['name'])
            if unavailable_tools:
                raise ValueError(f"Следующие инструменты недоступны: {', '.join(unavailable_tools)}")

            items_json = json.dumps(items, ensure_ascii=False)
            c.execute('INSERT INTO orders (id, user_id, items, date, total, address) VALUES (?, ?, ?, ?, ?, ?)',
                     (order_id, user_id, items_json, date, total, address))
            c.execute('UPDATE users SET orders_count = orders_count + 1, total_spent = total_spent + ? WHERE id = ?', (total, user_id))
            conn.commit()

            # Обновление профиля пользователя в базе данных
            c.execute('UPDATE users SET name = ?, username = ? WHERE id = ?',
                     (user_data.get('name', ''), user_data.get('username', ''), user_id))
            conn.commit()

            items_text = "\n".join([f"{item['name']} - {item['days']} дн., {item['quantity']} шт. ({item['total']} BYN)" for item in items])
            message = f"✅ Новый заказ #{order_id}\nПользователь: {update.effective_user.first_name} (ID: {user_id})\nДата: {date}\nАдрес: {address}\nТовары:\n{items_text}\nИтого: {total} BYN"
            await update.message.reply_text(message)

            # Уведомление администратору
            ADMIN_ID = 6226570057
            if user_id != ADMIN_ID:
                await context.bot.send_message(chat_id=ADMIN_ID, text=message)
            logger.info(f"Создан заказ #{order_id} для пользователя {user_id}")

        else:
            logger.warning(f"Неизвестное действие: {action} или недостаточно прав")
            await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'error', 'message': 'Неизвестное действие или недостаточно прав'}))

        conn.close()

    except Exception as e:
        logger.error(f"Ошибка обработки данных Web App: {e}")
        await context.bot.send_message(chat_id=user_id, text=json.dumps({'action': 'error', 'message': str(e)}))

# Обработка кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    conn = sqlite3.connect('tool_rental.db', check_same_thread=False)
    c = conn.cursor()

    if query.data == 'catalog':
        keyboard = [[InlineKeyboardButton("Открыть каталог", web_app={"url": "https://sait-vugf.onrender.com"})]]
        await query.edit_message_text("Выберите инструмент:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'history':
        c.execute('SELECT id, date, total, address FROM orders WHERE user_id = ?', (user_id,))
        orders = c.fetchall()
        if not orders:
            await query.edit_message_text("📋 История заказов пуста")
        else:
            history_text = "\n".join([f"Заказ #{o[0]} от {o[1]} - {o[2]} BYN (Адрес: {o[3]})" for o in orders])
            await query.edit_message_text(f"📋 История заказов:\n{history_text}")

    elif query.data == 'profile':
        c.execute('SELECT name, orders_count, total_spent, is_admin, join_date FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        profile_text = f"👤 Профиль\nИмя: {user[0]}\nЗаказов: {user[1]}\nПотрачено: {user[2]} BYN\nДата регистрации: {user[4]}\nАдмин: {'Да' if user[3] else 'Нет'}"
        await query.edit_message_text(profile_text)
    
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await greet(update, context)

def main() -> None:
    init_db()
    logger.info("База данных инициализирована")
    
    application = Application.builder().token('7850457813:AAErLA5O4Q8wiPutwCcgUAnNDBJKSNNF9vQ').build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Text(["привет", "Привет", "ПРИВЕТ"]), greet))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    
    application.run_polling()

if __name__ == '__main__':
    main()
# -*- coding: utf-8 -*-
import re
import json
import os
import threading
import telebot
from telebot import types
from flask import Flask

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Бот калькулятора активен!"

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === НАСТРОЙКИ БОТА ===
BOT_TOKEN = "8178571912:AAFz65csRG_C1R5F8ZQWbJJ8wFf1shXfCvc"
ADMIN_FILE = "admin_config.json"

# Реквизиты для оплаты
PAYMENT_REQUISITES = (
    "🌟 Реквизиты для оплаты\n"
    "💳 Перевод по СБП (на карту любого банка):\n\n\n"
    "После перевода обязательно нажмите кнопку ниже: \n"
    "✅ Я оплатил(а)"
)

# Функции для работы с ID администратора
def load_admin_id():
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, "r") as f:
                data = json.load(f)
                return data.get("admin_id")
        except:
            return None
    return None

def save_admin_id(admin_id):
    try:
        with open(ADMIN_FILE, "w") as f:
            json.dump({"admin_id": admin_id}, f)
        return True
    except:
        return False

# Загрузка описаний профессий
try:
    with open("professions.json", "r", encoding="utf-8") as f:
        professions = json.load(f)
except Exception:
    professions = {}

bot = telebot.TeleBot(BOT_TOKEN)

# Временное хранилище расчетов пользователей
user_calculations = {}

# === ОРИГИНАЛЬНАЯ ФОРМУЛА ИЗ PHP ===
def calculate_vector(date_str):
    parts = date_str.split('.')
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
    except ValueError:
        return None

    yearSum = sum(int(x) for x in str(year))
    sigma = day + month + yearSum
    b = day + month
    code = (5 * sigma + b) % 22

    if code == 0:
        code = 22

    return code

# Команда /start - СМС №1
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_calculations.pop(chat_id, None)

    admin_id = load_admin_id()
    if admin_id is None:
        save_admin_id(chat_id)

    welcome_text = (
        "Приветствуем в калькуляторе «Вектор Профессии»!\n"
        "Пожалуйста, нажмите кнопку start или отправьте вашу дату рождения в формате ДД.ММ.ГГГГ:"
    )
    bot.send_message(chat_id, welcome_text)

# Ручная установка админа /setadmin
@bot.message_handler(commands=['setadmin'])
def set_admin_manually(message):
    chat_id = message.chat.id
    save_admin_id(chat_id)
    bot.send_message(chat_id, "👑 Вы успешно назначены Администратором бота!")

# Обработка ввода даты рождения
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()

    # Проверка формата даты ДД.ММ.ГГГГ
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
        bot.send_message(
            chat_id, 
            "Приветствуем в калькуляторе «Вектор Профессии»!\n"
            "Пожалуйста, нажмите кнопку start или отправьте вашу дату рождения в формате ДД.ММ.ГГГГ:"
        )
        return

    # Расчет по оригинальной формуле
    arcana = calculate_vector(text)
    if arcana is None:
        bot.send_message(chat_id, "⚠️ Ошибка в дате. Пожалуйста, отправьте вашу дату рождения в формате ДД.ММ.ГГГГ:")
        return

    user_calculations[chat_id] = {
        "date": text,
        "arcana": arcana
    }

    # СМС №2
    ready_text = (
        f"✅ Расчёт для даты {text} готов!\n\n"
        "🔒 Доступно после оплаты\n"
        "       Стоимостью 100 ₽"
    )

    markup = types.InlineKeyboardMarkup()
    btn_pay = types.InlineKeyboardButton("🌟 ОПЛАТИТЬ", callback_data="pay")
    markup.add(btn_pay)

    bot.send_message(chat_id, ready_text, reply_markup=markup)

# Обработка нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data

    # СМС №3
    if data == "pay":
        markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Я оплатил(а)", callback_data="i_paid")
        markup.add(btn_confirm)

        bot.send_message(chat_id, PAYMENT_REQUISITES, reply_markup=markup)
        bot.answer_callback_query(call.id)

    # СМС №4 и уведомление админу
    elif data == "i_paid":
        bot.send_message(
            chat_id, 
            "⏳ Запрос отправлен администратору. Расчет откроется после подтверждения."
        )
        bot.answer_callback_query(call.id)

        admin_id = load_admin_id()
        if admin_id:
            user_info = user_calculations.get(chat_id, {})
            user_date = user_info.get("date", "неизвестно")

            username = call.from_user.username
            user_link = f"@{username}" if username else f"ID: {chat_id}"

            admin_msg = (
                f"🔔 **Новый запрос на подтверждение оплаты!**\n\n"
                f"👤 Пользователь: {user_link}\n"
                f"📅 Дата рождения: `{user_date}`\n"
                f"💳 Сумма: 100 ₽\n\n"
                f"Подтвердить доступ к расчёту?"
            )

            admin_markup = types.InlineKeyboardMarkup()
            btn_approve = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{chat_id}")
            btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{chat_id}")
            admin_markup.add(btn_approve, btn_reject)

            try:
                bot.send_message(admin_id, admin_msg, parse_mode="Markdown", reply_markup=admin_markup)
            except Exception as e:
                print(f"Ошибка отправки сообщения админу: {e}")

    # Подтверждение от администратора
    elif data.startswith("approve_"):
        target_chat_id = int(data.split("_")[1])

        user_info = user_calculations.get(target_chat_id, {})
        arcana = user_info.get("arcana")

        if arcana and str(arcana) in professions:
            desc = professions[str(arcana)]
        elif arcana and arcana in professions:
            desc = professions[arcana]
        else:
            desc = "Описание профессии формируется..."

        success_msg = (
            f"Ваш Вектор Профессии:\n\n"
            f"{desc}"
        )

        try:
            bot.send_message(target_chat_id, success_msg)
            bot.edit_message_text(
                f"✅ **Оплата пользователя {target_chat_id} ПОДТВЕРЖДЕНА.** Результат отправлен.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка отправки пользователю: {e}")

        bot.answer_callback_query(call.id)

    # Отклонение от администратора
    elif data.startswith("reject_"):
        target_chat_id = int(data.split("_")[1])
        reject_msg = "⚠️ Денежный перевод не подтвержден."

        try:
            bot.send_message(target_chat_id, reject_msg)
            bot.edit_message_text(
                f"❌ **Запрос пользователя {target_chat_id} ОТКЛОНЕН.**",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка отправки пользователю: {e}")

        bot.answer_callback_query(call.id)

# Запуск веб-сервера и бота
if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    bot.infinity_polling()

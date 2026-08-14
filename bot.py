# -*- coding: utf-8 -*-
import re
import json
import os
import threading
import telebot
from telebot import types
from flask import Flask

# --- ВЕБ-СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ ЖИЗНИ БОТА ---
app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === НАСТРОЙКИ БОТА ===
BOT_TOKEN = "8178571912:AAFz65csRG_C1R5F8ZQWbJJ8wFf1shXfCvc"
ADMIN_FILE = "admin_config.json"

PAYMENT_REQUISITES = (
    "🌟 Реквизиты для поддержки проекта:\n\n"
    "💳 Перевод по СБП (на карту любого банка):\n"
    "📞 Номер телефона: +7 (999) 123-45-67\n\n"
    "Сумма спонсорского взноса: 100 ₽\n\n"
    "После перевода обязательно нажмите кнопку ниже: «✅ Я перевел(а) поддержку»"
)

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
user_calculations = {}

# Формула расчета Вектора Профессии (22 Аркана)
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
    
    d = day
    if d > 22:
        d = sum(int(x) for x in str(d))
    if d > 22:
        d = sum(int(x) for x in str(d))
        
    m = month
    if m > 22:
        m = sum(int(x) for x in str(m))
        
    y = sum(int(x) for x in str(year))
    while y > 22:
        y = sum(int(x) for x in str(y))
        
    total = d + m + y
    while total > 22:
        total = sum(int(x) for x in str(total))
        
    if total == 0:
        total = 22
        
    return total

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_calculations.pop(chat_id, None)
    
    markup_reply = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_calc = types.KeyboardButton("🔮 Запустить калькулятор")
    markup_reply.add(btn_calc)

    welcome_text = (
        "🔮 **Приветствуем в калькуляторе «Вектор Профессии»!**\n\n"
        "📅 Пожалуйста, **нажмите кнопку ниже** или отправьте вашу дату рождения в формате `ДД.ММ.ГГГГ` (например, `02.02.1991`):"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=markup_reply, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔮 Запустить калькулятор")
def handle_button_click(message):
    send_welcome(message)

@bot.message_handler(commands=['setadmin'])
def set_admin_manually(message):
    chat_id = message.chat.id
    if save_admin_id(chat_id):
        bot.send_message(chat_id, f"👑 Готово! Теперь вы главный Администратор этого бота.")
    else:
        bot.send_message(chat_id, "❌ Ошибка сохранения администратора.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
        bot.send_message(chat_id, "⚠️ Введите дату в формате **ДД.ММ.ГГГГ** (например, `02.02.1991`):", parse_mode="Markdown")
        return
        
    arcana = calculate_vector(text)
    if not arcana:
        bot.send_message(chat_id, "⚠️ Ошибка расчета. Попробуйте еще раз.")
        return
        
    user_calculations[chat_id] = {"date": text, "arcana": arcana}
    
    info_text = (
        f"✅ **Расчёт для даты {text} готов!**\n\n"
        "🔒 **Доступно для спонсоров проекта**\n\n"
        "Спонсорский взнос помогает нам улучшать алгоритмы расчёта.\n\n"
        "🎁 В знак благодарности мы предоставим вам доступ к вашему расчёту на 24 часа."
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_pay = types.InlineKeyboardButton("🌟 Стать спонсором", callback_data="show_requisites")
    btn_check = types.InlineKeyboardButton("✅ Я перевел(а) поддержку", callback_data="confirm_payment")
    markup.add(btn_pay, btn_check)
    
    bot.send_message(chat_id, info_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    admin_id = load_admin_id()
    
    if call.data == "show_requisites":
        bot.send_message(chat_id, PAYMENT_REQUISITES)
        bot.answer_callback_query(call.id)
        
    elif call.data == "confirm_payment":
        calc = user_calculations.get(chat_id)
        if not calc:
            bot.send_message(chat_id, "❌ Сначала введите дату рождения.")
            bot.answer_callback_query(call.id)
            return
            
        bot.send_message(chat_id, "⏳ Запрос отправлен администратору. Расчет откроется после подтверждения.")
        
        if admin_id is None:
            bot.send_message(chat_id, "⚠️ Администратор не зарегистрирован. Отправьте команду /setadmin")
            bot.answer_callback_query(call.id)
            return
            
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        btn_approve = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"admin_approve_{chat_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{chat_id}")
        admin_markup.add(btn_approve, btn_reject)
        
        username = f"@{call.from_user.username}" if call.from_user.username else f"ID: {chat_id}"
        admin_text = (
            f"🔔 **Новый спонсорский запрос!**\n\n"
            f"👤 Пользователь: {call.from_user.first_name} ({username})\n"
            f"📅 Дата рождения: `{calc['date']}`\n"
            f"🔮 Вектор: **{calc['arcana']}**"
        )
        
        try:
            bot.send_message(admin_id, admin_text, reply_markup=admin_markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")
        bot.answer_callback_query(call.id)
        
    elif call.data.startswith("admin_approve_"):
        user_chat_id = int(call.data.replace("admin_approve_", ""))
        calc = user_calculations.get(user_chat_id)
        
        if calc:
            arcana_num = calc['arcana']
            description = professions.get(str(arcana_num), "Описание не найдено.")
            
            success_text = (
                f"🎉 **Спасибо за спонсорскую поддержку!**\n\n"
                f"🔮 **Ваш Вектор Профессии (Аркан {arcana_num}):**\n\n"
                f"{description}"
            )
            try:
                bot.send_message(user_chat_id, success_text, parse_mode="Markdown")
                bot.send_message(chat_id, f"✅ Доступ успешно открыт!")
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except Exception as e:
                bot.send_message(chat_id, f"❌ Ошибка: {e}")
        bot.answer_callback_query(call.id)
        
    elif call.data.startswith("admin_reject_"):
        user_chat_id = int(call.data.replace("admin_reject_", ""))
        try:
            bot.send_message(user_chat_id, "⚠️ Спонсорский перевод не подтвержден.")
            bot.send_message(chat_id, "❌ Запрос отклонен.")
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}")
        bot.answer_callback_query(call.id)

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Бот успешно запущен...")
    bot.infinity_polling()

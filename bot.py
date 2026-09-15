# -*- coding: utf-8 -*-
import re
import json
import os
import threading
import requests
import telebot
from telebot import types
from flask import Flask, send_from_directory, request

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

# Ссылка из вашего личного кабинета Render
RENDER_URL = "https://my-bot-47eg.onrender.com"

@app.route('/')
def home():
    return "Бот калькулятора активен!"

@app.route('/health')
def health():
    return "OK", 200

# Команды, которые позволяют серверу "показывать" ваши HTML файлы
@app.route('/privacy')
def serve_privacy():
    return send_from_directory(os.getcwd(), '01_Sait_Politika_konfidencialnosti.html')

@app.route('/terms')
def serve_terms():
    return send_from_directory(os.getcwd(), '02_Sait_Publichnaya_oferta.html')

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# === НАСТРОЙКИ БОТА ===
BOT_TOKEN = "8178571912:AAEwOLaU7SYCscdpYs4hrUFEU_J-w6MRuh4"
ADMIN_ID = 381819608  # Ваш Telegram ID для уведомлений

# === PLATEGA ===
try:
    from platega_config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET
except Exception:
    PLATEGA_MERCHANT_ID = "4ecefadd-df1e-4625-bf05-84d4351bb3ca"
    PLATEGA_SECRET = "ВАШ_API_SECRET"

# Реквизиты для оплаты
PAYMENT_REQUISITES = (
    "После перевода обязательно нажмите кнопку ниже: \n"
    "✅ Я оплатил(а)"
)

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


# === СОЗДАНИЕ ПЛАТЕЖА PLATEGA ===
def create_platega_payment(chat_id):
    if PLATEGA_MERCHANT_ID == "" or PLATEGA_SECRET == "":
        return None, "Ошибка настройки платежной системы."

    user_info = user_calculations.get(chat_id, {})

    if not user_info:
        return None, "Расчёт не найден."

    user_date = user_info.get("date", "неизвестно")

    payload = {
        "paymentDetails": {
            "amount": 100,
            "currency": "RUB"
        },
        "description": "Вектор Профессии",
        "return": f"{RENDER_URL}/payment_success?chat_id={chat_id}",
        "failedUrl": f"{RENDER_URL}/payment_failed",
        "payload": str(chat_id),
        "metadata": {
            "chatId": str(chat_id),
            "date": user_date
        }
    }

    try:
        response = requests.post(
            "https://app.platega.io/v2/transaction/process",
            headers={
                "X-MerchantId": PLATEGA_MERCHANT_ID,
                "X-Secret": PLATEGA_SECRET,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        data = response.json()

    except Exception as e:
        print(f"Ошибка Platega: {e}")
        return None, "Не удалось соединиться с платежной системой. Попробуйте позже."

    if (
        response.status_code < 200
        or response.status_code >= 300
        or not isinstance(data, dict)
        or not data.get("transactionId")
        or not data.get("url")
    ):
        print(
            f"Platega error. HTTP: {response.status_code} "
            f"Response: {response.text}"
        )
        return None, "Не удалось создать платёж. Попробуйте ещё раз."

    transaction_id = data["transactionId"]

    user_calculations[chat_id]["transactionId"] = transaction_id
    user_calculations[chat_id]["paymentStatus"] = "PENDING"

    return data["url"], None


# === CALLBACK PLATEGA ===
@app.route('/platega_callback', methods=['POST'])
def platega_callback():

    received_merchant_id = request.headers.get("X-MerchantId", "")
    received_secret = request.headers.get("X-Secret", "")

    if (
        received_merchant_id != PLATEGA_MERCHANT_ID
        or received_secret != PLATEGA_SECRET
    ):
        return "Unauthorized", 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return "Invalid JSON", 400

    transaction_id = data.get("id", "")
    status = data.get("status", "")
    amount = data.get("amount")
    currency = data.get("currency", "")

    if not transaction_id or not status:
        return "Invalid callback", 400

    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        return "Invalid payment", 400

    if amount_value != 100.0 or currency != "RUB":
        return "Invalid payment", 400

    target_chat_id = None

    for chat_id, user_info in user_calculations.items():
        if user_info.get("transactionId") == transaction_id:
            target_chat_id = chat_id
            break

    if target_chat_id is None:
        return "Order not found", 404

    user_info = user_calculations.get(target_chat_id, {})
    arcana = user_info.get("arcana")

    if status == "CONFIRMED":

        user_calculations[target_chat_id]["paid"] = True
        user_calculations[target_chat_id]["paymentStatus"] = "CONFIRMED"

        if arcana and str(arcana) in professions:
            desc = professions[str(arcana)]
        elif arcana and arcana in professions:
            desc = professions[arcana]
        else:
            desc = "Описание профессии формируется..."

        success_msg = (
            f"Ваш Вектор Профессии:\n\n"
            f"{desc}\n\n"
            f"Полученный результат носит информационно-рекомендательный и развлекательный характер.\n"
            f"Интерпретация представляет собой обобщённый взгляд, а не абсолютную истину или готовую инструкцию для принятия решений."
        )

        try:
            bot.send_message(target_chat_id, success_msg)

            bot.send_message(
                ADMIN_ID,
                f"✅ **Оплата пользователя {target_chat_id} ПОДТВЕРЖДЕНА.** "
                f"Результат автоматически отправлен пользователю.",
                parse_mode="Markdown"
            )

        except Exception as e:
            print(f"Ошибка отправки результата: {e}")

    elif status == "CANCELED":

        user_calculations[target_chat_id]["paymentStatus"] = "CANCELED"

    elif status == "CHARGEBACKED":

        user_calculations[target_chat_id]["paymentStatus"] = "CHARGEBACKED"

    return "OK", 200


# === CALLBACK СТАРОЙ КНОПКИ «Я ОПЛАТИЛ(А)» ===
@app.route('/payment_success')
def payment_success():
    chat_id = request.args.get("chat_id")

    if chat_id:
        try:
            bot.send_message(
                int(chat_id),
                "⏳ Оплата получена. Ожидается подтверждение платежной системы."
            )
        except Exception as e:
            print(f"Ошибка отправки payment_success: {e}")

    return "OK", 200


@app.route('/payment_failed')
def payment_failed():
    return "Оплата не завершена.", 200


# === ТЕСТ БЕЗ ОПЛАТЫ ===
@bot.message_handler(commands=['test'])
def test_payment(message):
    chat_id = message.chat.id

    user_info = user_calculations.get(chat_id, {})

    if not user_info:
        bot.send_message(
            chat_id,
            "Сначала отправьте дату рождения."
        )
        return

    arcana = user_info.get("arcana")

    if arcana and str(arcana) in professions:
        desc = professions[str(arcana)]
    elif arcana and arcana in professions:
        desc = professions[arcana]
    else:
        desc = "Описание профессии формируется..."

    success_msg = (
        f"Ваш Вектор Профессии:\n\n"
        f"{desc}\n\n"
        f"Полученный результат носит информационно-рекомендательный и развлекательный характер.\n"
        f"Интерпретация представляет собой обобщённый взгляд, а не абсолютную истину или готовую инструкцию для принятия решений."
    )

    try:
        bot.send_message(
            chat_id,
            success_msg
        )

        bot.send_message(
            ADMIN_ID,
            f"🧪 **ТЕСТ: результат пользователя {chat_id} выдан без оплаты.**",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"Ошибка отправки тестового результата: {e}")


# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_calculations.pop(chat_id, None)

    welcome_text = (
        "Приветствуем в калькуляторе «Вектор Профессии»!\n"
        "Пожалуйста, отправь слово start или вашу дату рождения в формате ДД.ММ.ГГГГ:"
    )

    bot.send_message(chat_id, welcome_text)


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
            "Пожалуйста, отправь слово start или ваш дату рождения в формате ДД.ММ.ГГГГ:"
        )
        return

    # Расчет по формуле
    arcana = calculate_vector(text)

    if arcana is None:
        bot.send_message(
            chat_id,
            "⚠️ Ошибка в дате. Пожалуйста, отправьте вашу дату рождения в формате ДД.ММ.ГГГГ:"
        )
        return

    user_calculations[chat_id] = {
        "date": text,
        "arcana": arcana
    }

    ready_text = (
        f"✅ Расчёт для даты {text} готов!\n\n"
        "🔒 Доступно после оплаты\n"
        "       СТОИМОСТЬ 117 ₽\n\n"
        "После успешной оплаты, вы получите лаконичный электронный аналитический профиль, "
        "который формируется на основе алгоритмического анализа вашей даты рождения. "
        "В отчёте будут представлены направления профессиональной деятельности, "
        "соответствующие вашим врождённым склонностям и талантам, а также потенциальные сферы самореализации."
        " поддержка: @poleznoe_tut_polza"
    )

    # КНОПКИ
    markup = types.InlineKeyboardMarkup()

    btn_pay = types.InlineKeyboardButton(
        "🌟 ОПЛАТИТЬ",
        callback_data="pay"
    )

    btn_privacy = types.InlineKeyboardButton(
        "политика конфиденциальности",
        url=f"{RENDER_URL}/privacy"
    )

    btn_terms = types.InlineKeyboardButton(
        "пользовательское соглашение",
        url=f"{RENDER_URL}/terms"
    )

    markup.add(btn_pay)
    markup.add(btn_privacy)
    markup.add(btn_terms)

    bot.send_message(
        chat_id,
        ready_text,
        reply_markup=markup,
        disable_web_page_preview=True
    )


# Обработка нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "pay":

        payment_url, error_message = create_platega_payment(chat_id)

        if error_message:
            bot.send_message(
                chat_id,
                error_message
            )
            bot.answer_callback_query(call.id)
            return

        btn_payment = types.InlineKeyboardButton(
            "🌟 ПЕРЕЙТИ К ОПЛАТЕ",
            url=payment_url
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(btn_payment)

        bot.send_message(
            chat_id,
            PAYMENT_REQUISITES,
            reply_markup=markup
        )

        bot.answer_callback_query(call.id)

    elif data == "i_paid":

        bot.send_message(
            chat_id,
            "⏳ Запрос отправлен администратору. Расчет откроется после подтверждения."
        )

        bot.answer_callback_query(call.id)

        user_info = user_calculations.get(chat_id, {})
        user_date = user_info.get("date", "неизвестно")

        username = call.from_user.username
        user_link = f"@{username}" if username else f"ID: {chat_id}"

        admin_msg = (
            f"🔔 **Новый запрос на подтверждение оплаты!**\n\n"
            f"👤 Пользователь: {user_link}\n"
            f"📅 Дата рождения: `{user_date}`\n"
            f"💳 Сумма: 117 ₽\n\n"
            f"Подтвердить доступ к расчёту?"
        )

        admin_markup = types.InlineKeyboardMarkup()

        btn_approve = types.InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"approve_{chat_id}"
        )

        btn_reject = types.InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"reject_{chat_id}"
        )

        admin_markup.add(btn_approve, btn_reject)

        try:
            bot.send_message(
                ADMIN_ID,
                admin_msg,
                parse_mode="Markdown",
                reply_markup=admin_markup
            )

        except Exception as e:
            print(f"Ошибка отправки сообщения админу: {e}")

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
            f"{desc}\n\n"
            f"Полученный результат носит информационно-рекомендательный и развлекательный характер.\n"
            f"Интерпретация представляет собой обобщённый взгляд, а не абсолютную истину или готовую инструкцию для принятия решений."
        )

        try:
            bot.send_message(
                target_chat_id,
                success_msg
            )

            bot.edit_message_text(
                f"✅ **Оплата пользователя {target_chat_id} ПОДТВЕРЖДЕНА.** Результат отправлен.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )

        except Exception as e:
            bot.send_message(
                chat_id,
                f"❌ Ошибка отправки пользователю: {e}"
            )

        bot.answer_callback_query(call.id)

    elif data.startswith("reject_"):

        target_chat_id = int(data.split("_")[1])
        reject_msg = "⚠️ Денежный перевод не подтвержден."

        try:
            bot.send_message(
                target_chat_id,
                reject_msg
            )

            bot.edit_message_text(
                f"❌ **Запрос пользователя {target_chat_id} ОТКЛОНЕН.**",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )

        except Exception as e:
            bot.send_message(
                chat_id,
                f"❌ Ошибка отправки пользователю: {e}"
            )

        bot.answer_callback_query(call.id)


# Запуск веб-сервера и бота
if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()

    bot.infinity_polling()

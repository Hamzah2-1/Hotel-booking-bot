from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from config import BotToken
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from conversation import State, get_state, reset_state, get_temp_data, set_state, clear_temp_data
from datetime import datetime, date
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
from fetcher import fetch_hotels, is_russian_city
from preference_parser import parse_preferences
from recommender import rank_hotels, book_hotel
import re

async def send_date_calendar(update, context, date_type="checkin", min_date=None):
    context.user_data["awaiting_date_type"] = date_type
    if min_date is None:
        min_date = date.today()
    context.user_data[f"calendar_min_date_{date_type}"] = min_date
    calendar, step = DetailedTelegramCalendar(locale="ru", min_date=min_date).build()
    text = f"Выберите дату {'заезда' if date_type == 'checkin' else 'выезда'}:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=calendar)
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, reply_markup=calendar)

async def show_hotel(update, context, index, is_callback=False):
    hotels = context.user_data.get("hotels", [])
    if not hotels or index < 0 or index >= len(hotels):
        return
    hotel = hotels[index]
    currency = hotel.get("currency", "RUB")
    caption = (f"🏨 {hotel['name']}\n⭐ {hotel['rating']} / 5\n"
               f"💰 {hotel['price_per_night']} {currency} за ночь\n\n"
               f"Отель {index+1} из {len(hotels)}")
    keyboard = []
    if index > 0:
        keyboard.append(InlineKeyboardButton("◀ Назад", callback_data=f"prev_{index}"))
    if index < len(hotels)-1:
        keyboard.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"next_{index}"))
    keyboard.append(InlineKeyboardButton("📅 Забронировать", callback_data=f"book_{index}"))
    reply_markup = InlineKeyboardMarkup([keyboard])

    photo_url = hotel.get("image_url")
    if photo_url:
        if is_callback and update.callback_query:
            media = InputMediaPhoto(media=photo_url, caption=caption)
            await update.callback_query.edit_message_media(media=media, reply_markup=reply_markup)
            await update.callback_query.answer()
        else:
            await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=reply_markup)
    else:
        if is_callback and update.callback_query:
            await update.callback_query.edit_message_text(caption, reply_markup=reply_markup)
            await update.callback_query.answer()
        else:
            await update.message.reply_text(caption, reply_markup=reply_markup)
    context.user_data["current_index"] = index

async def start(update, context):
    user_id = update.effective_user.id
    reset_state(user_id)
    context.user_data.clear()
    await update.message.reply_text(
        "Привет! Я помогу найти и забронировать отель в России.\n"
        "Напишите название города (например, Москва, Сочи, Казань).\n"
        "Или сразу укажите всё в одном сообщении: \n"
        "«Москва с 20.06 по 25.06, бюджет 5000₽, 2 гостя»"
    )

async def handler(update, context):
    user_id = update.effective_user.id
    state = get_state(user_id)
    temp = get_temp_data(user_id)
    text = update.message.text.strip()

    if text.startswith('/'):
        await start(update, context)
        return

    if state == State.AWAITING_CITY:
        if re.fullmatch(r'[А-Яа-яёA-Za-z\s\-]{2,50}', text) and not re.search(r'\d', text):
            city = text.strip()
            if not is_russian_city(city):
                await update.message.reply_text("❌ Такой город не найден в России. Попробуйте другой (Москва, Сочи, Казань).")
                return
            temp["city"] = city
            await send_date_calendar(update, context, "checkin")
            set_state(user_id, State.AWAITING_CHECKIN)
            return

        parsed = parse_preferences(text, temp)
        if parsed["valid"] and parsed.get("city"):
            city = parsed["city"]
            if not is_russian_city(city):
                await update.message.reply_text("❌ Такой город не найден в России. Попробуйте другой (Москва, Сочи, Казань).")
                return
            temp["city"] = city
            if parsed.get("checkin"):
                temp["checkin"] = parsed["checkin"]
            if parsed.get("checkout"):
                temp["checkout"] = parsed["checkout"]
            if parsed.get("budget_max"):
                temp["budget_max"] = parsed["budget_max"]
            if parsed.get("guests"):
                temp["guests"] = parsed["guests"]

            if all(k in temp for k in ["checkin", "checkout", "budget_max", "guests"]):
                await update.message.reply_text(f"✅ Город: {city}\nДаты: {temp['checkin']} – {temp['checkout']}\nБюджет: {temp['budget_max']}₽\nГостей: {temp['guests']}\nИщем отели...")
                await perform_search(update, context, user_id, temp)
                return
            else:
                if "checkin" not in temp:
                    await send_date_calendar(update, context, "checkin")
                    set_state(user_id, State.AWAITING_CHECKIN)
                else:
                    await send_date_calendar(update, context, "checkout", min_date=datetime.fromisoformat(temp["checkin"]).date())
                    set_state(user_id, State.AWAITING_CHECKOUT)
                return
        else:
            await update.message.reply_text("Пожалуйста, напишите название города (например, Москва) или укажите всё сразу (например, 'Москва с 20.06 по 25.06, бюджет 5000₽, 2 гостя').")
            return

    elif state == State.AWAITING_BUDGET:
        try:
            temp["budget_max"] = float(text.replace(",", "."))
            await update.message.reply_text("Укажите количество гостей (цифрой):")
            set_state(user_id, State.AWAITING_GUESTS)
        except ValueError:
            await update.message.reply_text("Введите число (бюджет в рублях):")

    elif state == State.AWAITING_GUESTS:
        try:
            temp["guests"] = int(text)
            await perform_search(update, context, user_id, temp)
        except ValueError:
            await update.message.reply_text("Введите целое число (количество гостей):")

    elif state == State.AWAITING_BOOKING_NAME:
        try:
            temp["booking_name"] = text
            await update.message.reply_text("Введите ваш номер телефона (например, +7 123 456-78-90):")
            set_state(user_id, State.AWAITING_BOOKING_PHONE)
        except Exception:
            await update.message.reply_text("Ошибка. Начните сначала /start")
            reset_state(user_id)

    elif state == State.AWAITING_BOOKING_PHONE:
        try:
            temp["booking_phone"] = text
            hotel = context.user_data.get("selected_hotel")
            if not hotel:
                await update.message.reply_text("Ошибка: отель не выбран. Начните сначала /start")
                reset_state(user_id)
                return
            user_details = {
                "user_id": user_id,
                "name": temp["booking_name"],
                "phone": temp["booking_phone"],
                "hotel_name": hotel["name"],
                "price": hotel["price_per_night"],
                "rating": hotel["rating"],
                "city": temp.get("city")
            }
            result = book_hotel(hotel["id"], user_details)
            if result["status"] == "confirmed":
                await update.message.reply_text(
                    f"✅ Бронирование подтверждено!\nНомер брони: {result['booking_ref']}\n"
                    f"Отель: {hotel['name']}\nДаты: {temp['checkin']} – {temp['checkout']}\n"
                    f"Гость: {temp['booking_name']}\nСпасибо!"
                )
            else:
                await update.message.reply_text("❌ Ошибка бронирования. Попробуйте позже.")
            reset_state(user_id)
            context.user_data.clear()
        except Exception:
            await update.message.reply_text("Ошибка. Начните сначала /start")
            reset_state(user_id)

    else:
        await update.message.reply_text("Я вас не понял. Напишите /start")

async def perform_search(update, context, user_id, temp):
    prefs = {
        "user_id": user_id,
        "city": temp["city"],
        "checkin": temp["checkin"],
        "checkout": temp["checkout"],
        "budget_max": temp["budget_max"],
        "guests": temp["guests"],
        "currency": "RUB",
        "created_at": datetime.now().isoformat()
    }
    await update.message.reply_text("🔍 Ищем отели с реальными ценами... Подождите.")
    hotels = fetch_hotels(prefs)
    if not hotels:
        await update.message.reply_text("❌ Нет отелей на выбранные даты в пределах вашего бюджета.\n"
                                        "Пожалуйста, введите новый бюджет (в рублях) или измените даты.\n"
                                        "Для смены дат начните заново: /start\n"
                                        "Или введите новый бюджет:")
        set_state(user_id, State.AWAITING_BUDGET)
        return
    ranked = rank_hotels(hotels, prefs)
    if not ranked:
        await update.message.reply_text("❌ Нет отелей, подходящих под ваши предпочтения. Попробуйте увеличить бюджет или изменить даты.\n"
                                        "Введите новый бюджет (в рублях) или /start для смены дат:")
        set_state(user_id, State.AWAITING_BUDGET)
        return
    context.user_data["hotels"] = ranked
    context.user_data["preferences"] = prefs
    context.user_data["current_index"] = 0
    await show_hotel(update, context, 0, is_callback=False)
    set_state(user_id, State.SHOWING_HOTELS)

async def prev_hotel_handler(update, context):
    query = update.callback_query
    await query.answer()
    index = context.user_data.get("current_index", 0) - 1
    await show_hotel(update, context, index, is_callback=True)

async def next_hotel_handler(update, context):
    query = update.callback_query
    await query.answer()
    index = context.user_data.get("current_index", 0) + 1
    await show_hotel(update, context, index, is_callback=True)

async def book_hotel_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    index = int(data.split("_")[1])
    hotels = context.user_data.get("hotels", [])
    if index < len(hotels):
        hotel = hotels[index]
        context.user_data["selected_hotel"] = hotel
        user_id = update.effective_user.id
        temp = get_temp_data(user_id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✍️ Бронирование отеля {hotel['name']}\n"
                 f"Стоимость: {hotel['price_per_night']} {hotel.get('currency','RUB')} за ночь\n\n"
                 "Введите ваше полное имя:"
        )
        set_state(user_id, State.AWAITING_BOOKING_NAME)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
    else:
        await query.edit_message_text("Ошибка: отель не найден. /start")

async def handle_calendar(update, context):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    date_type = context.user_data.get("awaiting_date_type", "checkin")
    min_date = context.user_data.get(f"calendar_min_date_{date_type}", date.today())
    result, key, step = DetailedTelegramCalendar(locale='ru', min_date=min_date).process(query.data)

    if not result and key:
        try:
            await query.edit_message_text(text=f"📅 Выберите {LSTEP[step]}:", reply_markup=key)
        except:
            await query.edit_message_reply_markup(reply_markup=key)
    elif result:
        user_id = update.effective_user.id
        temp = get_temp_data(user_id)
        formatted = result.strftime("%Y-%m-%d")
        if date_type == "checkin":
            temp["checkin"] = formatted
            await query.edit_message_text(text=f"✅ Дата заезда: {result.strftime('%d.%m.%Y')}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Теперь выберите дату выезда:")
            await send_date_calendar(update, context, "checkout", min_date=result)
            set_state(user_id, State.AWAITING_CHECKOUT)
        else:
            temp["checkout"] = formatted
            await query.edit_message_text(text=f"✅ Дата выезда: {result.strftime('%d.%m.%Y')}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Укажите ваш бюджет на всё проживание (в рублях):")
            set_state(user_id, State.AWAITING_BUDGET)

def main():
    app = Application.builder().token(BotToken).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    app.add_handler(CallbackQueryHandler(prev_hotel_handler, pattern="^prev_"))
    app.add_handler(CallbackQueryHandler(next_hotel_handler, pattern="^next_"))
    app.add_handler(CallbackQueryHandler(book_hotel_handler, pattern="^book_"))
    app.add_handler(CallbackQueryHandler(handle_calendar))
    app.run_polling()

if __name__ == "__main__":
    main()
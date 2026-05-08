import datetime
import sqlite3
import uuid
from typing import List, Dict

def score(hotel: Dict, nights: int, budget: float) -> float:
    total_price = hotel["price_per_night"] * nights
    if total_price > budget:
        return -1e9
    price_score = 1 - (total_price / budget)
    rating_score = hotel["rating"] / 5.0
    return 0.6 * price_score + 0.4 * rating_score

def _get_user_preference_vector(user_id: int) -> Dict:
    conn = sqlite3.connect("hotels.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_history
                 (user_id INTEGER, hotel_id TEXT, price REAL, rating REAL, city TEXT, created_at TEXT)''')
    c.execute("SELECT AVG(price), AVG(rating), city FROM user_history WHERE user_id=? GROUP BY city", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return {}
    avg_price = sum(r[0] for r in rows) / len(rows)
    avg_rating = sum(r[1] for r in rows) / len(rows)
    city_counts = {}
    for row in rows:
        city_counts[row[2]] = city_counts.get(row[2], 0) + 1
    fav_city = max(city_counts, key=city_counts.get) if city_counts else None
    return {"avg_price": avg_price, "avg_rating": avg_rating, "fav_city": fav_city}

def personalization_score(hotel: Dict, user_prefs: Dict) -> float:
    if not user_prefs:
        return 0.0
    score = 0.0
    price_diff = abs(hotel["price_per_night"] - user_prefs["avg_price"])
    max_price_diff = max(user_prefs["avg_price"], 1000)
    price_sim = max(0, 1 - price_diff / max_price_diff)
    score += 0.4 * price_sim
    rating_diff = abs(hotel["rating"] - user_prefs["avg_rating"])
    rating_sim = max(0, 1 - rating_diff / 5.0)
    score += 0.3 * rating_sim
    if user_prefs.get("fav_city") and hotel.get("city") == user_prefs["fav_city"]:
        score += 0.3
    return min(score, 1.0)

def rank_hotels(hotels: List[Dict], prefs: Dict) -> List[Dict]:
    user_id = prefs["user_id"]
    checkin = datetime.date.fromisoformat(prefs["checkin"])
    checkout = datetime.date.fromisoformat(prefs["checkout"])
    nights = (checkout - checkin).days
    budget = prefs["budget_max"]

    user_vector = _get_user_preference_vector(user_id)
    _save_preferences(prefs)

    results = []
    for h in hotels:
        base = score(h, nights, budget)
        if base < -1e8:
            continue
        personal = personalization_score(h, user_vector)
        weight_personal = 0.3 if user_vector else 0.0
        total = (1 - weight_personal) * base + weight_personal * personal
        results.append((h, total))

    results.sort(key=lambda x: x[1], reverse=True)
    ranked = [h for h, _ in results]
    _save_ranking(user_id, [h["id"] for h in ranked])
    return ranked

def _save_preferences(prefs: Dict):
    conn = sqlite3.connect("hotels.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                 (user_id INTEGER, city TEXT, checkin TEXT, checkout TEXT,
                  budget REAL, guests INTEGER, created_at TEXT)''')
    c.execute("INSERT INTO user_preferences VALUES (?,?,?,?,?,?,?)",
              (prefs["user_id"], prefs["city"], prefs["checkin"], prefs["checkout"],
               prefs["budget_max"], prefs["guests"], prefs.get("created_at", "")))
    conn.commit()
    conn.close()

def _save_ranking(user_id: int, hotel_ids: List[str]):
    conn = sqlite3.connect("hotels.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rankings
                 (user_id INTEGER, hotel_id TEXT, position INTEGER, timestamp TEXT)''')
    now = datetime.datetime.now().isoformat()
    for pos, hid in enumerate(hotel_ids):
        c.execute("INSERT INTO rankings VALUES (?,?,?,?)", (user_id, hid, pos, now))
    conn.commit()
    conn.close()

def book_hotel(hotel_id: str, user_details: Dict) -> Dict:
    conn = sqlite3.connect("hotels.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (ref TEXT, user_id INTEGER, hotel_id TEXT, hotel_name TEXT,
                  guest_name TEXT, phone TEXT, booking_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_history
                 (user_id INTEGER, hotel_id TEXT, price REAL, rating REAL, city TEXT, created_at TEXT)''')

    ref = str(uuid.uuid4())[:8]
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?)",
              (ref, user_details["user_id"], hotel_id, user_details.get("hotel_name", ""),
               user_details["name"], user_details["phone"], now))

    if all(k in user_details for k in ["price", "rating", "city"]):
        c.execute("INSERT INTO user_history VALUES (?,?,?,?,?,?)",
                  (user_details["user_id"], hotel_id, user_details["price"],
                   user_details["rating"], user_details["city"], now))

    conn.commit()
    conn.close()
    return {"status": "confirmed", "booking_ref": ref}
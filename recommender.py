import datetime
import sqlite3

def score(hotel, nights, budget):
    price = hotel["price_per_night"] * nights
    return (budget - price) * 0.6 + hotel["rating"] * 0.4

def rank_hotels(hotels, prefs):
    datein = datetime.date.fromisoformat(prefs["checkin"])
    dateout = datetime.date.fromisoformat(prefs["checkout"])
    nights = (dateout - datein).days
    budget = prefs["budget_max"]
    return sorted(hotels, key= (lambda h: score(h, nights, budget)), reverse=True)



def book_hotel(hotel_id, user_details):
    result = {"status": "", "booking_ref": ""}
    con = sqlite3.connect("hotels.db")
    bcursor = con.cursor()
    
    bcursor.execute("CREATE TABLE IF NOT EXISTS Booked ( ref TEXT, user_id INTEGER, hotel_id TEXT )")
    
    bcursor.execute("INSERT INTO Booked (user_id, hotel_id) VALUES (?, ?)", (user_details["user_id"], hotel_id))
    
    con.commit()
    con.close()
    return result

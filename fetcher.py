import requests
import json
from datetime import datetime
from typing import List, Dict, Optional

LITEAPI_KEY = "sand_42062a82-f610-49a6-8566-d2ed3a0728f2"

BASE_URL = "https://api.liteapi.travel/v3.0"

HEADERS = {
    "X-API-Key": LITEAPI_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

RUSSIAN_CITIES = {
    "москва", "санкт-петербург", "спб", "новосибирск", "екатеринбург",
    "казань", "нижний новгород", "челябинск", "самара", "омск",
    "ростов-на-дону", "уфа", "красноярск", "пермь", "воронеж",
    "волгоград", "краснодар", "саратов", "тюмень", "сочи"
}

ENGLISH_ALIASES = {
    "moscow": "москва",
    "st petersburg": "санкт-петербург",
    "spb": "санкт-петербург",
    "novosibirsk": "новосибирск",
    "ekaterinburg": "екатеринбург",
    "yekaterinburg": "екатеринбург",
    "kazan": "казань",
    "sochi": "сочи"
}

RUSSIAN_TO_API_ENGLISH = {
    "москва": "Moscow",
    "санкт-петербург": "Saint Petersburg",
    "спб": "Saint Petersburg",
    "новосибирск": "Novosibirsk",
    "екатеринбург": "Yekaterinburg",
    "казань": "Kazan",
    "сочи": "Sochi",
    "владивосток": "Vladivostok",
    "калининград": "Kaliningrad",
    "нижний новгород": "Nizhny Novgorod",
    "ростов-на-дону": "Rostov-on-Don",
    "краснодар": "Krasnodar",
    "самара": "Samara",
    "уфа": "Ufa",
    "пермь": "Perm",
    "воронеж": "Voronezh",
    "волгоград": "Volgograd",
    "томск": "Tomsk"
}


def is_russian_city(city_name: str) -> bool:
    if not city_name:
        return False

    normalized = city_name.lower().strip().replace("ё", "е")

    if normalized in ENGLISH_ALIASES:
        return True

    if normalized in RUSSIAN_CITIES:
        return True

    without_hyphen = normalized.replace("-", " ").replace("  ", " ").strip()

    if without_hyphen in RUSSIAN_CITIES:
        return True

    return False


def _city_to_api_name(city: str) -> str:
    city_lower = city.lower().strip()
    return RUSSIAN_TO_API_ENGLISH.get(city_lower, city.title())


def fetch_hotels(preferences: Dict) -> List[Dict]:
    city = preferences.get("city")

    if not city:
        print("NO CITY")
        return []

    city_api = _city_to_api_name(city)

    print("SEARCH CITY:", city_api)

    hotels_data = _search_hotels_by_city(city_api)

    print("HOTELS RESPONSE:")
    print(json.dumps(hotels_data, indent=2, ensure_ascii=False)[:5000])

    if not hotels_data:
        return []

    if "data" not in hotels_data:
        return []

    if not hotels_data["data"]:
        return []

    hotel_ids = [
        str(h["id"])
        for h in hotels_data["data"]
        if h.get("id")
    ]

    print("HOTEL IDS:", hotel_ids[:10])

    rates = _fetch_rates(hotel_ids, preferences)

    print("RATES RESULT:")
    print(json.dumps(rates, indent=2, ensure_ascii=False))

    budget_max = preferences.get("budget_max", float("inf"))

    hotels = []

    for item in hotels_data["data"]:
        hotel_id = str(item.get("id"))

        price_info = rates.get(hotel_id)

        if not price_info:
            continue

        price_per_night = price_info.get("price_per_night")

        if not price_per_night:
            continue

        if price_per_night > budget_max:
            continue

        image_url = None

        hotel_images = (
            item.get("hotelImages")
            or item.get("images")
            or item.get("photos")
        )

        if hotel_images and isinstance(hotel_images, list):
            first = hotel_images[0]

            if isinstance(first, dict):
                image_url = (
                    first.get("url")
                    or first.get("original")
                    or first.get("src")
                )

            elif isinstance(first, str):
                image_url = first

        hotels.append({
            "id": hotel_id,
            "name": item.get("name", "Без названия"),
            "price_per_night": float(price_per_night),
            "rating": float(item.get("stars", 0)),
            "lat": float(item.get("latitude", 0)),
            "lon": float(item.get("longitude", 0)),
            "currency": price_info.get("currency", "RUB"),
            "image_url": image_url
        })

    print("FINAL HOTELS:", len(hotels))

    return hotels


def _search_hotels_by_city(city: str) -> Optional[Dict]:
    url = f"{BASE_URL}/data/hotels"

    params = {
        "countryCode": "RU",
        "cityName": city,
        "limit": 20
    }

    try:
        print("SEARCH REQUEST:", url)
        print("PARAMS:", params)

        resp = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=15
        )

        print("SEARCH STATUS:", resp.status_code)
        print("SEARCH RAW:")
        print(resp.text[:3000])

        if resp.status_code != 200:
            return None

        return resp.json()

    except Exception as e:
        print("SEARCH ERROR:", repr(e))
        raise


def _fetch_rates(hotel_ids: List[str], prefs: Dict) -> Dict[str, Dict]:
    url = f"{BASE_URL}/hotels/rates"

    payload = {
        "hotelIds": hotel_ids,
        "checkin": prefs["checkin"],
        "checkout": prefs["checkout"],
        "currency": "RUB",
        "guestNationality": "RU",
        "occupancies": [
            {
                "adults": prefs.get("guests", 2),
                "children": []
            }
        ]
    }

    try:
        resp = requests.post(
            url,
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        print("RATES STATUS:", resp.status_code)
        print("RATES RAW:", resp.text[:5000])

        if resp.status_code != 200:
            return {}

        data = resp.json()

        result = {}

        nights = (
            datetime.fromisoformat(prefs["checkout"])
            - datetime.fromisoformat(prefs["checkin"])
        ).days

        for hotel in data.get("data", []):

            hotel_id = str(
                hotel.get("hotelId") or hotel.get("id")
            )

            if not hotel_id:
                continue

            room_types = hotel.get("roomTypes", [])

            cheapest_price = None
            currency = "RUB"

            for room in room_types:
                for rate in room.get("rates", []):

                    amount = None

                    # 1. retailRate (primary)
                    retail = rate.get("retailRate", {})
                    if isinstance(retail, dict):
                        total = retail.get("total", [])
                        if total and isinstance(total, list):
                            amount = total[0].get("amount")

                    # 2. fallback: suggestedSellingPrice
                    if amount is None:
                        spp = rate.get("suggestedSellingPrice", [])
                        if spp and isinstance(spp, list):
                            amount = spp[0].get("amount")

                    # 3. fallback: commission weird structure
                    if amount is None:
                        commission = rate.get("commission")
                        try:
                            if isinstance(commission, list) and len(commission) > 0:
                                amount = commission[0].get("amount")
                        except:
                            pass

                    if amount is None:
                        continue

                    try:
                        amount = float(amount)
                    except:
                        continue

                    if cheapest_price is None or amount < cheapest_price:
                        cheapest_price = amount
                        currency = rate.get("currency", "RUB")

            if cheapest_price is not None:
                result[hotel_id] = {
                    "price_per_night": (
                        cheapest_price / nights
                        if nights > 0
                        else cheapest_price
                    ),
                    "currency": currency
                }

        print("FINAL RATES RESULT:", result)

        return result

    except Exception as e:
        print("RATES ERROR:", repr(e))
        raise
import re
from datetime import datetime, date
from typing import Dict, Any, Optional

MONTHS_RU = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'июн': 6,
    'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
}

def _extract_date_ru(text: str) -> Optional[datetime]:
    if not text:
        return None
    m = re.search(r'(\d{1,2})\s*[\.\-/]\s*(\d{1,2})', text)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        try:
            return datetime(date.today().year, mo, d)
        except ValueError:
            pass
    m = re.search(r'(\d{1,2})\s+([а-яёА-ЯЁ]{3,})', text)
    if m:
        d = int(m.group(1))
        mo_name = m.group(2).lower()
        mo = MONTHS_RU.get(mo_name)
        if mo:
            try:
                return datetime(date.today().year, mo, d)
            except ValueError:
                pass
    return None

def parse_preferences(user_text: str, existing_prefs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = user_text.lower().strip()
    result = {
        "city": existing_prefs.get("city") if existing_prefs else None,
        "checkin": existing_prefs.get("checkin") if existing_prefs else None,
        "checkout": existing_prefs.get("checkout") if existing_prefs else None,
        "budget_max": existing_prefs.get("budget_max") if existing_prefs else None,
        "guests": existing_prefs.get("guests") if existing_prefs else None,
        "valid": True,
        "error": None,
        "updated_fields": []
    }

    date_range = re.search(r'(?:с|от)\s*(.+?)(?:по|до|на|выезд)\s*(.+?)(?:,|\.|$|\s{2,})', text)
    if date_range:
        ci_dt = _extract_date_ru(date_range.group(1))
        co_dt = _extract_date_ru(date_range.group(2))
        if ci_dt:
            result["checkin"] = ci_dt.strftime("%Y-%m-%d")
            result["updated_fields"].append("checkin")
        if co_dt:
            result["checkout"] = co_dt.strftime("%Y-%m-%d")
            result["updated_fields"].append("checkout")
    else:
        dates_found = []
        for match in re.finditer(r'\d{1,2}\s*[\.\-/]?\s*(?:\d{1,2}|[а-яё]+)', text):
            dt = _extract_date_ru(match.group(0))
            if dt:
                dates_found.append(dt)
        if len(dates_found) == 2:
            result["checkin"] = dates_found[0].strftime("%Y-%m-%d")
            result["checkout"] = dates_found[1].strftime("%Y-%m-%d")
            result["updated_fields"].extend(["checkin", "checkout"])
        elif len(dates_found) == 1:
            result["checkin"] = dates_found[0].strftime("%Y-%m-%d")
            result["updated_fields"].append("checkin")

    city_text = re.sub(r'(?:с|от|бюджет|цена|до|гост|чел).*', '', text)
    city_text = re.sub(r'[\d\.\-/,]+', '', city_text).strip()
    city_match = re.match(r'^([А-Яа-яёA-Za-z\s-]{2,50})', city_text)
    if city_match:
        parsed_city = city_match.group(1).strip().title()
        if len(parsed_city) > 1:
            result["city"] = parsed_city
            result["updated_fields"].append("city")

    budget_match = re.search(r'(?:до|бюджет|цена|стоимость|макс)[:\s]*(\d+(?:[.,]\d+)?)\s*(?:евро|евр|eur|₽|руб|rub|\$)?', text)
    if budget_match:
        val = float(budget_match.group(1).replace(',', '.'))
        result["budget_max"] = val
        result["updated_fields"].append("budget_max")

    guests_match = re.search(r'(\d+)\s*(?:гост|чел|человек|персон|взросл)', text)
    if guests_match:
        val = int(guests_match.group(1))
        result["guests"] = val
        result["updated_fields"].append("guests")

    today = date.today()
    try:
        if result["checkin"]:
            ci = datetime.strptime(result["checkin"], "%Y-%m-%d").date()
            if ci < today:
                result["valid"] = False
                result["error"] = "Дата заезда не может быть в прошлом."
                return result
        if result["checkout"]:
            co = datetime.strptime(result["checkout"], "%Y-%m-%d").date()
            ci_date = datetime.strptime(result["checkin"], "%Y-%m-%d").date() if result["checkin"] else None
            if ci_date and co <= ci_date:
                result["valid"] = False
                result["error"] = "Дата выезда должна быть строго позже даты заезда."
                return result
        if result["budget_max"] is not None and result["budget_max"] <= 0:
            result["valid"] = False
            result["error"] = "Бюджет должен быть больше 0."
            return result
        if result["guests"] is not None and result["guests"] <= 0:
            result["valid"] = False
            result["error"] = "Количество гостей должно быть больше 0."
            return result
    except Exception as e:
        result["valid"] = False
        result["error"] = f"Ошибка в формате данных: {e}"

    return result
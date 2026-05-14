import os
import json
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

HOME_URL = "https://district5.scenecinemas.com/home"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

DATA_FILE = "watchlist.json"


def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": msg,
            "disable_web_page_preview": True
        }
    )


def load_watchlist():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_watchlist(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_movie_url(movie_name):

    r = requests.get(HOME_URL, headers=HEADERS)

    soup = BeautifulSoup(r.text, "html.parser")

    movie_links = soup.select("a[href*='movie-details']")

    for a in movie_links:

        title = a.get("title", "").strip().lower()

        if movie_name.lower() == title:

            return a.get("href")

    return None


def check_booking(movie_name, target_date):

    movie_url = get_movie_url(movie_name)

    if not movie_url:
        return False, f"❌ الفيلم غير موجود: {movie_name}"

    ajax_url = f"{movie_url}?business_day={target_date}&ajax=1"

    r = requests.get(ajax_url, headers=HEADERS)

    if r.status_code != 200:
        return False, "❌ فشل الاتصال بالموقع"

    soup = BeautifulSoup(r.text, "html.parser")

    links = soup.select("a[href*='showtime-']")

    if not links:
        return False, "لا يوجد حجز بعد"

    result = f"🎬 تم فتح الحجز\n\n"
    result += f"🎞 الفيلم: {movie_name}\n"
    result += f"📅 التاريخ: {target_date}\n\n"

    for a in links:

        time_text = a.get_text(strip=True)
        link = a.get("href")

        result += f"⏰ {time_text}\n{link}\n\n"

    return True, result


watchlist = load_watchlist()

for item in watchlist:

    movie_name = item["movie"]
    target_date = item["date"]

    found, message = check_booking(movie_name, target_date)

    if found:

        send_telegram(message)

        print("BOOKING FOUND")

    else:

        print(message)

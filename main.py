import os
import requests
from bs4 import BeautifulSoup

MOVIE_URL = "https://district5.scenecinemas.com/movie-details/asad.html"
TARGET_DATE = "22-05-2026"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def send_telegram(message):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": True
        },
        timeout=20
    )


url = f"{MOVIE_URL}?business_day={TARGET_DATE}&ajax=1"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": MOVIE_URL,
}

try:
    r = requests.get(url, headers=headers, timeout=30)

    print("STATUS:", r.status_code)

    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "html.parser")

        links = soup.select("a[href*='showtime-']")

        showtimes = []

        for a in links:
            time_text = a.get_text(strip=True)
            link = a.get("href")

            if time_text and link:
                showtimes.append((time_text, link))

        if showtimes:
            msg = f"🎬 حجز فيلم Asad فتح ليوم {TARGET_DATE}\n\n"

            for t, link in showtimes:
                msg += f"⏰ {t}\n{link}\n\n"

            send_telegram(msg)
            print("BOOKING FOUND")

        else:
            print("No booking yet")

    else:
        print("Website error")

except Exception as e:
    print("ERROR:", e)

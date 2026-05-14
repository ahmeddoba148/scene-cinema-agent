import os
import json
import subprocess
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))
HOME_URL = "https://district5.scenecinemas.com/home"

WATCHLIST_FILE = "watchlist.json"
STATE_FILE = "bot_state.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}


def tg(method, data=None):
    return requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data or {},
        timeout=30
    ).json()


def send_msg(text):
    tg("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def commit_changes():
    try:
        subprocess.run(["git", "config", "user.name", "cinema-bot"], check=True)
        subprocess.run(["git", "config", "user.email", "cinema-bot@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", WATCHLIST_FILE, STATE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update cinema bot state"], check=False)
        subprocess.run(["git", "push"], check=False)
    except Exception as e:
        print("Git commit error:", e)


def get_movies():
    r = requests.get(HOME_URL, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    movies = []
    seen = set()

    for a in soup.select("a[href*='movie-details']"):
        title = a.get("title", "").strip()
        href = a.get("href", "").strip()

        if title and href and title.lower() not in seen:
            seen.add(title.lower())
            movies.append({"title": title, "url": href})

    return movies


def get_updates(offset=None):
    data = {"timeout": 0}
    if offset:
        data["offset"] = offset

    return tg("getUpdates", data).get("result", [])


def handle_commands():
    state = load_json(STATE_FILE, {"last_update_id": 0})
    watchlist = load_json(WATCHLIST_FILE, [])

    updates = get_updates(state.get("last_update_id", 0) + 1)

    changed = False

    for update in updates:
        state["last_update_id"] = update["update_id"]
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id != CHAT_ID or not text:
            continue

        if text == "/start":
            send_msg(
                "🎬 أهلا يا أحمد\n\n"
                "الأوامر:\n"
                "/movies - عرض الأفلام\n"
                "/watch رقم_الفيلم|التاريخ\n"
                "/list - عرض المراقبة\n"
                "/remove رقم\n"
                "/clear - مسح الكل\n\n"
                "مثال:\n"
                "/watch 2|22-05-2026"
            )

        elif text == "/movies":
            movies = get_movies()
            reply = "🎞 الأفلام المتاحة:\n\n"
            for i, m in enumerate(movies, 1):
                reply += f"{i}. {m['title']}\n"
            reply += "\nللمراقبة:\n/watch رقم الفيلم|التاريخ\nمثال:\n/watch 2|22-05-2026"
            send_msg(reply)

        elif text.startswith("/watch"):
            try:
                raw = text.replace("/watch", "", 1).strip()
                movie_part, date = raw.split("|")
                movie_part = movie_part.strip()
                date = date.strip()

                movies = get_movies()

                if movie_part.isdigit():
                    index = int(movie_part) - 1
                    movie = movies[index]
                else:
                    movie = next(
                        m for m in movies
                        if m["title"].lower() == movie_part.lower()
                    )

                item = {
                    "movie": movie["title"],
                    "url": movie["url"],
                    "date": date,
                    "alerted": False
                }

                watchlist.append(item)
                changed = True

                send_msg(
                    f"✅ تمت إضافة المراقبة\n\n"
                    f"🎞 الفيلم: {movie['title']}\n"
                    f"📅 التاريخ: {date}"
                )

            except Exception as e:
                send_msg(
                    "❌ صيغة الأمر غلط\n\n"
                    "استخدم:\n"
                    "/watch رقم_الفيلم|التاريخ\n\n"
                    "مثال:\n"
                    "/watch 2|22-05-2026"
                )

        elif text == "/list":
            if not watchlist:
                send_msg("📭 لا توجد أفلام تحت المراقبة.")
            else:
                reply = "📌 قائمة المراقبة:\n\n"
                for i, item in enumerate(watchlist, 1):
                    status = "✅ تم التنبيه" if item.get("alerted") else "⏳ منتظر"
                    reply += f"{i}. {item['movie']} - {item['date']} - {status}\n"
                send_msg(reply)

        elif text.startswith("/remove"):
            try:
                num = int(text.replace("/remove", "", 1).strip()) - 1
                removed = watchlist.pop(num)
                changed = True
                send_msg(f"🗑 تم حذف:\n{removed['movie']} - {removed['date']}")
            except:
                send_msg("❌ استخدم مثلًا:\n/remove 1")

        elif text == "/clear":
            watchlist = []
            changed = True
            send_msg("🧹 تم مسح كل قائمة المراقبة.")

    save_json(STATE_FILE, state)

    if changed:
        save_json(WATCHLIST_FILE, watchlist)

    return changed


def check_booking(item):
    ajax_url = f"{item['url']}?business_day={item['date']}&ajax=1"
    r = requests.get(ajax_url, headers={**HEADERS, "Referer": item["url"]}, timeout=30)

    if r.status_code != 200:
        print("Bad status:", r.status_code)
        return False

    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.select("a[href*='showtime-']")

    if not links:
        return False

    msg = (
        f"🔥 الحجز فتح!\n\n"
        f"🎞 الفيلم: {item['movie']}\n"
        f"📅 التاريخ: {item['date']}\n\n"
    )

    for a in links:
        t = a.get_text(strip=True)
        link = a.get("href")
        msg += f"⏰ {t}\n{link}\n\n"

    send_msg(msg)
    return True


def main():
    commands_changed = handle_commands()

    watchlist = load_json(WATCHLIST_FILE, [])
    changed = commands_changed

    for item in watchlist:
        if item.get("alerted"):
            continue

        opened = check_booking(item)

        if opened:
            item["alerted"] = True
            changed = True

    save_json(WATCHLIST_FILE, watchlist)

    if changed:
        commit_changes()


if __name__ == "__main__":
    main()

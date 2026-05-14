import os
import json
import subprocess
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))

HOME_URL = "https://district5.scenecinemas.com/home"

WATCHLIST_FILE = "watchlist.json"
STATE_FILE = "bot_state.json"
MOVIES_CACHE_FILE = "movies_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def tg(method, data=None):
    return requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=data or {},
        timeout=30
    ).json()


def send_msg(text, keyboard=None):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }

    if keyboard:
        data["reply_markup"] = keyboard

    return tg("sendMessage", data)


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "🎬 عرض الأفلام"}],
            [{"text": "📌 قائمة المراقبة"}],
            [{"text": "🧹 مسح الكل"}],
        ],
        "resize_keyboard": True
    }


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

        subprocess.run(
            ["git", "add", WATCHLIST_FILE, STATE_FILE, MOVIES_CACHE_FILE],
            check=True
        )

        subprocess.run(
            ["git", "commit", "-m", "Update cinema bot data"],
            check=False
        )

        subprocess.run(["git", "push"], check=False)

    except Exception as e:
        print("Git error:", e)


def get_movies():
    r = requests.get(HOME_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    movies = []
    seen = set()

    for a in soup.select("a[href*='movie-details']"):
        title = a.get("title", "").strip()
        href = a.get("href", "").strip()

        if title and href and title.lower() not in seen:
            seen.add(title.lower())
            movies.append({
                "title": title,
                "url": href
            })

    return movies


def get_cached_movies():
    return load_json(MOVIES_CACHE_FILE, {
        "last_check_utc": "Not checked yet",
        "count": 0,
        "movies": []
    })


def update_movies_cache():
    try:
        movies = get_movies()

        cache = {
            "last_check_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "count": len(movies),
            "movies": movies
        }

        save_json(MOVIES_CACHE_FILE, cache)

        print(f"Movies cache updated: {len(movies)} movies")

        return cache

    except Exception as e:
        old_cache = get_cached_movies()

        old_cache["last_error"] = str(e)
        old_cache["last_error_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        save_json(MOVIES_CACHE_FILE, old_cache)

        print("Movies cache update failed:", e)

        return old_cache


def get_updates(offset=None):
    data = {
        "timeout": 0
    }

    if offset:
        data["offset"] = offset

    result = tg("getUpdates", data)

    return result.get("result", [])


def show_movies():
    cache = get_cached_movies()
    movies = cache.get("movies", [])
    last_check = cache.get("last_check_utc", "Unknown")
    last_error = cache.get("last_error")

    if not movies:
        text = (
            "❌ لا توجد أفلام محفوظة حتى الآن.\n\n"
            f"🕒 آخر تحديث: {last_check}\n"
        )

        if last_error:
            text += f"\n⚠️ آخر خطأ: {last_error}"

        send_msg(text, main_keyboard())
        return

    text = (
        f"🎬 آخر قائمة أفلام\n"
        f"🕒 آخر تحديث: {last_check}\n"
        f"🎞 عدد الأفلام: {len(movies)}\n\n"
    )

    for i, movie in enumerate(movies, 1):
        text += f"{i}. {movie['title']}\n"

    text += (
        "\n📌 لإضافة مراقبة اكتب:\n"
        "رقم الفيلم|التاريخ\n\n"
        "مثال:\n"
        "2|22-05-2026"
    )

    send_msg(text, main_keyboard())


def show_watchlist(watchlist):
    if not watchlist:
        send_msg(
            "📭 لا توجد أفلام تحت المراقبة.",
            main_keyboard()
        )
        return

    text = "📌 قائمة المراقبة:\n\n"

    for i, item in enumerate(watchlist, 1):
        status = "✅ تم التنبيه" if item.get("alerted") else "⏳ منتظر"
        text += f"{i}. {item['movie']} - {item['date']} - {status}\n"

    text += (
        "\n🗑 لحذف عنصر اكتب:\n"
        "حذف رقم\n\n"
        "مثال:\n"
        "حذف 1"
    )

    send_msg(text, main_keyboard())


def add_watch_item(text, watchlist):
    try:
        movie_index, date = text.split("|")
        movie_index = int(movie_index.strip()) - 1
        date = date.strip()

        cache = get_cached_movies()
        movies = cache.get("movies", [])

        if movie_index < 0 or movie_index >= len(movies):
            send_msg(
                "❌ رقم الفيلم غير صحيح.\nاضغط 🎬 عرض الأفلام وشوف الرقم الصحيح.",
                main_keyboard()
            )
            return False

        movie = movies[movie_index]

        watchlist.append({
            "movie": movie["title"],
            "url": movie["url"],
            "date": date,
            "alerted": False
        })

        send_msg(
            f"✅ تمت إضافة المراقبة\n\n"
            f"🎞 الفيلم: {movie['title']}\n"
            f"📅 التاريخ: {date}\n\n"
            f"هتابعه تلقائيًا وأول ما الحجز يفتح هبعتلك.",
            main_keyboard()
        )

        return True

    except Exception as e:
        print("Add watch error:", e)

        send_msg(
            "❌ الصيغة غلط.\n\n"
            "اكتب مثلًا:\n"
            "2|22-05-2026",
            main_keyboard()
        )

        return False


def remove_watch_item(text, watchlist):
    try:
        num = text.replace("حذف", "", 1).strip()
        index = int(num) - 1

        if index < 0 or index >= len(watchlist):
            send_msg("❌ رقم غير صحيح.", main_keyboard())
            return False

        removed = watchlist.pop(index)

        send_msg(
            f"🗑 تم حذف:\n"
            f"{removed['movie']} - {removed['date']}",
            main_keyboard()
        )

        return True

    except Exception as e:
        print("Remove error:", e)

        send_msg(
            "❌ اكتب الحذف بهذا الشكل:\n"
            "حذف 1",
            main_keyboard()
        )

        return False


def handle_text_message(text, watchlist):
    changed = False

    if text == "/start":
        send_msg(
            "🎬 أهلا يا أحمد\n\n"
            "اختار من الأزرار:",
            main_keyboard()
        )

    elif text == "🎬 عرض الأفلام":
        show_movies()

    elif text == "📌 قائمة المراقبة":
        show_watchlist(watchlist)

    elif text == "🧹 مسح الكل":
        watchlist.clear()

        send_msg(
            "🧹 تم مسح كل قائمة المراقبة.",
            main_keyboard()
        )

        changed = True

    elif "|" in text:
        if add_watch_item(text, watchlist):
            changed = True

    elif text.startswith("حذف"):
        if remove_watch_item(text, watchlist):
            changed = True

    else:
        send_msg(
            "اختار من الأزرار 👇\n\n"
            "أو اكتب مثلًا:\n"
            "2|22-05-2026",
            main_keyboard()
        )

    return changed


def handle_bot_updates():
    state = load_json(STATE_FILE, {
        "last_update_id": 0
    })

    watchlist = load_json(WATCHLIST_FILE, [])

    updates = get_updates(
        state.get("last_update_id", 0) + 1
    )

    changed = False

    for update in updates:
        state["last_update_id"] = update["update_id"]

        msg = update.get("message")

        if not msg:
            continue

        chat_id = str(
            msg.get("chat", {})
            .get("id", "")
        )

        text = msg.get("text", "").strip()

        if chat_id == CHAT_ID and text:
            if handle_text_message(text, watchlist):
                changed = True

    save_json(STATE_FILE, state)
    save_json(WATCHLIST_FILE, watchlist)

    return changed


def check_booking(item):
    ajax_url = f"{item['url']}?business_day={item['date']}&ajax=1"

    r = requests.get(
        ajax_url,
        headers={
            **HEADERS,
            "Referer": item["url"]
        },
        timeout=30
    )

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
        time_text = a.get_text(strip=True)
        link = a.get("href")

        if time_text and link:
            msg += f"⏰ {time_text}\n{link}\n\n"

    send_msg(msg)

    return True


def check_watchlist():
    watchlist = load_json(WATCHLIST_FILE, [])
    changed = False

    for item in watchlist:
        if item.get("alerted"):
            continue

        try:
            opened = check_booking(item)

            if opened:
                item["alerted"] = True
                changed = True

        except Exception as e:
            print(f"Check error for {item.get('movie')}:", e)

    save_json(WATCHLIST_FILE, watchlist)

    return changed


def main():
    update_movies_cache()

    changed_1 = handle_bot_updates()
    changed_2 = check_watchlist()

    commit_changes()


if __name__ == "__main__":
    main()

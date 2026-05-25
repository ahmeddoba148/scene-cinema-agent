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

HEADERS = {"User-Agent": "Mozilla/5.0"}


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def tg(method, data=None):
    return requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=data or {},
        timeout=30
    ).json()


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "📌 الأفلام المراقبة"}],
            [{"text": "/start"}, {"text": "/list"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }


def send_msg(text):
    return tg("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
        "reply_markup": main_keyboard()
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
        subprocess.run(["git", "add", WATCHLIST_FILE, STATE_FILE, MOVIES_CACHE_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update cinema bot data"], check=False)
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
            movies.append({"title": title, "url": href})

    return movies


def get_cached_movies():
    return load_json(MOVIES_CACHE_FILE, {
        "last_check_utc": "Not checked yet",
        "count": 0,
        "movies": []
    })


def movie_titles_set(movies):
    return set(m["title"].strip().lower() for m in movies if m.get("title"))


def format_movies_list(movies, last_check):
    msg = "🎬 قائمة الأفلام الحالية بعد التحديث\n"
    msg += f"🕒 آخر تحديث: {last_check}\n"
    msg += f"🎞 عدد الأفلام: {len(movies)}\n\n"

    if not movies:
        msg += "📭 لا توجد أفلام حاليًا.\n"
    else:
        for i, movie in enumerate(movies, 1):
            msg += f"{i}. {movie['title']}\n"

    msg += "\n📌 لإضافة مراقبة اكتب:\n"
    msg += "رقم الفيلم-يوم-شهر-سنة\n\n"
    msg += "مثال:\n"
    msg += "2-22-05-2026"

    return msg


def format_movies_change_message(added, removed, last_check):
    msg = "🎬 حصل تغيير في قائمة أفلام Scene Cinemas\n\n"
    msg += f"🕒 آخر تحديث: {last_check}\n\n"

    if added:
        msg += "✅ أفلام اتضافت:\n"
        for title in sorted(added):
            msg += f"- {title}\n"
        msg += "\n"

    if removed:
        msg += "❌ أفلام اتشالت:\n"
        for title in sorted(removed):
            msg += f"- {title}\n"
        msg += "\n"

    return msg.strip()


def update_movies_cache_and_notify_if_changed():
    old_cache = get_cached_movies()
    old_movies = old_cache.get("movies", [])

    try:
        new_movies = get_movies()

        old_set = movie_titles_set(old_movies)
        new_set = movie_titles_set(new_movies)

        added = new_set - old_set
        removed = old_set - new_set

        cache = {
            "last_check_utc": now_utc(),
            "count": len(new_movies),
            "movies": new_movies
        }

        save_json(MOVIES_CACHE_FILE, cache)

        # أول تشغيل: ابعت القائمة كاملة فقط
        if not old_movies:
            send_msg(format_movies_list(new_movies, cache["last_check_utc"]))

        # عند أي إضافة أو حذف: ابعت رسالتين وراء بعض
        # 1) رسالة التغيير
        # 2) القائمة الحالية كاملة بعد التعديل
        elif added or removed:
            send_msg(format_movies_change_message(added, removed, cache["last_check_utc"]))
            send_msg(format_movies_list(new_movies, cache["last_check_utc"]))

        return cache

    except Exception as e:
        old_cache["last_error"] = str(e)
        old_cache["last_error_utc"] = now_utc()
        save_json(MOVIES_CACHE_FILE, old_cache)
        print("Movies cache update failed:", e)
        return old_cache


def get_updates(offset=None):
    data = {"timeout": 0}
    if offset:
        data["offset"] = offset

    result = tg("getUpdates", data)
    return result.get("result", [])


def format_watchlist(watchlist):
    if not watchlist:
        return "📭 لا توجد أفلام تحت المراقبة."

    msg = "📌 قائمة المراقبة:\n\n"

    for i, item in enumerate(watchlist, 1):
        status = "✅ تم التنبيه" if item.get("alerted") else "⏳ منتظر"
        msg += f"{i}. {item['movie']} - {item['date']} - {status}\n"

    msg += "\n🗑 للحذف اكتب:\nحذف 1"
    return msg


def remove_watch_item(text, watchlist):
    try:
        num = text.replace("حذف", "", 1).strip()
        index = int(num) - 1

        if index < 0 or index >= len(watchlist):
            send_msg("❌ رقم الحذف غير صحيح.")
            return False

        removed = watchlist.pop(index)

        send_msg(
            f"🗑 تم حذف المراقبة:\n\n"
            f"🎞 {removed['movie']}\n"
            f"📅 {removed['date']}"
        )

        return True

    except:
        send_msg("❌ اكتب الحذف بهذا الشكل:\nحذف 1")
        return False


def parse_watch_command(text):
    parts = text.strip().split("-")

    if len(parts) != 4:
        return None, None, "❌ الصيغة غلط.\n\nاكتب مثلًا:\n2-22-05-2026"

    movie_num_text, day, month, year = parts

    if not movie_num_text.isdigit():
        return None, None, "❌ رقم الفيلم لازم يكون رقم."

    if not (day.isdigit() and month.isdigit() and year.isdigit()):
        return None, None, "❌ التاريخ لازم يكون أرقام فقط."

    if len(day) not in [1, 2] or len(month) not in [1, 2] or len(year) != 4:
        return None, None, "❌ شكل التاريخ غلط.\n\nاكتب مثلًا:\n2-22-05-2026"

    day = day.zfill(2)
    month = month.zfill(2)

    date = f"{day}-{month}-{year}"
    movie_num = int(movie_num_text)

    return movie_num, date, None


def add_watch_by_number_and_date(text, watchlist):
    movie_num, date, error = parse_watch_command(text)

    if error:
        send_msg(error)
        return False

    cache = get_cached_movies()
    movies = cache.get("movies", [])

    if not movies:
        cache = update_movies_cache_and_notify_if_changed()
        movies = cache.get("movies", [])

    if not movies:
        send_msg("❌ قائمة الأفلام لم تتحدث بعد. جرب بعد أول تشغيل.")
        return False

    index = movie_num - 1

    if index < 0 or index >= len(movies):
        send_msg("❌ رقم الفيلم غير صحيح. ابعت /start لعرض القائمة.")
        return False

    movie = movies[index]

    for item in watchlist:
        same_movie = item.get("movie", "").lower() == movie["title"].lower()
        same_date = item.get("date", "") == date
        not_alerted = not item.get("alerted")

        if same_movie and same_date and not_alerted:
            send_msg(
                f"ℹ️ المراقبة دي متسجلة بالفعل.\n\n"
                f"🎞 الفيلم: {movie['title']}\n"
                f"📅 التاريخ: {date}"
            )
            return False

    watchlist.append({
        "movie": movie["title"],
        "url": movie["url"],
        "date": date,
        "alerted": False,
        "created_utc": now_utc()
    })

    send_msg(
        f"✅ تم بدء مراقبة الفيلم بنجاح\n\n"
        f"🎞 الفيلم: {movie['title']}\n"
        f"📅 التاريخ: {date}\n\n"
        f"هشيّك عليه تلقائيًا كل ساعتين، وأول ما الحجز يفتح هبعتلك."
    )

    return True


def handle_text_message(text, watchlist):
    changed = False
    text = text.strip()

    if text == "/start":
        cache = get_cached_movies()
        movies = cache.get("movies", [])
        last_check = cache.get("last_check_utc", "Unknown")

        if not movies:
            cache = update_movies_cache_and_notify_if_changed()
            movies = cache.get("movies", [])
            last_check = cache.get("last_check_utc", "Unknown")

        if movies:
            send_msg(format_movies_list(movies, last_check))
        else:
            send_msg("❌ لم أقدر أجيب قائمة الأفلام حاليًا.")

    elif text in ["/list", "📌 الأفلام المراقبة"]:
        send_msg(format_watchlist(watchlist))

    elif text == "/clear":
        watchlist.clear()
        send_msg("🧹 تم مسح كل قائمة المراقبة.")
        changed = True

    elif text.startswith("حذف"):
        if remove_watch_item(text, watchlist):
            changed = True

    elif "-" in text:
        if add_watch_by_number_and_date(text, watchlist):
            changed = True

    else:
        send_msg(
            "❌ مش فاهم الأمر.\n\n"
            "لعرض الأفلام اكتب:\n"
            "/start\n\n"
            "لإضافة مراقبة اكتب:\n"
            "رقم الفيلم-يوم-شهر-سنة\n\n"
            "مثال:\n"
            "2-22-05-2026"
        )

    return changed


def handle_bot_updates():
    state = load_json(STATE_FILE, {"last_update_id": 0})
    watchlist = load_json(WATCHLIST_FILE, [])

    updates = get_updates(state.get("last_update_id", 0) + 1)

    changed = False

    for update in updates:
        state["last_update_id"] = update["update_id"]

        msg = update.get("message")
        if not msg:
            continue

        chat_id = str(msg.get("chat", {}).get("id", ""))
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
        headers={**HEADERS, "Referer": item["url"]},
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
                item["alerted_utc"] = now_utc()
                changed = True

        except Exception as e:
            print(f"Check error for {item.get('movie')}:", e)

    save_json(WATCHLIST_FILE, watchlist)
    return changed


def main():
    update_movies_cache_and_notify_if_changed()

    handle_bot_updates()

    check_watchlist()

    commit_changes()


if __name__ == "__main__":
    main()

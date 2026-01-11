import time
import json
import os
from datetime import date
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = "8252295424:AAGRllLya9BowzOdoKQvEt42MMTwUSAkn2M"
DAILY_LIMIT = 5
SUBSCRIBE_USERNAME = "@A_udw"

USAGE_FILE = "usage.json"
SUBSCRIBERS_FILE = "subscribers.txt"


# =========================
# FILE HELPERS
# =========================
def load_usage():
    if not os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(USAGE_FILE, "r") as f:
        return json.load(f)


def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return set()
    with open(SUBSCRIBERS_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def check_limit(user_id: int):
    usage = load_usage()
    today = str(date.today())
    uid = str(user_id)

    if uid not in usage or usage[uid]["date"] != today:
        usage[uid] = {"date": today, "count": 1}
        save_usage(usage)
        return True, DAILY_LIMIT - 1

    if usage[uid]["count"] >= DAILY_LIMIT:
        return False, 0

    usage[uid]["count"] += 1
    save_usage(usage)
    return True, DAILY_LIMIT - usage[uid]["count"]


# =========================
# SCRAPER
# =========================
class FacebookScraper:
    def setup_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.binary_location = "/usr/bin/chromium"
        return webdriver.Chrome(options=options)

    def get_profile_id(self, driver, url):
        try:
            meta = driver.find_element(By.CSS_SELECTOR, "meta[property='fb:profile_id']")
            pid = meta.get_attribute("content")
            if pid:
                return pid
        except:
            pass

        try:
            mobile = url.replace("www.facebook.com", "m.facebook.com").replace("facebook.com", "m.facebook.com")
            driver.get(mobile)
            time.sleep(2)
            if "id=" in driver.current_url:
                return driver.current_url.split("id=")[1].split("&")[0]
        except:
            pass

        return None

    def scrape(self, url):
        driver = self.setup_driver()
        data = {
            "profile": None,
            "cover": None,
            "photos": [],
            "profile_id": None
        }

        try:
            driver.get(url)
            time.sleep(3)

            # PROFILE ID
            data["profile_id"] = self.get_profile_id(driver, url)

            # PROFILE PHOTO
            try:
                meta = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                data["profile"] = meta.get_attribute("content")
            except:
                pass

            # COVER PHOTO
            try:
                cover = driver.find_element(By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']")
                data["cover"] = cover.get_attribute("src")
            except:
                pass

            # PUBLIC PHOTOS
            driver.get(url.rstrip("/") + "/photos")
            time.sleep(2)

            for _ in range(2):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            imgs = driver.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src")
                if src and "scontent" in src and src not in data["photos"]:
                    data["photos"].append(src)
                if len(data["photos"]) >= 20:
                    break

            return data

        finally:
            driver.quit()


# =========================
# TELEGRAM HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Facebook Scraper Bot\n\n"
        "📸 Profile Photo\n"
        "🖼️ Cover Photo\n"
        "📷 Public Photos (media group)\n"
        "🆔 Profile ID\n\n"
        f"🎁 Free: {DAILY_LIMIT} requests/day\n"
        f"💎 Unlimited: DM {SUBSCRIBE_USERNAME}\n\n"
        "📌 Just send a Facebook profile link"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = (update.message.text or "").strip()

    if "facebook.com" not in url:
        await update.message.reply_text("❌ Send a valid Facebook profile link.")
        return

    subscribers = load_subscribers()

    # LIMIT CHECK
    if str(user_id) not in subscribers:
        allowed, remaining = check_limit(user_id)
        if not allowed:
            await update.message.reply_text(
                f"🚫 Daily limit reached ({DAILY_LIMIT})\n\n"
                f"💎 Subscribe via {SUBSCRIBE_USERNAME}"
            )
            return
    else:
        remaining = "∞"

    status = await update.message.reply_text(
        f"⏳ Fetching data...\nRemaining today: {remaining}"
    )

    scraper = FacebookScraper()
    data = scraper.scrape(url)

    await status.delete()

    # =========================
    # SEND RESULTS
    # =========================
    if data["profile_id"]:
        await update.message.reply_text(f"🆔 Profile ID:\n{data['profile_id']}")

    if data["profile"]:
        await update.message.reply_photo(
            data["profile"], caption="📸 Profile Photo"
        )

    if data["cover"]:
        await update.message.reply_photo(
            data["cover"], caption="🖼️ Cover Photo"
        )

    if data["photos"]:
        media = [InputMediaPhoto(p) for p in data["photos"]]
        for i in range(0, len(media), 10):
            await update.message.reply_media_group(media[i:i+10])


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()

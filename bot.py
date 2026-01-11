import time
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = "8252295424:AAGRllLya9BowzOdoKQvEt42MMTwUSAkn2M"


# =========================
# FACEBOOK SCRAPER
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

    def scrape(self, url):
        driver = self.setup_driver()

        data = {
            "profile_photo": None,
            "cover_photo": None,
            "public_photos": []
        }

        try:
            # =========================
            # PROFILE PAGE
            # =========================
            driver.get(url)
            time.sleep(3)

            # Profile photo (meta og:image)
            try:
                meta = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                data["profile_photo"] = meta.get_attribute("content")
            except:
                pass

            # Cover photo
            try:
                cover = driver.find_element(
                    By.CSS_SELECTOR,
                    "img[data-imgperflogname='profileCoverPhoto']"
                )
                data["cover_photo"] = cover.get_attribute("src")
            except:
                pass

            # =========================
            # PUBLIC PHOTOS
            # =========================
            driver.get(url.rstrip("/") + "/photos")
            time.sleep(2)

            for _ in range(2):
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(1)

            imgs = driver.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src")
                if src and "scontent" in src:
                    data["public_photos"].append(src)
                if len(data["public_photos"]) >= 20:
                    break

            return data

        finally:
            driver.quit()


# =========================
# TELEGRAM HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Facebook Photos Bot\n\n"
        "Send a Facebook profile link and I will fetch:\n"
        "• Profile photo\n"
        "• Cover photo\n"
        "• Public photos (media group)\n\n"
        "Example:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if "facebook.com" not in url:
        await update.message.reply_text("❌ Please send a valid Facebook profile URL.")
        return

    status = await update.message.reply_text("⏳ Fetching photos…")

    scraper = FacebookScraper()
    data = scraper.scrape(url)

    await status.delete()

    # =========================
    # SEND RESULTS (ORDERED)
    # =========================
    if data["profile_photo"]:
        await update.message.reply_photo(
            data["profile_photo"],
            caption="📸 Profile Photo"
        )

    if data["cover_photo"]:
        await update.message.reply_photo(
            data["cover_photo"],
            caption="🖼️ Cover Photo"
        )

    if data["public_photos"]:
        await update.message.reply_text(
            f"📷 Found {len(data['public_photos'])} public photos"
        )

        media = [InputMediaPhoto(p) for p in data["public_photos"]]

        for i in range(0, len(media), 10):
            await update.message.reply_media_group(
                media[i:i + 10]
            )
    else:
        await update.message.reply_text("❌ No public photos found.")


# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

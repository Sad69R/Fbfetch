import os
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# =========================
# Configuration
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


class FacebookScraper:
    def __init__(self):
        self.driver = None

    def setup_driver(self):
        """Setup headless Chrome driver (Railway compatible)"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver

    def scrape_photos(self, profile_url):
        """Scrape profile photo, cover photo, and some public photos"""
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(5)

            photos = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": []
            }

            # Profile photo
            try:
                profile_pic = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "img[data-imgperflogname='profileCoverPhoto']"
                )
                photos["profile_photo"] = profile_pic.get_attribute("src")
            except:
                pass

            # Cover photo
            try:
                cover = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "img[data-imgperflogname='profileCoverPhoto']"
                )
                photos["cover_photo"] = cover.get_attribute("src")
            except:
                pass

            # Public photos
            try:
                photos_url = profile_url.rstrip("/") + "/photos"
                self.driver.get(photos_url)
                time.sleep(3)

                for _ in range(3):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(2)

                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        if src not in photos["public_photos"]:
                            photos["public_photos"].append(src)
                    if len(photos["public_photos"]) >= 10:
                        break

            except Exception as e:
                print("Error loading public photos:", e)

            return photos

        except Exception as e:
            print("Scraping error:", e)
            return None

        finally:
            if self.driver:
                self.driver.quit()


# =========================
# Telegram Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a Facebook profile URL and I will try to fetch:\n"
        "• Profile photo\n"
        "• Cover photo\n"
        "• Public photos\n\n"
        "Example:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "facebook.com" not in text:
        await update.message.reply_text("❌ Please send a valid Facebook profile URL.")
        return

    await update.message.reply_text("🔍 Fetching photos... please wait.")

    scraper = FacebookScraper()
    photos = scraper.scrape_photos(text)

    if not photos:
        await update.message.reply_text(
            "❌ Failed to fetch photos.\nProfile may be private or Facebook blocked access."
        )
        return

    if photos["profile_photo"]:
        try:
            await update.message.reply_photo(
                photos["profile_photo"], caption="📸 Profile Photo"
            )
        except:
            await update.message.reply_text(photos["profile_photo"])

    if photos["cover_photo"]:
        try:
            await update.message.reply_photo(
                photos["cover_photo"], caption="🖼️ Cover Photo"
            )
        except:
            await update.message.reply_text(photos["cover_photo"])

    if photos["public_photos"]:
        await update.message.reply_text(
            f"📷 Found {len(photos['public_photos'])} public photos:"
        )
        for i, url in enumerate(photos["public_photos"][:5], start=1):
            try:
                await update.message.reply_photo(url, caption=f"Photo {i}")
                time.sleep(1)
            except:
                await update.message.reply_text(url)

    if not any(
        [photos["profile_photo"], photos["cover_photo"], photos["public_photos"]]
    ):
        await update.message.reply_text(
            "❌ No photos found. Profile may be private."
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()


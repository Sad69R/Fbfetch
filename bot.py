import time
from telegram import Update
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
# PUT YOUR BOT TOKEN HERE
# =========================
TELEGRAM_BOT_TOKEN = "8252295424:AAGRllLya9BowzOdoKQvEt42MMTwUSAkn2M"


class FacebookScraper:
    def __init__(self):
        self.driver = None

    def setup_driver(self):
        """Chrome setup compatible with Docker/Railway"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        # Path used inside the Docker image
        chrome_options.binary_location = "/usr/bin/chromium"

        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver

    def scrape_photos(self, profile_url: str):
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(5)

            result = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
            }

            # Try to get profile/cover photo (best-effort)
            try:
                img = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "img[data-imgperflogname='profileCoverPhoto']"
                )
                src = img.get_attribute("src")
                result["profile_photo"] = src
                result["cover_photo"] = src
            except:
                pass

            # Navigate to photos page
            try:
                self.driver.get(profile_url.rstrip("/") + "/photos")
                time.sleep(3)

                # Scroll to load images
                for _ in range(3):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(2)

                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        if src not in result["public_photos"]:
                            result["public_photos"].append(src)
                    if len(result["public_photos"]) >= 5:
                        break
            except:
                pass

            return result

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
        "Send a Facebook profile URL.\n"
        "Example:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if "facebook.com" not in url:
        await update.message.reply_text("Please send a valid Facebook profile URL.")
        return

    await update.message.reply_text("Fetching photos, please wait...")

    scraper = FacebookScraper()
    data = scraper.scrape_photos(url)

    if not data:
        await update.message.reply_text(
            "Failed to fetch photos. The profile may be private or blocked."
        )
        return

    if data["profile_photo"]:
        try:
            await update.message.reply_photo(
                data["profile_photo"], caption="Profile photo"
            )
        except:
            await update.message.reply_text(data["profile_photo"])

    if data["cover_photo"]:
        try:
            await update.message.reply_photo(
                data["cover_photo"], caption="Cover photo"
            )
        except:
            await update.message.reply_text(data["cover_photo"])

    if data["public_photos"]:
        for i, photo in enumerate(data["public_photos"], start=1):
            try:
                await update.message.reply_photo(photo, caption=f"Photo {i}")
                time.sleep(1)
            except:
                await update.message.reply_text(photo)
    else:
        await update.message.reply_text("No public photos found.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

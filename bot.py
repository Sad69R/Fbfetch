import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver

    def scrape_photos(self, profile_url):
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(5)

            photos = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": []
            }

            # Profile / cover photo
            try:
                img = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "img[data-imgperflogname='profileCoverPhoto']"
                )
                src = img.get_attribute("src")
                photos["profile_photo"] = src
                photos["cover_photo"] = src
            except:
                pass

            # Public photos
            try:
                self.driver.get(profile_url.rstrip("/") + "/photos")
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
                    if len(photos["public_photos"]) >= 5:
                        break
            except:
                pass

            return photos

        except Exception as e:
            print("Scraping error:", e)
            return None

        finally:
            if self.driver:
                self.driver.quit()


# =========================
# Telegram handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a Facebook profile URL.\nExample:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text

    if "facebook.com" not in url:
        await update.message.reply_text("Send a valid Facebook profile URL.")
        return

    await update.message.reply_text("Fetching photos, please wait...")

    scraper = FacebookScraper()
    photos = scraper.scrape_photos(url)

    if not photos:
        await update.message.reply_text("Failed to fetch photos.")
        return

    if photos["profile_photo"]:
        await update.message.reply_photo(photos["profile_photo"])

    for photo in photos["public_photos"]:
        await update.message.reply_photo(photo)
        time.sleep(1)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

import time
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.binary_location = "/usr/bin/chromium"  # Docker path

        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver

    def scrape_photos(self, profile_url: str):
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(3)

            result = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
            }

            # Profile photo
            try:
                profile_img = self.driver.find_element(
                    By.CSS_SELECTOR, "image[width='168'], img[data-imgperflogname='profile']"
                )
                result["profile_photo"] = profile_img.get_attribute("src")
            except:
                pass

            # Cover photo
            try:
                cover_img = self.driver.find_element(
                    By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']"
                )
                result["cover_photo"] = cover_img.get_attribute("src")
            except:
                pass

            # Public photos
            try:
                self.driver.get(profile_url.rstrip("/") + "/photos")
                time.sleep(2)
                for _ in range(2):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(1)

                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        if src not in result["public_photos"]:
                            result["public_photos"].append(src)
                    if len(result["public_photos"]) >= 20:
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
        "👋 Welcome! Use the command:\n"
        "/fetchphotos <Facebook Profile URL>\n\n"
        "Example:\n/fetchphotos https://facebook.com/username"
    )


async def fetch_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args  # list of words after command
    if not args:
        await update.message.reply_text("❌ Please provide a Facebook profile URL after the command.")
        return

    url = args[0].strip()
    if "facebook.com" not in url:
        await update.message.reply_text("❌ Please provide a valid Facebook profile URL.")
        return

    await update.message.reply_text("🔍 Fetching photos... this may take a few seconds.")

    scraper = FacebookScraper()
    data = scraper.scrape_photos(url)

    if not data:
        await update.message.reply_text("❌ Failed to fetch photos. The profile may be private or blocked.")
        return

    # Profile photo
    if data["profile_photo"]:
        await update.message.reply_photo(data["profile_photo"], caption="📸 Profile Photo")

    # Cover photo
    if data["cover_photo"]:
        await update.message.reply_photo(data["cover_photo"], caption="🖼️ Cover Photo")

    # Public photos
    public_photos = data["public_photos"]
    if public_photos:
        await update.message.reply_text(f"📷 Found {len(public_photos)} public photos. Sending top {min(20, len(public_photos))}...")
        media = [InputMediaPhoto(url) for url in public_photos[:20]]
        for i in range(0, len(media), 10):  # Telegram media group max 10
            await update.message.reply_media_group(media[i:i+10])
    else:
        await update.message.reply_text("No public photos found.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fetchphotos", fetch_photos))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

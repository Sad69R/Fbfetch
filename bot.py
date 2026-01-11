import time
import random
import os
import logging
from datetime import datetime
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
from dotenv import load_dotenv

# =========================
# Configuration
# =========================
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class FacebookScraper:
    def __init__(self):
        self.driver = None
        self.last_request = None
        self.request_count = 0

    def rate_limit(self):
        if self.last_request:
            elapsed = (datetime.now() - self.last_request).seconds
            if elapsed < 5:
                sleep_time = random.uniform(3, 7)
                time.sleep(sleep_time)

        self.last_request = datetime.now()
        self.request_count += 1

        if self.request_count > 10:
            raise Exception("Rate limit reached for this session")

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        chrome_options.binary_location = "/usr/bin/chromium"
        self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self.driver

    def handle_popups(self):
        selectors = [
            "[aria-label='Close']",
            "[aria-label='close']",
            "div[role='button'][aria-label='Close']"
        ]
        for selector in selectors:
            try:
                self.driver.find_element(By.CSS_SELECTOR, selector).click()
                time.sleep(1)
                break
            except:
                continue

    def scrape_profile(self, profile_url: str):
        try:
            self.rate_limit()
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(random.uniform(3, 6))
            self.handle_popups()

            result = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
                "friends_links": []
            }

            # Profile photo
            try:
                meta = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                result["profile_photo"] = meta.get_attribute("content")
            except:
                pass

            # Cover photo
            try:
                cover = self.driver.find_element(By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']")
                result["cover_photo"] = cover.get_attribute("src")
            except:
                pass

            # Public photos
            self.driver.get(profile_url.rstrip("/") + "/photos")
            time.sleep(3)
            for _ in range(2):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            imgs = self.driver.find_elements(By.TAG_NAME, "img")
            for img in imgs:
                src = img.get_attribute("src")
                if src and "scontent" in src and src not in result["public_photos"]:
                    result["public_photos"].append(src)
                if len(result["public_photos"]) >= 20:
                    break

            # Friends / mentions (best-effort, logged-out)
            self.driver.get(profile_url)
            time.sleep(3)
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                if href and "facebook.com" in href and "profile.php?id=" in href:
                    clean = href.split("?")[0]
                    if clean not in result["friends_links"]:
                        result["friends_links"].append(clean)
                if len(result["friends_links"]) >= 30:
                    break

            return result

        except Exception as e:
            return {"error": str(e)}

        finally:
            if self.driver:
                self.driver.quit()


# =========================
# Telegram handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Facebook Profile Scraper Bot\n\n"
        "Send a Facebook profile link and I will fetch:\n"
        "• Profile photo\n"
        "• Cover photo\n"
        "• Public photos\n"
        "• Public mentions (if available)\n\n"
        "Example:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if "facebook.com" not in url:
        await update.message.reply_text("❌ Please send a valid Facebook profile URL")
        return

    status = await update.message.reply_text("🔍 Fetching data, please wait...")

    scraper = FacebookScraper()
    data = scraper.scrape_profile(url)

    await status.delete()

    if data.get("error"):
        await update.message.reply_text(f"❌ Error:\n{data['error']}")
        return

    if data["profile_photo"]:
        await update.message.reply_photo(data["profile_photo"], caption="📸 Profile Photo")

    if data["cover_photo"]:
        await update.message.reply_photo(data["cover_photo"], caption="🖼️ Cover Photo")

    if data["public_photos"]:
        media = [InputMediaPhoto(p) for p in data["public_photos"][:10]]
        await update.message.reply_media_group(media)

    if data["friends_links"]:
        text = "👥 Found public mentions:\n" + "\n".join(data["friends_links"])
        await update.message.reply_text(text)
    else:
        await update.message.reply_text("👥 No public mentions found")

    await update.message.reply_text("✅ Done")


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()

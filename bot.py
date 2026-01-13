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
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException


# =========================
# Telegram bot token
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

    def scrape_profile(self, profile_url: str):
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(3)

            result = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
                "friends_links": set(),
            }

            # -------------------------
            # Profile photo
            # -------------------------
            try:
                profile_img = self.driver.find_element(
                    By.CSS_SELECTOR, "image[width='168'], img[data-imgperflogname='profile']"
                )
                result["profile_photo"] = profile_img.get_attribute("src")
            except:
                try:
                    meta_profile = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                    result["profile_photo"] = meta_profile.get_attribute("content")
                except:
                    pass

            # -------------------------
            # Cover photo
            # -------------------------
            try:
                cover_img = self.driver.find_element(
                    By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']"
                )
                result["cover_photo"] = cover_img.get_attribute("src")
            except:
                try:
                    meta_cover = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                    result["cover_photo"] = meta_cover.get_attribute("content")
                except:
                    pass

            # -------------------------
            # Public photos
            # -------------------------
            try:
                self.driver.get(profile_url.rstrip("/") + "/photos")
                time.sleep(2)
                for _ in range(2):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        result["public_photos"].append(src)
                    if len(result["public_photos"]) >= 20:
                        break
            except:
                pass

            # -------------------------
            # Friends mentions/tags/comments
            # -------------------------
            try:
                self.driver.get(profile_url)
                time.sleep(2)
                # scroll down to load posts
                for _ in range(3):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                # Expand comments dynamically
                for _ in range(5):
                    try:
                        more_comments = self.driver.find_elements(
                            By.XPATH, "//span[contains(text(),'View more comments')]"
                        )
                        for btn in more_comments:
                            try:
                                btn.click()
                                time.sleep(0.5)
                            except (ElementClickInterceptedException, NoSuchElementException):
                                continue
                    except:
                        break

                # Collect links inside posts and comments
                links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href")
                    if href and "facebook.com/" in href:
                        if any(x in href for x in ["profile.php?id=", "/friends"]):
                            result["friends_links"].add(href)

            except:
                pass

            # Limit top 30 friends links
            result["friends_links"] = list(result["friends_links"])[:30]

            return result

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
        "👋 Send me a Facebook profile URL and I will fetch:\n"
        "• Profile photo\n"
        "• Cover photo\n"
        "• Public photos (top 20)\n"
        "• Friends mentions/comments/tags links (top 30)\n\n"
        "Example:\nhttps://facebook.com/username"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if "facebook.com" not in url:
        await update.message.reply_text("❌ Please send a valid Facebook profile URL.")
        return

    await update.message.reply_text("🔍 Fetching data... this may take a few seconds.")

    scraper = FacebookScraper()
    data = scraper.scrape_profile(url)

    if not data:
        await update.message.reply_text("❌ Failed to fetch data. The profile may be private or blocked.")
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
        await update.message.reply_text(
            f"📷 Found {len(public_photos)} public photos. Sending top {min(20, len(public_photos))}..."
        )
        media = [InputMediaPhoto(url) for url in public_photos[:20]]
        for i in range(0, len(media), 10):
            await update.message.reply_media_group(media[i:i+10])
    else:
        await update.message.reply_text("No public photos found.")

    # Friends links
    friends_links = data["friends_links"]
    if friends_links:
        text = "👥 Found friends mentions/comments/tags (top 30):\n" + "\n".join(friends_links)
        await update.message.reply_text(text)
    else:
        await update.message.reply_text("No friends mentions/comments/tags found.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

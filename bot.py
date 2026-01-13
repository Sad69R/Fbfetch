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
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    TimeoutException
)

TELEGRAM_BOT_TOKEN = ("8252295424:AAGRllLya9BowzOdoKQvEt42MMTwUSAkn2M")

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FacebookScraper:
    def __init__(self):
        self.driver = None
        self.last_request = None
        self.request_count = 0

    def rate_limit(self):
        """Prevent detection with rate limiting"""
        if self.last_request:
            elapsed = (datetime.now() - self.last_request).seconds
            if elapsed < 5:
                sleep_time = random.uniform(3, 7)
                logger.info(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self.last_request = datetime.now()
        self.request_count += 1
        
        # Stop after 10 requests per session to avoid bans
        if self.request_count > 10:
            raise Exception("Rate limit reached for this session")

    def setup_driver(self):
        """Setup Chrome driver with anti-detection measures"""
        chrome_options = Options()
        
        # Headless mode (comment out for debugging)
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Anti-detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Realistic user agent
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Docker path (change if needed)
        chrome_options.binary_location = "/usr/bin/chromium"
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Hide webdriver flag
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        
        logger.info("Chrome driver initialized")
        return self.driver

    def handle_popups(self):
        """Close common Facebook popups"""
        try:
            # Try to close login popup
            close_selectors = [
                "[aria-label='Close']",
                "[aria-label='close']",
                "div[role='button'][aria-label='Close']"
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    close_btn.click()
                    time.sleep(1)
                    logger.info("Closed popup")
                    break
                except:
                    continue
        except Exception as e:
            logger.debug(f"No popup to close: {e}")

    def scrape_profile(self, profile_url: str):
        """Main scraping function"""
        try:
            self.rate_limit()
            self.setup_driver()
            
            logger.info(f"Scraping profile: {profile_url}")
            self.driver.get(profile_url)
            
            # Wait for page load
            sleep_time = random.uniform(3, 6)
            time.sleep(sleep_time)
            
            # Handle popups
            self.handle_popups()
            
            result = {
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
                "friends_links": set(),
                "error": None
            }

            # -------------------------
            # Profile photo with fallbacks
            # -------------------------
            profile_selectors = [
                "svg image[width='168']",
                "image[width='168']",
                "img[data-imgperflogname='profileCoverPhoto']",
                "img.profilePic",
            ]
            
            for selector in profile_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    src = elem.get_attribute("src") or elem.get_attribute("xlink:href")
                    if src and ("scontent" in src or "fbcdn" in src):
                        result["profile_photo"] = src
                        logger.info("Profile photo found")
                        break
                except:
                    continue
            
            # Fallback to og:image meta tag
            if not result["profile_photo"]:
                try:
                    meta_profile = self.driver.find_element(
                        By.CSS_SELECTOR, "meta[property='og:image']"
                    )
                    result["profile_photo"] = meta_profile.get_attribute("content")
                    logger.info("Profile photo found via meta tag")
                except:
                    logger.warning("Profile photo not found")

            # -------------------------
            # Cover photo
            # -------------------------
            cover_selectors = [
                "img[data-imgperflogname='profileCoverPhoto']",
                "img[class*='cover']",
                "div[data-pagelet='ProfileCover'] img"
            ]
            
            for selector in cover_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    src = elem.get_attribute("src")
                    if src and "scontent" in src:
                        result["cover_photo"] = src
                        logger.info("Cover photo found")
                        break
                except:
                    continue

            # -------------------------
            # Public photos
            # -------------------------
            try:
                photos_url = profile_url.rstrip("/") + "/photos"
                logger.info(f"Navigating to photos: {photos_url}")
                self.driver.get(photos_url)
                time.sleep(random.uniform(2, 4))
                
                self.handle_popups()
                
                # Scroll to load more photos
                for i in range(2):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(random.uniform(1, 2))
                    logger.info(f"Scroll {i+1}/2")

                # Collect photo URLs
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and ("scontent" in src or "fbcdn" in src):
                        # Avoid duplicates and low-quality images
                        if src not in result["public_photos"] and "p130x130" not in src:
                            result["public_photos"].append(src)
                    
                    if len(result["public_photos"]) >= 20:
                        break
                
                logger.info(f"Found {len(result['public_photos'])} public photos")
                
            except Exception as e:
                logger.error(f"Error scraping photos: {e}")

            # -------------------------
            # Friends mentions/tags/comments
            # -------------------------
            try:
                logger.info("Returning to profile for friends links")
                self.driver.get(profile_url)
                time.sleep(random.uniform(2, 4))
                
                self.handle_popups()
                
                # Scroll to load posts
                for i in range(3):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(random.uniform(1, 2))
                    logger.info(f"Post scroll {i+1}/3")

                # Try to expand comments
                for attempt in range(5):
                    try:
                        more_comments_selectors = [
                            "//span[contains(text(),'View more comments')]",
                            "//span[contains(text(),'more comments')]",
                            "//div[contains(@aria-label, 'comments')]"
                        ]
                        
                        for selector in more_comments_selectors:
                            try:
                                buttons = self.driver.find_elements(By.XPATH, selector)
                                for btn in buttons[:3]:  # Limit to avoid detection
                                    try:
                                        btn.click()
                                        time.sleep(random.uniform(0.5, 1))
                                    except:
                                        continue
                            except:
                                continue
                    except:
                        break

                # Collect profile links
                links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    try:
                        href = link.get_attribute("href")
                        if href and "facebook.com/" in href:
                            # Filter for profile/friend links
                            if any(x in href for x in ["profile.php?id=", "/people/", "/friends"]):
                                # Clean URL
                                clean_href = href.split("?")[0] if "?" in href else href
                                result["friends_links"].add(clean_href)
                            
                            if len(result["friends_links"]) >= 30:
                                break
                    except:
                        continue
                
                logger.info(f"Found {len(result['friends_links'])} friend links")

            except Exception as e:
                logger.error(f"Error scraping friends: {e}")

            # Convert set to list and limit
            result["friends_links"] = list(result["friends_links"])[:30]

            return result

        except Exception as e:
            logger.error(f"Scraping error: {e}", exc_info=True)
            return {"error": str(e)}

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Driver closed")


# =========================
# Telegram handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    logger.info(f"Start command from user {user_id} (@{username})")
    
    await update.message.reply_text(
        "👋 <b>Facebook Profile Scraper Bot</b>\n\n"
        "Send me a Facebook profile URL and I will fetch:\n"
        "• 📸 Profile photo\n"
        "• 🖼️ Cover photo\n"
        "• 📷 Public photos (up to 20)\n"
        "• 👥 Friends mentions/tags (up to 30 links)\n\n"
        "<b>Example:</b>\n"
        "<code>https://facebook.com/username</code>\n\n"
        "⚠️ <b>Note:</b> Only public data can be accessed without login. "
        "Private profiles will return limited information.",
        parse_mode='HTML'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message handler for profile URLs"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    
    url = (update.message.text or "").strip()
    
    # Validate URL
    if not url.startswith(("https://facebook.com/", "https://www.facebook.com/", "https://m.facebook.com/")):
        await update.message.reply_text(
            "❌ <b>Invalid URL</b>\n\n"
            "Please send a valid Facebook profile URL.\n\n"
            "<b>Examples:</b>\n"
            "• <code>https://facebook.com/username</code>\n"
            "• <code>https://www.facebook.com/profile.php?id=123456</code>",
            parse_mode='HTML'
        )
        return
    
    # Log request
    logger.info(f"User {user_id} (@{username}) requested: {url}")
    
    status_msg = await update.message.reply_text(
        "🔍 <b>Fetching data...</b>\n\n"
        "This may take 30-60 seconds.\n"
        "Please wait...",
        parse_mode='HTML'
    )
    
    try:
        scraper = FacebookScraper()
        data = scraper.scrape_profile(url)
        
        # Check for errors
        if data.get("error"):
            logger.error(f"Scraping failed for {url}: {data['error']}")
            await status_msg.edit_text(
                f"❌ <b>Error occurred</b>\n\n"
                f"<code>{data['error']}</code>\n\n"
                "<b>This may be due to:</b>\n"
                "• Profile is private or deleted\n"
                "• Facebook blocked the request\n"
                "• Rate limiting (try again later)\n"
                "• Invalid or inaccessible URL\n"
                "• Anti-bot measures detected",
                parse_mode='HTML'
            )
            return
        
        # Delete status message
        await status_msg.delete()
        
        # Profile photo
        if data["profile_photo"]:
            try:
                await update.message.reply_photo(
                    data["profile_photo"],
                    caption="📸 <b>Profile Photo</b>",
                    parse_mode='HTML'
                )
                logger.info("Sent profile photo")
            except Exception as e:
                logger.error(f"Failed to send profile photo: {e}")
                await update.message.reply_text(
                    f"❌ Could not send profile photo\n<code>{data['profile_photo']}</code>",
                    parse_mode='HTML'
                )

        # Cover photo
        if data["cover_photo"]:
            try:
                await update.message.reply_photo(
                    data["cover_photo"],
                    caption="🖼️ <b>Cover Photo</b>",
                    parse_mode='HTML'
                )
                logger.info("Sent cover photo")
            except Exception as e:
                logger.error(f"Failed to send cover photo: {e}")

        # Public photos
        public_photos = data["public_photos"]
        if public_photos:
            await update.message.reply_text(
                f"📷 <b>Found {len(public_photos)} public photo(s)</b>\n\n"
                f"Sending top {min(20, len(public_photos))}...",
                parse_mode='HTML'
            )
            
            try:
                # Send in batches of 10 (Telegram media group limit)
                media_groups = [public_photos[i:i+10] for i in range(0, len(public_photos), 10)]
                
                for idx, group in enumerate(media_groups):
                    media = [InputMediaPhoto(url) for url in group]
                    await update.message.reply_media_group(media)
                    logger.info(f"Sent photo group {idx+1}/{len(media_groups)}")
                    
                    # Small delay between groups
                    if idx < len(media_groups) - 1:
                        time.sleep(1)
                        
            except Exception as e:
                logger.error(f"Failed to send photos: {e}")
                await update.message.reply_text(
                    "❌ Some photos could not be sent. They may be protected or unavailable."
                )
        else:
            await update.message.reply_text(
                "📷 No public photos found.\n\n"
                "The profile may be private or have no photos."
            )

        # Friends links
        friends_links = data["friends_links"]
        if friends_links:
            links_text = "\n".join([f"• {link}" for link in friends_links])
            message_text = (
                f"👥 <b>Found {len(friends_links)} friend link(s)</b>\n\n"
                f"<i>Links from mentions/comments/tags:</i>\n\n"
                f"{links_text}"
            )
            
            # Telegram message limit is 4096 characters
            if len(message_text) > 4000:
                # Split into multiple messages
                chunks = [friends_links[i:i+15] for i in range(0, len(friends_links), 15)]
                for idx, chunk in enumerate(chunks):
                    chunk_text = "\n".join([f"• {link}" for link in chunk])
                    await update.message.reply_text(
                        f"👥 <b>Friend links ({idx+1}/{len(chunks)})</b>\n\n{chunk_text}",
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(message_text, parse_mode='HTML')
            
            logger.info(f"Sent {len(friends_links)} friend links")
        else:
            await update.message.reply_text(
                "👥 No friend mentions/comments/tags found.\n\n"
                "The profile may be private or have no visible interactions."
            )
        
        # Summary
        await update.message.reply_text(
            "✅ <b>Scraping complete!</b>\n\n"
            f"• Profile photo: {'✓' if data['profile_photo'] else '✗'}\n"
            f"• Cover photo: {'✓' if data['cover_photo'] else '✗'}\n"
            f"• Public photos: {len(public_photos)}\n"
            f"• Friend links: {len(friends_links)}",
            parse_mode='HTML'
        )
        
        logger.info(f"Successfully completed scraping for {url}")

    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ <b>An unexpected error occurred</b>\n\n"
            "Please try again later or contact support.\n\n"
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


def main():
    """Main bot function"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        print("ERROR: Please set TELEGRAM_BOT_TOKEN in your .env file")
        return
    
    logger.info("Starting bot...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running and polling for updates...")
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

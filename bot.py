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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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

    def setup_driver(self):
        """Setup Chrome driver optimized for speed"""
        chrome_options = Options()
        
        # Performance optimizations
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Disable images for faster loading (except for photo pages)
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Anti-detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # User agent
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Docker path
        chrome_options.binary_location = "/usr/bin/chromium"
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(15)
        
        # Hide webdriver
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        
        logger.info("Chrome driver initialized")
        return self.driver

    def quick_close_popups(self):
        """Quickly close popups without waiting"""
        try:
            close_selectors = [
                "[aria-label='Close']",
                "[aria-label='close']",
                "div[role='button'][aria-label='Close']",
                "[data-testid='cookie-policy-manage-dialog-accept-button']"
            ]
            
            for selector in close_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        elements[0].click()
                        time.sleep(0.3)
                        logger.info("Closed popup")
                        break
                except:
                    continue
        except:
            pass

    def get_profile_photo(self):
        """Enhanced profile photo extraction with multiple methods"""
        profile_photo = None
        
        # Method 1: SVG image element (most common)
        try:
            svg_images = self.driver.find_elements(By.CSS_SELECTOR, "svg image")
            for img in svg_images:
                href = img.get_attribute("xlink:href") or img.get_attribute("href")
                if href and ("scontent" in href or "fbcdn" in href):
                    # Get the highest quality version
                    if "_nc_cat" in href or "_nc_ohc" in href:
                        profile_photo = href
                        logger.info("Profile photo found via SVG")
                        break
        except:
            pass
        
        # Method 2: Profile picture link
        if not profile_photo:
            try:
                profile_link = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    "a[href*='/photo/'], a[href*='/profile/picture/']"
                )
                href = profile_link.get_attribute("href")
                if href:
                    # Extract image from link
                    imgs = profile_link.find_elements(By.TAG_NAME, "img")
                    if imgs:
                        src = imgs[0].get_attribute("src")
                        if src and ("scontent" in src or "fbcdn" in src):
                            profile_photo = src
                            logger.info("Profile photo found via link")
            except:
                pass
        
        # Method 3: All images on page
        if not profile_photo:
            try:
                all_imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in all_imgs[:15]:  # Check first 15 images only
                    src = img.get_attribute("src")
                    if src and ("scontent" in src or "fbcdn" in src):
                        # Look for profile-related attributes
                        alt = img.get_attribute("alt") or ""
                        if "profile" in alt.lower() or img.get_attribute("data-imgperflogname"):
                            profile_photo = src
                            logger.info("Profile photo found via img scan")
                            break
            except:
                pass
        
        # Method 4: Meta tag fallback
        if not profile_photo:
            try:
                meta = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                profile_photo = meta.get_attribute("content")
                logger.info("Profile photo found via meta tag")
            except:
                pass
        
        return profile_photo

    def get_cover_photo(self):
        """Enhanced cover photo extraction"""
        cover_photo = None
        
        # Method 1: Cover photo specific selectors
        cover_selectors = [
            "img[data-imgperflogname='profileCoverPhoto']",
            "div[data-pagelet='ProfileCover'] img",
            "a[href*='cover_photo'] img",
            "img[class*='cover']"
        ]
        
        for selector in cover_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                src = elem.get_attribute("src")
                if src and "scontent" in src and "p720x720" not in src:
                    cover_photo = src
                    logger.info(f"Cover photo found via {selector}")
                    break
            except:
                continue
        
        # Method 2: Large images scan
        if not cover_photo:
            try:
                large_imgs = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    "img[width], img[height]"
                )
                for img in large_imgs:
                    try:
                        width = int(img.get_attribute("width") or 0)
                        height = int(img.get_attribute("height") or 0)
                        if width > 400 or height > 200:
                            src = img.get_attribute("src")
                            if src and "scontent" in src:
                                cover_photo = src
                                logger.info("Cover photo found via size")
                                break
                    except:
                        continue
            except:
                pass
        
        return cover_photo

    def extract_user_info(self, profile_url: str):
        """Extract Facebook user ID and username"""
        user_id = None
        username = None
        
        # Method 1: Extract from URL
        try:
            if "profile.php?id=" in profile_url:
                # Direct numeric ID in URL
                user_id = profile_url.split("profile.php?id=")[1].split("&")[0]
                logger.info(f"User ID from URL: {user_id}")
            elif "/people/" in profile_url:
                # People URL format
                parts = profile_url.split("/people/")[1].split("/")
                username = parts[0]
                if len(parts) > 1:
                    user_id = parts[1]
                logger.info(f"Username: {username}, ID: {user_id}")
            else:
                # Username in URL
                username = profile_url.rstrip("/").split("/")[-1]
                if username and username not in ["www.facebook.com", "facebook.com"]:
                    logger.info(f"Username from URL: {username}")
        except Exception as e:
            logger.error(f"Error extracting from URL: {e}")
        
        # Method 2: Extract from page source
        if not user_id:
            try:
                # Look for user ID in meta tags
                meta_selectors = [
                    "meta[property='al:android:url']",
                    "meta[property='al:ios:url']",
                ]
                
                for selector in meta_selectors:
                    try:
                        meta = self.driver.find_element(By.CSS_SELECTOR, selector)
                        content = meta.get_attribute("content")
                        if content and "id=" in content:
                            user_id = content.split("id=")[1].split("&")[0]
                            logger.info(f"User ID from meta: {user_id}")
                            break
                    except:
                        continue
            except:
                pass
        
        # Method 3: Extract from page links
        if not user_id:
            try:
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='profile.php?id=']")
                if links:
                    href = links[0].get_attribute("href")
                    user_id = href.split("profile.php?id=")[1].split("&")[0]
                    logger.info(f"User ID from link: {user_id}")
            except:
                pass
        
        # Method 4: Look in page source for entity_id or profile_id
        if not user_id:
            try:
                page_source = self.driver.page_source
                
                # Search for common ID patterns
                import re
                patterns = [
                    r'"entity_id":"(\d+)"',
                    r'"userID":"(\d+)"',
                    r'"profile_id":"(\d+)"',
                    r'profileID=(\d+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, page_source)
                    if match:
                        user_id = match.group(1)
                        logger.info(f"User ID from page source: {user_id}")
                        break
            except:
                pass
        
        return user_id, username

    def scrape_profile(self, profile_url: str):
        """Optimized scraping function"""
        try:
            self.setup_driver()
            
            logger.info(f"Scraping profile: {profile_url}")
            
            result = {
                "user_id": None,
                "username": None,
                "profile_photo": None,
                "cover_photo": None,
                "public_photos": [],
                "friends_links": [],
                "error": None
            }

            # Load main profile page
            try:
                self.driver.get(profile_url)
                time.sleep(2)  # Reduced wait time
                self.quick_close_popups()
            except TimeoutException:
                logger.warning("Page load timeout, continuing anyway")
            
            # Extract User ID and Username
            result["user_id"], result["username"] = self.extract_user_info(profile_url)
            
            # Get profile and cover photos
            result["profile_photo"] = self.get_profile_photo()
            result["cover_photo"] = self.get_cover_photo()
            
            # -------------------------
            # Public photos (faster method)
            # -------------------------
            try:
                photos_url = profile_url.rstrip("/") + "/photos"
                logger.info(f"Loading photos: {photos_url}")
                
                # Re-enable images for photo page
                self.driver.execute_cdp_cmd('Emulation.setDefaultBackgroundColorOverride', {'color': {'r': 255, 'g': 255, 'b': 255, 'a': 1}})
                
                try:
                    self.driver.get(photos_url)
                    time.sleep(2)
                except TimeoutException:
                    pass
                
                self.quick_close_popups()
                
                # Single scroll to load initial photos
                self.driver.execute_script("window.scrollTo(0, 800);")
                time.sleep(1)
                
                # Quick photo collection
                seen = set()
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                
                for img in imgs:
                    if len(result["public_photos"]) >= 20:
                        break
                    
                    src = img.get_attribute("src")
                    if src and ("scontent" in src or "fbcdn" in src):
                        # Filter out low quality thumbnails
                        if all(x not in src for x in ["p130x130", "p75x75", "s32x32"]):
                            if src not in seen:
                                seen.add(src)
                                result["public_photos"].append(src)
                
                logger.info(f"Collected {len(result['public_photos'])} photos")
                
            except Exception as e:
                logger.error(f"Error getting photos: {e}")

            # -------------------------
            # Friends links (simplified)
            # -------------------------
            try:
                logger.info("Collecting friend links")
                self.driver.get(profile_url)
                time.sleep(1.5)
                
                # Single scroll
                self.driver.execute_script("window.scrollTo(0, 1000);")
                time.sleep(1)
                
                # Collect links quickly
                links = self.driver.find_elements(By.TAG_NAME, "a")
                friends_set = set()
                
                for link in links[:100]:  # Limit scan
                    try:
                        href = link.get_attribute("href")
                        if href and "facebook.com/" in href:
                            if any(x in href for x in ["profile.php?id=", "/people/", "/friends"]):
                                clean = href.split("?")[0]
                                friends_set.add(clean)
                                
                                if len(friends_set) >= 30:
                                    break
                    except:
                        continue
                
                result["friends_links"] = list(friends_set)[:30]
                logger.info(f"Found {len(result['friends_links'])} friend links")
                
            except Exception as e:
                logger.error(f"Error getting friends: {e}")

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
        "👋 <b>Facebook Profile Bot</b>\n\n"
        "Send me a Facebook profile URL\n"
        "<b>Example:</b>\n"
        "<code>https://facebook.com/username</code>\n\n"
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
    
    logger.info(f"User {user_id} (@{username}) requested: {url}")
    
    status_msg = await update.message.reply_text(
        "🔍 <b>Searching Photos...</b>\n\n"
        "This should take 15-30 seconds.\n"
        "Please wait...",
        parse_mode='HTML'
    )
    
    try:
        scraper = FacebookScraper()
        data = scraper.scrape_profile(url)
        
        if data.get("error"):
            logger.error(f"Scraping failed: {data['error']}")
            await status_msg.edit_text(
                f"❌ <b>Error occurred</b>\n\n"
                f"<code>{data['error']}</code>\n\n"
                "<b>Possible causes:</b>\n"
                "• Profile is private or deleted\n"
                "• Facebook blocked the request\n"
                "• Invalid URL\n"
                "• Network timeout",
                parse_mode='HTML'
            )
            return
        
        await status_msg.delete()
        
        # User ID and Username
        user_info_parts = []
        if data.get("user_id"):
            user_info_parts.append(f"🆔 <b>User ID:</b> <code>{data['user_id']}</code>")
        if data.get("username"):
            user_info_parts.append(f"👤 <b>Username:</b> <code>{data['username']}</code>")
        
        if user_info_parts:
            await update.message.reply_text(
                "\n".join(user_info_parts),
                parse_mode='HTML'
            )
            logger.info(f"Sent user info: ID={data.get('user_id')}, Username={data.get('username')}")
        
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
        else:
            await update.message.reply_text("📸 No profile photo found (may be private)")

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
        else:
            await update.message.reply_text("🖼️ No cover photo found")

        # Public photos
        public_photos = data["public_photos"]
        if public_photos:
            await update.message.reply_text(
                f"📷 <b>Found {len(public_photos)} public photo(s)</b>\n\n"
                f"Sending now...",
                parse_mode='HTML'
            )
            
            try:
                media_groups = [public_photos[i:i+10] for i in range(0, len(public_photos), 10)]
                
                for idx, group in enumerate(media_groups):
                    media = [InputMediaPhoto(url) for url in group]
                    await update.message.reply_media_group(media)
                    logger.info(f"Sent photo group {idx+1}/{len(media_groups)}")
                    
                    if idx < len(media_groups) - 1:
                        time.sleep(0.5)
                        
            except Exception as e:
                logger.error(f"Failed to send photos: {e}")
                await update.message.reply_text(
                    "❌ Some photos could not be sent."
                )
        else:
            await update.message.reply_text(
                "📷 No public photos found (profile may be private)"
            )

        # Friends links
        friends_links = data["friends_links"]
        if friends_links:
            links_text = "\n".join([f"• {link}" for link in friends_links])
            message_text = (
                f"👥 <b>Found {len(friends_links)} friend link(s)</b>\n\n"
                f"{links_text}"
            )
            
            if len(message_text) > 4000:
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
            await update.message.reply_text("👥 No friend links found")
        
        # Summary
        await update.message.reply_text(
            "✅ <b>Search complete!</b>\n\n"
            f"• User ID: {data.get('user_id') or '✗'}\n"
            f"• Username: {data.get('username') or '✗'}\n"
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
            f"<code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


def main():
    """Main bot function"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        print("ERROR: Set TELEGRAM_BOT_TOKEN in .env file")
        return
    
    logger.info("Starting bot...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot running...")
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import time
import random
import os
import logging
import requests
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

    def extract_user_id_from_url(self, profile_url: str):
        """Extract user ID directly from URL"""
        user_id = None
        username = None
        
        try:
            if "profile.php?id=" in profile_url:
                user_id = profile_url.split("profile.php?id=")[1].split("&")[0]
                logger.info(f"User ID from URL: {user_id}")
            elif "/people/" in profile_url:
                parts = profile_url.split("/people/")[1].split("/")
                username = parts[0]
                if len(parts) > 1:
                    user_id = parts[1]
                logger.info(f"Username: {username}, ID: {user_id}")
            else:
                username = profile_url.rstrip("/").split("/")[-1].split("?")[0]
                if username and username not in ["www.facebook.com", "facebook.com", "m.facebook.com"]:
                    logger.info(f"Username from URL: {username}")
        except Exception as e:
            logger.error(f"Error extracting from URL: {e}")
        
        return user_id, username

    def get_profile_photo_via_graph_api(self, user_id: str):
        """Get profile photo using Facebook Graph API"""
        if not user_id:
            return None, None
        
        try:
            # Try multiple Graph API methods
            
            # Method 1: Direct redirect URL (simplest, most reliable)
            direct_url = f"https://graph.facebook.com/{user_id}/picture?type=large&width=720&height=720"
            logger.info(f"Trying direct Graph API URL: {direct_url}")
            
            # Test if the URL is accessible
            test_response = requests.head(direct_url, timeout=10, allow_redirects=True)
            if test_response.status_code == 200:
                final_url = test_response.url  # This is the actual image URL after redirect
                logger.info(f"✓ Profile photo found via Graph API: {final_url}")
                return final_url, False
            
            # Method 2: Non-redirect API call to get JSON response
            json_url = f"https://graph.facebook.com/{user_id}/picture?type=large&redirect=0&width=720&height=720"
            logger.info(f"Trying JSON Graph API URL: {json_url}")
            
            response = requests.get(json_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Graph API JSON response: {data}")
                
                if data.get("data") and data["data"].get("url"):
                    profile_url = data["data"]["url"]
                    is_silhouette = data["data"].get("is_silhouette", False)
                    
                    logger.info(f"✓ Profile photo from JSON: {profile_url}, silhouette: {is_silhouette}")
                    return profile_url, is_silhouette
            
            # Method 3: Try different sizes
            for size in ["large", "normal", "small"]:
                fallback_url = f"https://graph.facebook.com/{user_id}/picture?type={size}"
                logger.info(f"Trying fallback size: {size}")
                test = requests.head(fallback_url, timeout=10, allow_redirects=True)
                if test.status_code == 200:
                    logger.info(f"✓ Fallback successful with size: {size}")
                    return test.url, False
            
            logger.warning("❌ Could not fetch profile photo via any Graph API method")
            return None, None
            
        except Exception as e:
            logger.error(f"❌ Error getting profile photo via Graph API: {e}")
            return None, None

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
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Disable images for faster loading
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

    def get_profile_photo_from_page(self):
        """Extract profile photo directly from page HTML/DOM"""
        profile_photo = None
        
        # Method 1: SVG image elements (most reliable for mobile view)
        try:
            svg_images = self.driver.find_elements(By.CSS_SELECTOR, "svg image")
            for img in svg_images:
                href = img.get_attribute("xlink:href") or img.get_attribute("href")
                if href and ("scontent" in href or "fbcdn" in href):
                    # Look for high-quality indicators
                    if "_nc_cat" in href or "_nc_ohc" in href or "p720x720" in href:
                        profile_photo = href
                        logger.info(f"✓ Profile photo from SVG: {href[:100]}...")
                        break
                    elif not profile_photo:  # Store as fallback
                        profile_photo = href
        except Exception as e:
            logger.debug(f"SVG method failed: {e}")
        
        # Method 2: Image tags with specific attributes
        if not profile_photo:
            try:
                selectors = [
                    "img[data-imgperflogname='profileCoverPhoto']",
                    "img[alt][src*='scontent']",
                    "a[href*='photo'] img[src*='scontent']",
                ]
                
                for selector in selectors:
                    imgs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in imgs:
                        src = img.get_attribute("src")
                        if src and "scontent" in src:
                            # Avoid cover photos and small thumbnails
                            if "p720x720" not in src and "p130x130" not in src:
                                alt = (img.get_attribute("alt") or "").lower()
                                # Check if it's likely a profile photo
                                if "profile" in alt or not alt:
                                    profile_photo = src
                                    logger.info(f"✓ Profile photo from img tag: {src[:100]}...")
                                    break
                    if profile_photo:
                        break
            except Exception as e:
                logger.debug(f"IMG tag method failed: {e}")
        
        # Method 3: Look in page source for high-res image URLs
        if not profile_photo:
            try:
                import re
                page_source = self.driver.page_source
                
                # Find all scontent URLs
                pattern = r'https://scontent[^"\'>\s]+\.(?:jpg|jpeg|png)'
                matches = re.findall(pattern, page_source)
                
                # Filter for likely profile photos (medium to large size indicators)
                for url in matches:
                    if any(size in url for size in ["_n.", "_s.", "_b."]) and "p720x720" not in url:
                        profile_photo = url
                        logger.info(f"✓ Profile photo from page source: {url[:100]}...")
                        break
            except Exception as e:
                logger.debug(f"Page source method failed: {e}")
        
        # Method 4: Try mobile view which sometimes shows images differently
        if not profile_photo:
            try:
                current_url = self.driver.current_url
                if "m.facebook.com" not in current_url:
                    mobile_url = current_url.replace("www.facebook.com", "m.facebook.com").replace("facebook.com", "m.facebook.com")
                    logger.info(f"Trying mobile view: {mobile_url}")
                    self.driver.get(mobile_url)
                    time.sleep(1)
                    
                    # Re-try SVG method on mobile
                    svg_images = self.driver.find_elements(By.CSS_SELECTOR, "svg image, img[src*='scontent']")
                    for img in svg_images:
                        src = img.get_attribute("src") or img.get_attribute("xlink:href") or img.get_attribute("href")
                        if src and "scontent" in src and "p130x130" not in src:
                            profile_photo = src
                            logger.info(f"✓ Profile photo from mobile: {src[:100]}...")
                            break
            except Exception as e:
                logger.debug(f"Mobile view method failed: {e}")
        
        return profile_photo
        """Quickly close popups"""
        try:
            close_selectors = [
                "[aria-label='Close']",
                "[aria-label='close']",
                "div[role='button'][aria-label='Close']",
            ]
            
            for selector in close_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        elements[0].click()
                        time.sleep(0.3)
                        break
                except:
                    continue
        except:
            pass

    def get_cover_photo(self):
        """Get cover photo from page"""
        cover_photo = None
        
        cover_selectors = [
            "img[data-imgperflogname='profileCoverPhoto']",
            "div[data-pagelet='ProfileCover'] img",
            "a[href*='cover_photo'] img",
        ]
        
        for selector in cover_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                src = elem.get_attribute("src")
                if src and "scontent" in src:
                    cover_photo = src
                    logger.info(f"Cover photo found")
                    break
            except:
                continue
        
        return cover_photo

    def extract_user_id_from_page(self):
        """Extract user ID from page source if not in URL"""
        user_id = None
        
        try:
            # Method 1: Meta tags
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
                        return user_id
                except:
                    continue
            
            # Method 2: Profile links
            links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='profile.php?id=']")
            if links:
                href = links[0].get_attribute("href")
                user_id = href.split("profile.php?id=")[1].split("&")[0]
                logger.info(f"User ID from link: {user_id}")
                return user_id
            
            # Method 3: Page source regex
            import re
            page_source = self.driver.page_source
            patterns = [
                r'"entity_id":"(\d+)"',
                r'"userID":"(\d+)"',
                r'"profile_id":"(\d+)"',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_source)
                if match:
                    user_id = match.group(1)
                    logger.info(f"User ID from page source: {user_id}")
                    return user_id
                    
        except Exception as e:
            logger.error(f"Error extracting user ID from page: {e}")
        
        return user_id

    def scrape_profile(self, profile_url: str):
        """Main scraping function using Graph API + web scraping"""
        try:
            result = {
                "user_id": None,
                "username": None,
                "profile_photo": None,
                "profile_photo_hd": None,
                "cover_photo": None,
                "public_photos": [],
                "friends_links": [],
                "is_silhouette": False,
                "error": None
            }

            # Step 1: Extract user ID from URL
            user_id, username = self.extract_user_id_from_url(profile_url)
            result["user_id"] = user_id
            result["username"] = username
            
            # Step 2: If we have user ID, try Graph API first (fast but may return silhouette)
            graph_api_photo = None
            if user_id:
                logger.info(f"Attempting Graph API for user ID: {user_id}")
                graph_api_photo, is_silhouette = self.get_profile_photo_via_graph_api(user_id)
                if graph_api_photo and not is_silhouette:
                    result["profile_photo"] = graph_api_photo
                    result["profile_photo_hd"] = graph_api_photo
                    result["is_silhouette"] = False
                    logger.info(f"✓✓✓ Profile photo via Graph API (not silhouette)")
                elif is_silhouette:
                    logger.warning(f"⚠️ Graph API returned silhouette, will try scraping")
            
            # Step 3: Setup Selenium and scrape if Graph API failed or returned silhouette
            self.setup_driver()
            
            logger.info(f"Loading profile page: {profile_url}")
            try:
                self.driver.get(profile_url)
                time.sleep(2)
                self.quick_close_popups()
            except TimeoutException:
                logger.warning("Page load timeout, continuing")
            
            # Step 4: If no profile photo yet (or silhouette), scrape from page
            if not result["profile_photo"] or result.get("is_silhouette"):
                logger.info("Attempting to scrape profile photo from page...")
                scraped_photo = self.get_profile_photo_from_page()
                if scraped_photo:
                    result["profile_photo"] = scraped_photo
                    result["profile_photo_hd"] = scraped_photo
                    result["is_silhouette"] = False
                    logger.info(f"✓✓✓ Profile photo scraped from page!")
            
            # Step 5: If still no user ID, extract from page
            if not result["user_id"]:
                result["user_id"] = self.extract_user_id_from_page()
                
                # Try Graph API again if we now have user ID
                if result["user_id"] and not result["profile_photo"]:
                    profile_photo, is_silhouette = self.get_profile_photo_via_graph_api(result["user_id"])
                    if profile_photo:
                        result["profile_photo"] = profile_photo
                        result["profile_photo_hd"] = profile_photo
                        result["is_silhouette"] = is_silhouette
            
            # Step 6: Get cover photo
            result["cover_photo"] = self.get_cover_photo()
            
            # Step 7: Get public photos
            try:
                photos_url = profile_url.rstrip("/").split("?")[0] + "/photos"
                logger.info(f"Loading photos: {photos_url}")
                
                try:
                    self.driver.get(photos_url)
                    time.sleep(2)
                except TimeoutException:
                    pass
                
                self.quick_close_popups()
                
                # Single scroll
                self.driver.execute_script("window.scrollTo(0, 800);")
                time.sleep(1)
                
                # Collect photos
                seen = set()
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                
                for img in imgs:
                    if len(result["public_photos"]) >= 20:
                        break
                    
                    src = img.get_attribute("src")
                    if src and ("scontent" in src or "fbcdn" in src):
                        if all(x not in src for x in ["p130x130", "p75x75", "s32x32"]):
                            if src not in seen:
                                seen.add(src)
                                result["public_photos"].append(src)
                
                logger.info(f"Collected {len(result['public_photos'])} photos")
                
            except Exception as e:
                logger.error(f"Error getting photos: {e}")

            # Step 7: Get friend links
            try:
                logger.info("Collecting friend links")
                self.driver.get(profile_url)
                time.sleep(1.5)
                
                self.driver.execute_script("window.scrollTo(0, 1000);")
                time.sleep(1)
                
                links = self.driver.find_elements(By.TAG_NAME, "a")
                friends_set = set()
                
                for link in links[:100]:
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
        "👋 <b>Facebook Profile Scraper Bot</b>\n\n"
        "Send me a Facebook profile URL and I will fetch:\n"
        "• 🆔 User ID\n"
        "• 📸 Profile photo (HD via Graph API)\n"
        "• 🖼️ Cover photo\n"
        "• 📷 Public photos (up to 20)\n"
        "• 👥 Friends mentions/tags (up to 30 links)\n\n"
        "<b>Example:</b>\n"
        "<code>https://facebook.com/username</code>\n"
        "<code>https://facebook.com/profile.php?id=123456</code>\n\n"
        "⚠️ <b>Note:</b> Profile photos are fetched via Facebook's Graph API, "
        "which works even for private profiles!",
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
        "🔍 <b>Fetching data via Graph API...</b>\n\n"
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
                "• Invalid URL format\n"
                "• Network timeout\n"
                "• Facebook blocking",
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
            info_text = "\n".join(user_info_parts)
            if data.get("is_silhouette"):
                info_text += "\n\n⚠️ <i>Profile photo is private or not set (showing silhouette)</i>"
            
            await update.message.reply_text(info_text, parse_mode='HTML')
            logger.info(f"Sent user info: ID={data.get('user_id')}, Username={data.get('username')}")
        
        # Profile photo
        if data.get("profile_photo"):
            try:
                caption = "📸 <b>Profile Photo (HD - Graph API)</b>"
                if data.get("is_silhouette"):
                    caption += "\n<i>⚠️ This is a default silhouette (profile is private)</i>"
                
                logger.info(f"Attempting to send profile photo: {data['profile_photo']}")
                await update.message.reply_photo(
                    data["profile_photo"],
                    caption=caption,
                    parse_mode='HTML'
                )
                logger.info("✓✓✓ Successfully sent profile photo via Graph API")
            except Exception as e:
                logger.error(f"❌❌❌ Failed to send profile photo: {e}")
                # Try sending as URL instead
                await update.message.reply_text(
                    f"📸 <b>Profile Photo URL:</b>\n<code>{data['profile_photo']}</code>\n\n"
                    f"<a href='{data['profile_photo']}'>Click to view</a>",
                    parse_mode='HTML',
                    disable_web_page_preview=False
                )
        else:
            logger.warning("⚠️ No profile photo in data")
            await update.message.reply_text("📸 No profile photo found (may be private or not set)")

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
                await update.message.reply_text("❌ Some photos could not be sent.")
        else:
            await update.message.reply_text("📷 No public photos found")

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
            "✅ <b>Scraping complete!</b>\n\n"
            f"• User ID: {data.get('user_id') or '✗'}\n"
            f"• Username: {data.get('username') or '✗'}\n"
            f"• Profile photo: {'✓ (Graph API)' if data['profile_photo'] else '✗'}\n"
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

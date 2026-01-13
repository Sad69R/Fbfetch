import time
import random
import os
import logging
import requests
import re
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
from selenium.common.exceptions import TimeoutException

# =========================
# Configuration


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
        """Setup Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        chrome_options.binary_location = "/usr/bin/chromium"
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.set_page_load_timeout(20)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        logger.info("Chrome driver initialized")
        return self.driver

    def close_popups(self):
        """Close popups"""
        try:
            selectors = [
                "[aria-label='Close']",
                "[aria-label='close']",
                "div[role='button'][aria-label='Close']",
            ]
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if elems:
                        elems[0].click()
                        time.sleep(0.5)
                        return
                except:
                    pass
        except:
            pass

    def extract_user_id(self, profile_url):
        """Extract user ID from URL"""
        user_id = None
        username = None
        
        try:
            if "profile.php?id=" in profile_url:
                user_id = profile_url.split("profile.php?id=")[1].split("&")[0]
            elif "/people/" in profile_url:
                parts = profile_url.split("/people/")[1].split("/")
                username = parts[0]
                if len(parts) > 1:
                    user_id = parts[1]
            else:
                username = profile_url.rstrip("/").split("/")[-1].split("?")[0]
                if username not in ["www.facebook.com", "facebook.com", "m.facebook.com"]:
                    pass
                else:
                    username = None
        except:
            pass
        
        logger.info(f"Extracted - ID: {user_id}, Username: {username}")
        return user_id, username

    def get_profile_photo_comprehensive(self, user_id, profile_url):
        """Comprehensive profile photo extraction - tries ALL methods"""
        
        # Method 1: Graph API
        if user_id:
            try:
                logger.info("Method 1: Trying Graph API...")
                direct_url = f"https://graph.facebook.com/{user_id}/picture?type=large&width=720&height=720"
                response = requests.head(direct_url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    final_url = response.url
                    # Check if not silhouette
                    if "static" not in final_url and len(final_url) > 100:
                        logger.info(f"✓ Graph API success: {final_url[:80]}...")
                        return final_url
            except Exception as e:
                logger.debug(f"Graph API failed: {e}")
        
        # Method 2-8: Web scraping methods
        try:
            logger.info("Method 2-8: Trying web scraping...")
            self.setup_driver()
            
            # Load page
            try:
                self.driver.get(profile_url)
                time.sleep(3)
                self.close_popups()
            except:
                pass
            
            # Method 2: SVG images (most common for profile photos)
            try:
                logger.info("Method 2: SVG images...")
                svg_imgs = self.driver.find_elements(By.CSS_SELECTOR, "svg image")
                for img in svg_imgs:
                    href = img.get_attribute("xlink:href") or img.get_attribute("href")
                    if href and "scontent" in href:
                        logger.info(f"✓ SVG method: {href[:80]}...")
                        return href
            except Exception as e:
                logger.debug(f"SVG method failed: {e}")
            
            # Method 3: Profile picture link
            try:
                logger.info("Method 3: Profile picture link...")
                links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='photo'], a[href*='picture']")
                for link in links[:5]:
                    imgs = link.find_elements(By.TAG_NAME, "img")
                    for img in imgs:
                        src = img.get_attribute("src")
                        if src and "scontent" in src and "p130x130" not in src:
                            logger.info(f"✓ Link method: {src[:80]}...")
                            return src
            except Exception as e:
                logger.debug(f"Link method failed: {e}")
            
            # Method 4: All images on page
            try:
                logger.info("Method 4: Scanning all images...")
                all_imgs = self.driver.find_elements(By.TAG_NAME, "img")
                best_img = None
                best_size = 0
                
                for img in all_imgs[:30]:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        # Get image size
                        try:
                            width = int(img.get_attribute("width") or 0)
                            height = int(img.get_attribute("height") or 0)
                            size = width * height
                            
                            # Look for square-ish images (profile photos are usually square)
                            if 0.8 <= (width/height if height > 0 else 0) <= 1.2:
                                if size > best_size and "p130x130" not in src:
                                    best_img = src
                                    best_size = size
                        except:
                            if not best_img and "p130x130" not in src:
                                best_img = src
                
                if best_img:
                    logger.info(f"✓ Image scan method: {best_img[:80]}...")
                    return best_img
            except Exception as e:
                logger.debug(f"Image scan failed: {e}")
            
            # Method 5: Page source regex
            try:
                logger.info("Method 5: Page source regex...")
                page_source = self.driver.page_source
                pattern = r'https://scontent[^"\'>\s]+\.(?:jpg|jpeg|png)'
                matches = re.findall(pattern, page_source)
                
                for url in matches:
                    if "_n." in url or "_s." in url or "_b." in url:
                        if "p130x130" not in url and "p75x75" not in url:
                            logger.info(f"✓ Regex method: {url[:80]}...")
                            return url
            except Exception as e:
                logger.debug(f"Regex method failed: {e}")
            
            # Method 6: Meta tag
            try:
                logger.info("Method 6: Meta og:image...")
                meta = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                content = meta.get_attribute("content")
                if content:
                    logger.info(f"✓ Meta tag method: {content[:80]}...")
                    return content
            except Exception as e:
                logger.debug(f"Meta tag failed: {e}")
            
            # Method 7: Mobile view
            try:
                logger.info("Method 7: Trying mobile view...")
                mobile_url = profile_url.replace("www.facebook.com", "m.facebook.com").replace("facebook.com", "m.facebook.com")
                self.driver.get(mobile_url)
                time.sleep(2)
                
                imgs = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='scontent']")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "p130x130" not in src and "p75x75" not in src:
                        logger.info(f"✓ Mobile method: {src[:80]}...")
                        return src
            except Exception as e:
                logger.debug(f"Mobile method failed: {e}")
            
            # Method 8: mbasic.facebook.com (most basic version)
            try:
                logger.info("Method 8: Trying mbasic view...")
                mbasic_url = profile_url.replace("www.facebook.com", "mbasic.facebook.com").replace("m.facebook.com", "mbasic.facebook.com").replace("facebook.com", "mbasic.facebook.com")
                self.driver.get(mbasic_url)
                time.sleep(2)
                
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs[:10]:
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        logger.info(f"✓ mbasic method: {src[:80]}...")
                        return src
            except Exception as e:
                logger.debug(f"mbasic method failed: {e}")
        
        except Exception as e:
            logger.error(f"Web scraping error: {e}")
        
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
        
        logger.warning("❌ All profile photo methods failed")
        return None

    def get_cover_photo_comprehensive(self, profile_url):
        """Comprehensive cover photo extraction"""
        try:
            if not self.driver:
                self.setup_driver()
                self.driver.get(profile_url)
                time.sleep(2)
                self.close_popups()
            
            # Method 1: Cover photo specific selectors
            selectors = [
                "img[data-imgperflogname='profileCoverPhoto']",
                "div[data-pagelet='ProfileCover'] img",
                "a[href*='cover_photo'] img",
                "img[class*='cover']",
            ]
            
            for sel in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, sel)
                    src = elem.get_attribute("src")
                    if src and "scontent" in src:
                        logger.info(f"✓ Cover photo found: {src[:80]}...")
                        return src
                except:
                    continue
            
            # Method 2: Large images (cover photos are wide)
            try:
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    try:
                        width = int(img.get_attribute("width") or 0)
                        height = int(img.get_attribute("height") or 0)
                        
                        # Cover photos are typically wide (width > 2 * height)
                        if width > 400 and width > height * 1.5:
                            src = img.get_attribute("src")
                            if src and "scontent" in src:
                                logger.info(f"✓ Cover photo by size: {src[:80]}...")
                                return src
                    except:
                        continue
            except:
                pass
            
            logger.warning("❌ Cover photo not found")
            return None
            
        except Exception as e:
            logger.error(f"Cover photo error: {e}")
            return None

    def scrape_profile(self, profile_url):
        """Main scraping function"""
        result = {
            "user_id": None,
            "username": None,
            "profile_photo": None,
            "cover_photo": None,
            "public_photos": [],
            "friends_links": [],
            "error": None
        }
        
        try:
            # Extract user ID from URL
            user_id, username = self.extract_user_id(profile_url)
            result["user_id"] = user_id
            result["username"] = username
            
            # Get profile photo (tries 8 different methods)
            logger.info("=" * 50)
            logger.info("STARTING PROFILE PHOTO EXTRACTION")
            logger.info("=" * 50)
            result["profile_photo"] = self.get_profile_photo_comprehensive(user_id, profile_url)
            
            # Get cover photo
            logger.info("=" * 50)
            logger.info("STARTING COVER PHOTO EXTRACTION")
            logger.info("=" * 50)
            result["cover_photo"] = self.get_cover_photo_comprehensive(profile_url)
            
            # Get public photos
            try:
                logger.info("Getting public photos...")
                if not self.driver:
                    self.setup_driver()
                
                photos_url = profile_url.rstrip("/").split("?")[0] + "/photos"
                self.driver.get(photos_url)
                time.sleep(2)
                self.close_popups()
                
                self.driver.execute_script("window.scrollTo(0, 800);")
                time.sleep(1)
                
                seen = set()
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                
                for img in imgs:
                    if len(result["public_photos"]) >= 20:
                        break
                    src = img.get_attribute("src")
                    if src and "scontent" in src:
                        if all(x not in src for x in ["p130x130", "p75x75", "s32x32"]):
                            if src not in seen:
                                seen.add(src)
                                result["public_photos"].append(src)
                
                logger.info(f"Found {len(result['public_photos'])} public photos")
            except Exception as e:
                logger.error(f"Public photos error: {e}")
            
            # Get friend links
            try:
                logger.info("Getting friend links...")
                self.driver.get(profile_url)
                time.sleep(1)
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
                
                result["friends_links"] = list(friends_set)
                logger.info(f"Found {len(result['friends_links'])} friend links")
            except Exception as e:
                logger.error(f"Friend links error: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Scraping error: {e}", exc_info=True)
            return {"error": str(e)}
        
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("Driver closed")
                except:
                    pass


# =========================
# Telegram handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Facebook Profile Scraper Bot</b>\n\n"
        "Send me a Facebook profile URL and I will fetch:\n"
        "• 🆔 User ID\n"
        "• 📸 Profile photo (8 extraction methods!)\n"
        "• 🖼️ Cover photo\n"
        "• 📷 Public photos (up to 20)\n"
        "• 👥 Friends links (up to 30)\n\n"
        "<b>Example:</b>\n"
        "<code>https://facebook.com/username</code>\n"
        "<code>https://facebook.com/profile.php?id=123456</code>",
        parse_mode='HTML'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    url = (update.message.text or "").strip()
    
    if not url.startswith(("https://facebook.com/", "https://www.facebook.com/", "https://m.facebook.com/")):
        await update.message.reply_text(
            "❌ <b>Invalid URL</b>\n\n"
            "Please send a valid Facebook profile URL.",
            parse_mode='HTML'
        )
        return
    
    logger.info(f"User {user_id} (@{username}) requested: {url}")
    
    status_msg = await update.message.reply_text(
        "🔍 <b>Fetching data...</b>\n\n"
        "Trying 8 different methods to extract profile photo.\n"
        "This may take 20-40 seconds...",
        parse_mode='HTML'
    )
    
    try:
        scraper = FacebookScraper()
        data = scraper.scrape_profile(url)
        
        if data.get("error"):
            await status_msg.edit_text(
                f"❌ <b>Error</b>\n\n<code>{data['error']}</code>",
                parse_mode='HTML'
            )
            return
        
        await status_msg.delete()
        
        # User info
        info_parts = []
        if data.get("user_id"):
            info_parts.append(f"🆔 <b>User ID:</b> <code>{data['user_id']}</code>")
        if data.get("username"):
            info_parts.append(f"👤 <b>Username:</b> <code>{data['username']}</code>")
        
        if info_parts:
            await update.message.reply_text("\n".join(info_parts), parse_mode='HTML')
        
        # Profile photo
        if data.get("profile_photo"):
            try:
                await update.message.reply_photo(
                    data["profile_photo"],
                    caption="📸 <b>Profile Photo</b>",
                    parse_mode='HTML'
                )
                logger.info("✓ Sent profile photo")
            except Exception as e:
                logger.error(f"Send failed: {e}")
                await update.message.reply_text(
                    f"📸 <b>Profile Photo URL:</b>\n<a href='{data['profile_photo']}'>Click to view</a>",
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text("📸 Profile photo not found")
        
        # Cover photo
        if data.get("cover_photo"):
            try:
                await update.message.reply_photo(
                    data["cover_photo"],
                    caption="🖼️ <b>Cover Photo</b>",
                    parse_mode='HTML'
                )
                logger.info("✓ Sent cover photo")
            except:
                pass
        else:
            await update.message.reply_text("🖼️ Cover photo not found")
        
        # Public photos
        photos = data.get("public_photos", [])
        if photos:
            await update.message.reply_text(
                f"📷 <b>Found {len(photos)} public photos</b>",
                parse_mode='HTML'
            )
            
            try:
                groups = [photos[i:i+10] for i in range(0, len(photos), 10)]
                for group in groups:
                    media = [InputMediaPhoto(url) for url in group]
                    await update.message.reply_media_group(media)
                    time.sleep(0.5)
            except:
                pass
        else:
            await update.message.reply_text("📷 No public photos found")
        
        # Friend links
        friends = data.get("friends_links", [])
        if friends:
            text = f"👥 <b>Found {len(friends)} friend links</b>\n\n"
            text += "\n".join([f"• {link}" for link in friends])
            
            if len(text) > 4000:
                chunks = [friends[i:i+15] for i in range(0, len(friends), 15)]
                for idx, chunk in enumerate(chunks):
                    chunk_text = "\n".join([f"• {link}" for link in chunk])
                    await update.message.reply_text(
                        f"👥 <b>Links ({idx+1}/{len(chunks)})</b>\n\n{chunk_text}",
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(text, parse_mode='HTML')
        else:
            await update.message.reply_text("👥 No friend links found")
        
        # Summary
        await update.message.reply_text(
            "✅ <b>Complete!</b>\n\n"
            f"• User ID: {data.get('user_id') or '✗'}\n"
            f"• Username: {data.get('username') or '✗'}\n"
            f"• Profile photo: {'✓' if data.get('profile_photo') else '✗'}\n"
            f"• Cover photo: {'✓' if data.get('cover_photo') else '✗'}\n"
            f"• Public photos: {len(photos)}\n"
            f"• Friend links: {len(friends)}",
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ <b>Error</b>\n\n<code>{str(e)}</code>",
            parse_mode='HTML'
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in .env file")
        return
    
    logger.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    print("✅ Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

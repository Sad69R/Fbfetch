import os
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from io import BytesIO

# Configuration
TELEGRAM_BOT_TOKEN = "8252295424:AAGRllLya9BowzOdoKQvEt42MMTwUSAkn2M"

class FacebookScraper:
    def __init__(self):
        self.driver = None
    
    def setup_driver(self):
        """Setup headless Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
    
    def extract_profile_id(self, url):
        """Extract profile ID or username from URL"""
        url = url.strip()
        if "profile.php?id=" in url:
            return url.split("id=")[1].split("&")[0]
        elif "facebook.com/" in url:
            parts = url.split("facebook.com/")[1].split("/")[0].split("?")[0]
            return parts
        return None
    
    def scrape_photos(self, profile_url):
        """Scrape profile photo, cover photo, and public photos"""
        try:
            self.setup_driver()
            self.driver.get(profile_url)
            time.sleep(5)  # Wait for page load
            
            photos = {
                'profile_photo': None,
                'cover_photo': None,
                'public_photos': []
            }
            
            # Try to get profile photo
            try:
                profile_pic = self.driver.find_element(By.CSS_SELECTOR, "image[width='168']")
                if profile_pic:
                    photos['profile_photo'] = profile_pic.get_attribute("xlink:href")
            except:
                try:
                    profile_pic = self.driver.find_element(By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']")
                    photos['profile_photo'] = profile_pic.get_attribute("src")
                except:
                    pass
            
            # Try to get cover photo
            try:
                cover = self.driver.find_element(By.CSS_SELECTOR, "img[data-imgperflogname='profileCoverPhoto']")
                if cover:
                    photos['cover_photo'] = cover.get_attribute("src")
            except:
                pass
            
            # Navigate to photos
            try:
                photos_url = profile_url.rstrip('/') + "/photos"
                self.driver.get(photos_url)
                time.sleep(3)
                
                # Scroll to load more photos
                for _ in range(3):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                
                # Get photo elements
                img_elements = self.driver.find_elements(By.TAG_NAME, "img")
                for img in img_elements[:10]:  # Limit to 10 photos
                    src = img.get_attribute("src")
                    if src and "scontent" in src and src not in photos['public_photos']:
                        photos['public_photos'].append(src)
                        
            except Exception as e:
                print(f"Error getting public photos: {e}")
            
            return photos
            
        except Exception as e:
            print(f"Error scraping: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "👋 Send me a Facebook profile URL and I'll try to fetch:\n"
        "• Profile photo\n"
        "• Cover photo\n"
        "• Public photos\n\n"
        "Example: https://facebook.com/username"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Facebook URLs"""
    message = update.message.text
    
    if "facebook.com" not in message:
        await update.message.reply_text("❌ Please send a valid Facebook profile URL")
        return
    
    await update.message.reply_text("🔍 Fetching photos... This may take 10-20 seconds.")
    
    try:
        scraper = FacebookScraper()
        photos = scraper.scrape_photos(message)
        
        if not photos:
            await update.message.reply_text("❌ Failed to fetch photos. The profile might be private or URL is invalid.")
            return
        
        # Send profile photo
        if photos['profile_photo']:
            try:
                await update.message.reply_photo(photos['profile_photo'], caption="📸 Profile Photo")
            except:
                await update.message.reply_text(f"Profile Photo URL: {photos['profile_photo']}")
        
        # Send cover photo
        if photos['cover_photo']:
            try:
                await update.message.reply_photo(photos['cover_photo'], caption="🖼️ Cover Photo")
            except:
                await update.message.reply_text(f"Cover Photo URL: {photos['cover_photo']}")
        
        # Send public photos
        if photos['public_photos']:
            await update.message.reply_text(f"📷 Found {len(photos['public_photos'])} public photos:")
            for idx, photo_url in enumerate(photos['public_photos'][:5], 1):
                try:
                    await update.message.reply_photo(photo_url, caption=f"Photo {idx}")
                    time.sleep(1)  # Avoid rate limits
                except:
                    await update.message.reply_text(f"Photo {idx} URL: {photo_url}")
        
        if not any([photos['profile_photo'], photos['cover_photo'], photos['public_photos']]):
            await update.message.reply_text("❌ No photos found. Profile might be private or require login.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def main():
    """Start the bot"""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

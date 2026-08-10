import os
import asyncio
import re
import base64
import json
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

TARGET_URL = "https://outlook.live.com/mail/0/inbox"
VIEWPORT = {"width": 330, "height": 550}

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

async def clean_outlook_interface(page):
    """CSS injection matching PyQt clean_outlook_interface method[cite: 3]"""
    try:
        custom_css = """
            #o365header, #HeaderPane, header, [role='region'][aria-label*='Header'] { display: none !important; }
            #LeftRail, [data-app-section='LeftRail'], div[role='navigation'] { display: none !important; }
            #ribbonRoot, [role='menubar'], [aria-label*='Ribbon'], [data-app-section='CommandBar'] { display: none !important; }
            #adUnit, [aria-label*='Advertisement'] { display: none !important; }
            body, #root, #mainFolderList, div[role='main'] {
                height: 100vh !important;
                max-height: 100vh !important;
                width: 100vw !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: auto !important;
            }
        """
        await page.add_style_tag(content=custom_css)
    except Exception:
        pass

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    async def event_generator():
        if not email or not password:
            yield json.dumps({"type": "error", "error": "ইমেইল এবং পাসওয়ার্ড প্রদান করা আবশ্যক।"}) + "\n"
            return

        async with async_playwright() as p:
            yield json.dumps({"type": "status", "msg": "Starting Browser..."}) + "\n"
            
            browser_args = [
                "--disable-blink-features=AutomationControlled", 
                "--no-sandbox",
                "--disable-infobars"
            ]
            browser = await p.chromium.launch(headless=True, args=browser_args)

            context = await browser.new_context(
                viewport=VIEWPORT,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            try:
                # ------------------- LOGIN FLOW (Matching PyQt) -------------------[cite: 3]
                yield json.dumps({"type": "status", "msg": "Opening login page..."}) + "\n"
                await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

                yield json.dumps({"type": "status", "msg": "Submitting Email..."}) + "\n"
                email_selectors = "input[name='loginfmt'], input[type='email'], #i0116"
                await page.wait_for_selector(email_selectors, timeout=15000)
                await page.fill(email_selectors, email)
                
                submit_btn = "input[type='submit'], #idSIButton9, button[type='submit']"
                await page.click(submit_btn)
                await asyncio.sleep(1.5)

                yield json.dumps({"type": "status", "msg": "Checking Password Screen..."}) + "\n"
                password_input_selector = "input[name='passwd'], input[type='password'], #i0118"
                pwd_field = page.locator(password_input_selector).first
                
                for _ in range(8):
                    if await pwd_field.is_visible():
                        break
                    try:
                        pwd_link = page.get_by_text("Use your password", exact=False).first
                        if await pwd_link.is_visible():
                            await pwd_link.click()
                            await asyncio.sleep(1)
                            break
                        
                        fallback = page.locator("#idA_PWD, [id*='PWD'], a:has-text('password')").first
                        if await fallback.is_visible():
                            await fallback.click()
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.4)

                yield json.dumps({"type": "status", "msg": "Submitting Password..."}) + "\n"
                await page.wait_for_selector(password_input_selector, timeout=10000)
                await page.fill(password_input_selector, password)
                await page.click(submit_btn)
                
                yield json.dumps({"type": "status", "msg": "Verifying Credentials..."}) + "\n"
                await asyncio.sleep(2.5)

                body_text = (await page.locator("body").first.inner_text()).lower()
                
                if "password sign-in isn't available" in body_text or "isn't available. try another method" in body_text:
                    await browser.close()
                    yield json.dumps({"type": "error", "error": "⚠️ Error: Password sign-in isn't available. Please use VPN!"}) + "\n"
                    return

                if "password is incorrect" in body_text or "your account or password is incorrect" in body_text or "incorrect for your microsoft account" in body_text:
                    await browser.close()
                    yield json.dumps({"type": "error", "error": "❌ Error: Password is Incorrect!"}) + "\n"
                    return

                if "account has been locked" in body_text or "help us protect your account" in body_text or "verify your identity" in body_text or "unusual activity" in body_text:
                    await browser.close()
                    yield json.dumps({"type": "error", "error": "⚠️ Error: Account Locked or Verification Needed!"}) + "\n"
                    return

                # Redirecting to Inbox[cite: 3]
                yield json.dumps({"type": "status", "msg": "Redirecting to Inbox..."}) + "\n"
                try:
                    await page.goto(TARGET_URL, wait_until="commit", timeout=20000)
                except Exception:
                    pass

                yield json.dumps({"type": "status", "msg": "Optimizing View..."}) + "\n"
                await clean_outlook_interface(page)
                
                yield json.dumps({"type": "status", "msg": "Inbox Loaded Successfully!"}) + "\n"

                # ------------------- LIVE STREAMING & OTP SCANNING -------------------[cite: 3]
                last_fb_otp, last_fb_link = "None", "No Link"
                last_li_otp, last_li_link = "None", "No Link"
                last_ig_otp, last_ig_link = "None", "No Link"
                otp_counter = 0

                while True:
                    screenshot_base64 = ""
                    try:
                        screenshot_bytes = await page.screenshot(type='jpeg', quality=60)
                        screenshot_base64 = f"data:image/jpeg;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"
                    except Exception:
                        pass

                    otp_counter += 1
                    if otp_counter >= 5:
                        otp_counter = 0
                        try:
                            mail_items = page.locator("[role='option'], [data-convid], div[aria-label*='Notification']")
                            count = await mail_items.count()

                            fb_otp, fb_link = "None", "No Link"
                            li_otp, li_link = "None", "No Link"
                            ig_otp, ig_link = "None", "No Link"

                            if count > 0:
                                for i in range(min(count, 5)):
                                    item = mail_items.nth(i)
                                    if await item.is_visible():
                                        item_text = await item.inner_text()
                                        item_html = await item.inner_html()
                                        lower_text = item_text.lower()
                                        
                                        # FACEBOOK SCAN[cite: 3]
                                        if fb_otp == "None" and ("facebook" in lower_text or "fb" in lower_text):
                                            fb_matches = re.findall(r'\b\d{4,8}\b', item_text)
                                            if fb_matches:
                                                fb_otp = fb_matches[0]
                                            
                                            links = re.findall(r'https?://[^\s>"]+', item_html + " " + item_text)
                                            fb_urls = [u for u in links if 'facebook.com' in u or 'fb.me' in u or 'fb' in u]
                                            if fb_urls:
                                                fb_link = fb_urls[0]
                                            else:
                                                link_elem = item.locator("a[href]")
                                                if await link_elem.count() > 0:
                                                    fb_link = await link_elem.first.get_attribute("href") or "No Link"

                                        # LINKEDIN SCAN[cite: 3]
                                        if li_otp == "None" and ("linkedin" in lower_text or "pin" in lower_text):
                                            li_matches = re.findall(r'\b\d{6}\b', item_text)
                                            if li_matches:
                                                li_otp = li_matches[0]

                                            links = re.findall(r'https?://[^\s>"]+', item_html + " " + item_text)
                                            li_urls = [u for u in links if 'linkedin.com' in u or 'lnkd.in' in u]
                                            if li_urls:
                                                li_link = li_urls[0]
                                            else:
                                                link_elem = item.locator("a[href]")
                                                if await link_elem.count() > 0:
                                                    li_link = await link_elem.first.get_attribute("href") or "No Link"

                                        # INSTAGRAM SCAN
                                        if ig_otp == "None" and ("instagram" in lower_text or "ig" in lower_text):
                                            ig_matches = re.findall(r'\b\d{6}\b', item_text)
                                            if ig_matches:
                                                ig_otp = ig_matches[0]

                                            links = re.findall(r'https?://[^\s>"]+', item_html + " " + item_text)
                                            ig_urls = [u for u in links if 'instagram.com' in u]
                                            if ig_urls:
                                                ig_link = ig_urls[0]

                            last_fb_otp, last_fb_link = fb_otp, fb_link
                            last_li_otp, last_li_link = li_otp, li_link
                            last_ig_otp, last_ig_link = ig_otp, ig_link

                        except Exception:
                            pass

                    # 🟢 FIXED DATA STRUCTURE FOR FRONTEND (Includes instagram)
                    yield json.dumps({
                        "type": "result",
                        "success": True,
                        "otps": {
                            "facebook": {"code": last_fb_otp, "link": last_fb_link},
                            "linkedin": {"code": last_li_otp, "link": last_li_link},
                            "instagram": {"code": last_ig_otp, "link": last_ig_link}
                        },
                        "screenshot": screenshot_base64
                    }) + "\n"

                    await asyncio.sleep(0.4)

            except Exception as e:
                try:
                    await browser.close()
                except Exception:
                    pass
                
                err = str(e).lower()
                if "timeout" in err:
                    yield json.dumps({"type": "error", "error": "❌ Error: Network Timeout / Slow Internet!"}) + "\n"
                else:
                    yield json.dumps({"type": "error", "error": f"❌ Error: Login Failed! ({str(e)})"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

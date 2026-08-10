import os
import asyncio
import re
import base64
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

def extract_otp_and_link(text, html_content=""):
    otp = None
    link = None
    
    # 4 to 8 digit OTP/Code extraction
    otp_match = re.search(r'\b\d{4,8}\b', text)
    if otp_match:
        otp = otp_match.group(0)

    # Magic link / Verification URL extraction
    if html_content:
        links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_content)
        valid_links = [l for l in links if "linkedin.com" in l or "facebook.com" in l or "instagram.com" in l or "confirm" in l or "verify" in l or "action" in l or "code" in l]
        if valid_links:
            link = valid_links[0]
            
    if not link:
        link_match = re.search(r'https?://[^\s<>"]+', text)
        if link_match:
            link = link_match.group(0)

    return otp, link

async def inject_clean_css(page):
    """Outlook Interface clean CSS injection"""
    try:
        custom_css = """
            #o365header, #HeaderPane, header, [role='region'][aria-label*='Header'] { display: none !important; }
            #LeftRail, [data-app-section='LeftRail'], div[role='navigation'] { display: none !important; }
            #ribbonRoot, [role='menubar'], [aria-label*='Ribbon'], [data-app-section='CommandBar'] { display: none !important; }
            #adUnit, [aria-label*='Advertisement'] { display: none !important; }
        """
        await page.add_style_tag(content=custom_css)
    except Exception:
        pass

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    print(f"--> [1] Request received for Email: {email}")
    
    if not email or not password:
        return JSONResponse(
            status_code=400, 
            content={"success": False, "error": "ইমেইল এবং পাসওয়ার্ড প্রদান করা আবশ্যক।"}
        )

    async with async_playwright() as p:
        print("--> [2] Launching Playwright Chromium...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()

        # Webdriver evasion
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        # Block heavy media assets
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

        try:
            print("--> [3] Navigating to login.live.com...")
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

            # Step 1: Submit Email
            print("--> [4] Entering Email...")
            email_selectors = "input[name='loginfmt'], input[type='email'], #i0116"
            await page.wait_for_selector(email_selectors, timeout=15000)
            await page.fill(email_selectors, email)
            
            submit_btn = "input[type='submit'], #idSIButton9, button[type='submit']"
            await page.click(submit_btn)
            await asyncio.sleep(1.5)

            # Step 2: Handle "Use Password" option if prompt appears
            password_input_selector = "input[name='passwd'], input[type='password'], #i0118"
            pwd_field = page.locator(password_input_selector).first
            
            for _ in range(5):
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

            # Step 3: Submit Password
            print("--> [5] Entering Password...")
            await page.wait_for_selector(password_input_selector, timeout=10000)
            await page.fill(password_input_selector, password)
            await page.click(submit_btn)
            
            print("--> [6] Verifying Credentials & Checking Errors...")
            await asyncio.sleep(2.5)

            # Body Error Check Logic
            body_text = (await page.locator("body").inner_text()).lower()
            
            if "password sign-in isn't available" in body_text or "isn't available. try another method" in body_text:
                await browser.close()
                return JSONResponse(status_code=400, content={"success": False, "error": "⚠️ Error: Password sign-in isn't available. Please use VPN!"})

            if "password is incorrect" in body_text or "your account or password is incorrect" in body_text or "incorrect for your microsoft account" in body_text:
                await browser.close()
                return JSONResponse(status_code=400, content={"success": False, "error": "❌ Error: Password is Incorrect!"})

            if "account has been locked" in body_text or "help us protect your account" in body_text or "verify your identity" in body_text or "unusual activity" in body_text:
                await browser.close()
                return JSONResponse(status_code=400, content={"success": False, "error": "⚠️ Error: Account Locked or Verification Needed!"})

            # Handle Skip Prompts (Stay Signed In, etc.)
            skip_selectors = ['#iCancel', 'a:has-text("Cancel")', 'a:has-text("Skip")', '#acceptButton', '#idSIButton9', 'button:has-text("Yes")', 'button:has-text("No")']
            for selector in skip_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(1.5)
                except Exception:
                    pass

            # Step 4: Redirect to Inbox & Capture Live Screen
            print("--> [7] Redirecting to Inbox...")
            try:
                await page.goto("https://outlook.live.com/mail/0/inbox", wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass

            await inject_clean_css(page)

            # **ইনবক্সে আসার সাথে সাথে স্ক্রিনশট ক্যাপচার**
            screenshot_base64 = ""
            try:
                await asyncio.sleep(1)
                img_bytes = await page.screenshot(type='jpeg', quality=60)
                screenshot_base64 = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('utf-8')}"
            except Exception:
                pass

            # Wait for any mail list container to appear
            try:
                await page.wait_for_selector('div[role="listitem"], div[role="option"], [data-convid]', timeout=15000)
            except Exception:
                print("--> Warning: Explicit mail container selector wait timed out, proceeding to fallback scan...")

            await asyncio.sleep(2)

            email_list = []
            otps = {
                "linkedin": {"code": None, "link": None},
                "facebook": {"code": None, "link": None},
                "instagram": {"code": None, "link": None}
            }

            print("--> [8] Extracting Emails & OTPs...")
            
            selectors = [
                'div[role="listitem"]',
                'div[role="option"]',
                '[data-convid]',
                'div[data-automation-id="ListItem"]',
                'div[aria-label*="Message"]'
            ]
            
            inbox_items = None
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    if cnt > 0:
                        inbox_items = loc
                        print(f"--> Found {cnt} emails using selector: {sel}")
                        break
                except Exception:
                    continue

            if not inbox_items:
                inbox_items = page.locator('div[tabindex="0"][role]')

            if inbox_items:
                count = await inbox_items.count()
                for i in range(min(count, 15)):
                    try:
                        item = inbox_items.nth(i)
                        
                        try:
                            await item.click(timeout=1500)
                            await asyncio.sleep(0.5)
                        except Exception:
                            pass

                        aria_label = await item.get_attribute("aria-label") or ""
                        text = await item.inner_text()
                        
                        if not text.strip():
                            continue

                        body_content = ""
                        html_content = ""
                        try:
                            body_elem = page.locator('div[aria-label="Message body"], div[role="main"], div[data-tabgroup="messageBody"]').first
                            if await body_elem.is_visible():
                                body_content = await body_elem.inner_text()
                                html_content = await body_elem.inner_html()
                        except Exception:
                            pass

                        full_content = (aria_label + "\n" + text + "\n" + body_content).strip()
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        
                        sender = lines[0] if len(lines) > 0 else "Outlook Mail"
                        subject = lines[1] if len(lines) > 1 else (aria_label[:40] if aria_label else "No Subject")
                        preview = body_content if body_content else (" ".join(lines[2:]) if len(lines) > 2 else aria_label)

                        date_match = re.search(r'(\d{1,2}:\d{2}\s?(?:AM|PM)?|\d{1,2}/\d{1,2}/\d{4}|Mon|Tue|Wed|Thu|Fri|Sat|Sun)', aria_label + " " + text, re.IGNORECASE)
                        date_str = date_match.group(0) if date_match else "Recently"

                        email_list.append({
                            "sender": sender,
                            "subject": subject,
                            "preview": preview,
                            "date": date_str
                        })

                        lower_content = full_content.lower()
                        code, link = extract_otp_and_link(full_content, html_content)

                        if ("linkedin" in lower_content or "linkedin" in sender.lower()) and not otps["linkedin"]["code"]:
                            otps["linkedin"]["code"] = code
                            otps["linkedin"]["link"] = link
                        elif ("facebook" in lower_content or "fb" in lower_content or "facebook" in sender.lower()) and not otps["facebook"]["code"]:
                            otps["facebook"]["code"] = code
                            otps["facebook"]["link"] = link
                        elif ("instagram" in lower_content or "instagram" in sender.lower()) and not otps["instagram"]["code"]:
                            otps["instagram"]["code"] = code
                            otps["instagram"]["link"] = link

                    except Exception:
                        continue

            await browser.close()

            if email_list:
                print("--> [SUCCESS] Completed Successfully!")
                return JSONResponse(content={
                    "success": True, 
                    "otps": otps, 
                    "emails": email_list,
                    "screenshot": screenshot_base64
                })
            else:
                return JSONResponse(content={
                    "success": False, 
                    "error": "ইনবক্সে কোনো ইমেইল পাওয়া যায়নি অথবা ইনবক্স খালি।",
                    "screenshot": screenshot_base64
                }, status_code=400)

        except Exception as e:
            error_msg = str(e)
            print(f"--> [ERROR]: {error_msg}")
            await browser.close()
            if "timeout" in error_msg.lower():
                return JSONResponse(content={"success": False, "error": "❌ Error: Network Timeout / Slow Internet!"}, status_code=500)
            return JSONResponse(content={"success": False, "error": f"প্রসেস করার সময় ত্রুটি ঘটেছে: {error_msg}"}, status_code=500)

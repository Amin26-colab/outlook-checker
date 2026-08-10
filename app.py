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

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

def extract_otp_and_link(text, html_content=""):
    otp = None
    link = None
    
    otp_match = re.search(r'\b\d{4,8}\b', text)
    if otp_match:
        otp = otp_match.group(0)

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
    try:
        custom_css = """
            #o365header, #HeaderPane, header, [role='region'][aria-label*='Header'] { display: none !important; }
            #LeftRail, [data-app-section='LeftRail'], div[role='navigation'] { display: none !important; }
            #ribbonRoot, [role='menubar'], [aria-label*='Ribbon'], [data-app-section='CommandBar'] { display: none !important; }
            #adUnit, [aria-label*='Advertisement'] { display: none !important; }
            body, #root, #mainFolderList, div[role='main'] {
                height: 100vh !important;
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
            yield json.dumps({"type": "status", "msg": "🚀 Launching Fast Engine..."}) + "\n"
            
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-infobars"
                ]
            )
            
            # Optimization 1: Small viewport (like their VIEWPORT = {"width": 330, "height": 550})
            context = await browser.new_context(
                viewport={"width": 360, "height": 600},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

            try:
                yield json.dumps({"type": "status", "msg": "🌐 Accessing Login Page..."}) + "\n"
                
                # Fast domcontentloaded
                await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=25000)

                # Step 1: Submit Email
                yield json.dumps({"type": "status", "msg": "📧 Submitting Email..."}) + "\n"
                email_selectors = "input[name='loginfmt'], input[type='email'], #i0116"
                await page.wait_for_selector(email_selectors, timeout=10000)
                await page.fill(email_selectors, email)
                
                submit_btn = "input[type='submit'], #idSIButton9, button[type='submit']"
                await page.click(submit_btn)

                # Step 2: Handle Password / Use your password
                password_input_selector = "input[name='passwd'], input[type='password'], #i0118"
                pwd_field = page.locator(password_input_selector).first

                # Fast check loop like their code
                for _ in range(6):
                    if await pwd_field.is_visible():
                        break
                    try:
                        pwd_link = page.get_by_text("Use your password", exact=False).first
                        if await pwd_link.is_visible():
                            await pwd_link.click()
                            break
                        
                        fallback = page.locator("#idA_PWD, [id*='PWD'], a:has-text('password')").first
                        if await fallback.is_visible():
                            await fallback.click()
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)

                yield json.dumps({"type": "status", "msg": "🔑 Submitting Password..."}) + "\n"
                await page.wait_for_selector(password_input_selector, timeout=10000)
                await page.fill(password_input_selector, password)
                await page.click(submit_btn)
                
                yield json.dumps({"type": "status", "msg": "🔍 Validating Account Status..."}) + "\n"
                await asyncio.sleep(1)

                # Direct Selector based validation (Ultra Fast)
                error_selectors = ["#usernameError", "#passwordError", "#error", ".error", "[role='alert']", "#i0118Error"]
                for selector in error_selectors:
                    try:
                        err_elem = page.locator(selector).first
                        if await err_elem.is_visible(timeout=500):
                            err_text = (await err_elem.inner_text()).lower()
                            if "password" in err_text or "incorrect" in err_text:
                                await browser.close()
                                yield json.dumps({"type": "error", "error": "❌ Error: Password is Incorrect!"}) + "\n"
                                return
                            elif "locked" in err_text or "protect" in err_text or "verify" in err_text:
                                await browser.close()
                                yield json.dumps({"type": "error", "error": "⚠️ Error: Account Locked or Verification Required!"}) + "\n"
                                return
                    except Exception:
                        pass

                current_url = page.url
                if "Abuse" in current_url or "proof/remember" in current_url or "recover" in current_url:
                    await browser.close()
                    yield json.dumps({"type": "error", "error": "⚠️ Error: IP Blocked / Account Locked / Verification Required!"}) + "\n"
                    return

                # Skip stay signed in prompts quickly
                skip_selectors = ['#iCancel', '#acceptButton', '#idSIButton9', 'button:has-text("Yes")', 'button:has-text("No")']
                for selector in skip_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=500):
                            await btn.click()
                    except Exception:
                        pass

                # Optimization 2: Use wait_until="commit" (Key secret from their code)
                yield json.dumps({"type": "status", "msg": "🚀 Redirecting to Inbox..."}) + "\n"
                try:
                    await page.goto("https://outlook.live.com/mail/0/inbox", wait_until="commit", timeout=15000)
                except Exception:
                    pass

                await inject_clean_css(page)
                yield json.dumps({"type": "status", "msg": "🟢 Live Sync Active!"}) + "\n"

                # Optimization 3: Fast Live Stream Loop
                while True:
                    screenshot_base64 = ""
                    try:
                        # Quality set to 60 for super-fast compression
                        img_bytes = await page.screenshot(type='jpeg', quality=60)
                        screenshot_base64 = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                    except Exception:
                        pass

                    email_list = []
                    otps = {
                        "linkedin": {"code": None, "link": None},
                        "facebook": {"code": None, "link": None},
                        "instagram": {"code": None, "link": None}
                    }

                    # Mail extraction selector (from their code)
                    mail_items = page.locator("[role='option'], [data-convid], div[aria-label*='Notification'], div[role='listitem']")
                    try:
                        count = await mail_items.count()
                        for i in range(min(count, 10)):
                            item = mail_items.nth(i)
                            if await item.is_visible():
                                text = await item.inner_text()
                                html_content = await item.inner_html()
                                
                                if not text.strip():
                                    continue

                                lines = [line.strip() for line in text.split('\n') if line.strip()]
                                sender = lines[0] if len(lines) > 0 else "Outlook Mail"
                                subject = lines[1] if len(lines) > 1 else "No Subject"
                                preview = " ".join(lines[2:]) if len(lines) > 2 else text

                                email_list.append({
                                    "sender": sender,
                                    "subject": subject,
                                    "preview": preview,
                                    "date": "Recently"
                                })

                                lower_content = text.lower()
                                code, link = extract_otp_and_link(text, html_content)

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
                        pass

                    # Instant result emit
                    yield json.dumps({
                        "type": "result",
                        "success": True, 
                        "otps": otps, 
                        "emails": email_list,
                        "screenshot": screenshot_base64
                    }) + "\n"

                    # 1.5 seconds fast update delay
                    await asyncio.sleep(1.5)

            except Exception as e:
                try:
                    await browser.close()
                except Exception:
                    pass
                yield json.dumps({"type": "error", "error": f"Error: {str(e)}"}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

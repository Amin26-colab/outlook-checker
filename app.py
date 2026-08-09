import os
import re
import asyncio
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

def extract_otp_and_link(text):
    otp = None
    link = None
    
    # 6 to 8 digit OTP extraction
    otp_match = re.search(r'\b\d{6,8}\b', text)
    if otp_match:
        otp = otp_match.group(0)

    # URL extraction
    link_match = re.search(r'https?://[^\s<>"]+', text)
    if link_match:
        link = link_match.group(0)

    return otp, link

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    async with async_playwright() as p:
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        page = await context.new_page()

        # Block heavy media files to keep performance fast
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

        otps = {
            "linkedin": {"code": None, "link": None},
            "facebook": {"code": None, "link": None},
            "instagram": {"code": None, "link": None}
        }
        email_list = []

        try:
            # Step 1: Login Page
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

            # Step 2: Email Entry
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            await email_input.wait_for(state="visible", timeout=12000)
            await email_input.fill(email)
            await page.keyboard.press("Enter")

            # Step 3: Password Entry
            pass_input = page.locator('input[type="password"], input[name="passwd"]').first
            await pass_input.wait_for(state="visible", timeout=12000)
            await pass_input.fill(password)
            await page.keyboard.press("Enter")

            # Step 4: Handle "Stay Signed In" / Prompts
            await asyncio.sleep(3)
            prompt_buttons = ['#idSIButton9', '#acceptButton', '#iCancel', 'button:has-text("Yes")', 'button:has-text("No")']
            for btn_sel in prompt_buttons:
                try:
                    btn = page.locator(btn_sel).first
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass

            # Step 5: Direct Outlook Navigation
            await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded", timeout=40000)
            
            # Wait for Inbox UI rendering
            await asyncio.sleep(6)

            # Multi-Selector Support for Outlook
            selectors = [
                'div[role="option"]',
                'div[data-convid]',
                'div[role="listitem"]',
                'div[aria-label*="Select a conversation"]',
                'div[aria-label*="Email"]'
            ]
            
            inbox_locator = None
            for sel in selectors:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    inbox_locator = loc
                    break

            if inbox_locator:
                count = await inbox_locator.count()

                for i in range(min(count, 15)):
                    try:
                        item = inbox_locator.nth(i)
                        aria = await item.get_attribute("aria-label") or ""
                        text = await item.inner_text()
                        
                        full_content = (aria + "\n" + text).strip()
                        lines = [line.strip() for line in text.split('\n') if line.strip()]

                        sender = lines[0] if lines else "Outlook Sender"
                        subject = lines[1] if len(lines) > 1 else (aria[:40] if aria else "No Subject")
                        preview = " ".join(lines[2:]) if len(lines) > 2 else full_content

                        email_list.append({
                            "sender": sender,
                            "subject": subject,
                            "preview": preview,
                            "full_body": full_content
                        })

                        # OTP & Link Extraction Logic
                        lower_content = full_content.lower()
                        code, link = extract_otp_and_link(full_content)

                        if ("linkedin" in lower_content or "linkedin" in sender.lower()) and not otps["linkedin"]["code"]:
                            otps["linkedin"]["code"] = code
                            otps["linkedin"]["link"] = link
                        elif ("facebook" in lower_content or "facebook" in sender.lower()) and not otps["facebook"]["code"]:
                            otps["facebook"]["code"] = code
                            otps["facebook"]["link"] = link
                        elif ("instagram" in lower_content or "instagram" in sender.lower()) and not otps["instagram"]["code"]:
                            otps["instagram"]["code"] = code
                            otps["instagram"]["link"] = link

                    except Exception:
                        continue

            await browser.close()

            if email_list:
                return JSONResponse(content={"success": True, "otps": otps, "emails": email_list})
            else:
                return JSONResponse(content={"success": False, "error": "ইনবক্সে কোনো ইমেইল পাওয়া যায়নি। অ্যাকাউন্টে ২-স্টেপ ভেরিফিকেশন অথবা আইপি ব্লকিং আছে কিনা পরীক্ষা করুন।"}, status_code=400)

        except Exception as e:
            await browser.close()
            return JSONResponse(content={"success": False, "error": f"Process Failed: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

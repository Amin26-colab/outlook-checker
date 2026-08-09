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
    # Regex to extract 6 or 8 digit codes and links
    otp = None
    link = None
    
    otp_match = re.search(r'\b\d{6,8}\b', text)
    if otp_match:
        otp = otp_match.group(0)

    link_match = re.search(r'https?://[^\s<>"]+', text)
    if link_match:
        link = link_match.group(0)

    return otp, link

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        
        # Performance optimization: Block unnecessary assets
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,svg,css,woff2}", lambda route: route.abort())

        otps = {
            "linkedin": {"code": None, "link": None},
            "facebook": {"code": None, "link": None},
            "instagram": {"code": None, "link": None}
        }
        email_list = []

        try:
            # Login Process
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=20000)

            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            await email_input.fill(email)
            await page.keyboard.press("Enter")

            pass_input = page.locator('input[type="password"], input[name="passwd"]').first
            await pass_input.wait_for(state="visible", timeout=10000)
            await pass_input.fill(password)
            await page.keyboard.press("Enter")

            # Quick Skip Prompts
            await asyncio.sleep(2)
            try:
                btn = page.locator('#idSIButton9, #acceptButton').first
                if await btn.is_visible():
                    await btn.click()
            except Exception:
                pass

            # Direct Inbox Route
            await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded", timeout=30000)
            
            # Smart wait for emails
            inbox_locator = page.locator('div[role="option"]')
            await inbox_locator.first.wait_for(state="attached", timeout=15000)
            
            count = await inbox_locator.count()

            for i in range(min(count, 12)):
                try:
                    item = inbox_locator.nth(i)
                    text = await item.inner_text()
                    aria = await item.get_attribute("aria-label") or ""
                    full_content = aria + "\n" + text

                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    sender = lines[0] if lines else "Unknown"
                    subject = lines[1] if len(lines) > 1 else aria[:40]
                    preview = lines[2] if len(lines) > 2 else full_content

                    email_list.append({
                        "sender": sender,
                        "subject": subject,
                        "preview": preview,
                        "full_body": full_content
                    })

                    # Auto OTP & Link Scraping
                    lower_content = full_content.lower()
                    code, link = extract_otp_and_link(full_content)

                    if "linkedin" in lower_content and not otps["linkedin"]["code"]:
                        otps["linkedin"]["code"] = code
                        otps["linkedin"]["link"] = link
                    elif "facebook" in lower_content and not otps["facebook"]["code"]:
                        otps["facebook"]["code"] = code
                        otps["facebook"]["link"] = link
                    elif "instagram" in lower_content and not otps["instagram"]["code"]:
                        otps["instagram"]["code"] = code
                        otps["instagram"]["link"] = link

                except Exception:
                    continue

            await browser.close()
            return JSONResponse(content={"success": True, "otps": otps, "emails": email_list})

        except Exception as e:
            await browser.close()
            return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

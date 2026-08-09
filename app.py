import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from playwright.async_api import async_playwright

app = FastAPI()

# Jinja2 Templates Path Fix
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    async with async_playwright() as p:
        # Render/Server headless environment flags
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navigation
            await page.goto("https://login.live.com/", wait_until="domcontentloaded")

            # ১. Email Input ও Next
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            await email_input.wait_for(state="visible", timeout=15000)
            await email_input.click()
            await email_input.press_sequentially(email, delay=50)
            await asyncio.sleep(1)

            try:
                await email_input.press("Enter")
            except Exception:
                await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

            # ২. Password Input ও Sign in
            pass_input = page.locator('input[type="password"], input[name="passwd"]').first
            await pass_input.wait_for(state="visible", timeout=15000)
            await pass_input.click()
            await pass_input.press_sequentially(password, delay=50)
            await asyncio.sleep(1)

            try:
                await pass_input.press("Enter")
            except Exception:
                await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

            # ৩. সিকিউরিটি প্রম্পট বাইপাস
            await asyncio.sleep(3)
            skip_selectors = ['#iCancel', 'a:has-text("Cancel")', 'a:has-text("Skip")', '#acceptButton', '#idSIButton9']
            for selector in skip_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass

            # ৪. ইনবক্সে নেভিগেট ও ডাটা স্ক্র্যাপ
            await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded")
            await page.wait_for_selector('div[role="listbox"], div[role="option"]', timeout=20000)
            
            emails = await page.locator('div[role="option"]').all()
            email_list = []
            
            for item in emails[:10]:
                text = await item.inner_text()
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                if lines:
                    email_list.append({
                        "sender": lines[0] if len(lines) > 0 else "Unknown",
                        "subject": lines[1] if len(lines) > 1 else "No Subject",
                        "preview": lines[2] if len(lines) > 2 else ""
                    })

            await browser.close()

            if email_list:
                return JSONResponse(content={"success": True, "emails": email_list})
            else:
                return JSONResponse(content={"success": False, "error": "No emails found in inbox."}, status_code=400)

        except Exception as e:
            await browser.close()
            return JSONResponse(content={"success": False, "error": f"Inbox loading failed: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

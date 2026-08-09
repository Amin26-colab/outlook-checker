import os
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

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    print(f"--> [1] Request received for Email: {email}")
    
    async with async_playwright() as p:
        print("--> [2] Launching Playwright Chromium Browser...")
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        try:
            # step 1
            print("--> [3] Navigating to login.live.com...")
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

            # step 2
            print("--> [4] Entering Email...")
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            await email_input.wait_for(state="visible", timeout=15000)
            await email_input.click()
            await email_input.press_sequentially(email, delay=50)
            await asyncio.sleep(1)

            try:
                await email_input.press("Enter")
            except Exception:
                await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

            # step 3
            print("--> [5] Entering Password...")
            pass_input = page.locator('input[type="password"], input[name="passwd"]').first
            await pass_input.wait_for(state="visible", timeout=15000)
            await pass_input.click()
            await pass_input.press_sequentially(password, delay=50)
            await asyncio.sleep(1)

            try:
                await pass_input.press("Enter")
            except Exception:
                await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

            # step 4
            print("--> [6] Handling Security Prompts...")
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

            # step 5
            print("--> [7] Navigating to Outlook Inbox...")
            await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded", timeout=40000)
            
            print("--> [8] Waiting for Inbox Elements...")
            await page.wait_for_selector('div[role="listbox"], div[role="option"]', timeout=25000)
            
            emails = await page.locator('div[role="option"]').all()
            email_list = []
            
            print("--> [9] Parsing Emails...")
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
                print("--> [SUCCESS] Inbox fetched successfully!")
                return JSONResponse(content={"success": True, "emails": email_list})
            else:
                print("--> [WARNING] No emails found in inbox.")
                return JSONResponse(content={"success": False, "error": "No emails found in inbox."}, status_code=400)

        except Exception as e:
            error_msg = str(e)
            print(f"--> [ERROR] Exception occurred: {error_msg}")
            await browser.close()
            return JSONResponse(content={"success": False, "error": f"Failed at process: {error_msg}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

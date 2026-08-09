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
            # Step 1: Login Page
            print("--> [3] Navigating to login.live.com...")
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

            # Step 2: Email Entry
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

            # Step 3: Password Entry
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

            # Step 4: Security Prompts
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

            # Step 5: Direct Inbox Load
            print("--> [7] Navigating to Outlook Inbox...")
            await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded", timeout=40000)
            
            print("--> [8] Waiting for Inbox Render...")
            # wait_for না রেখে ইনবক্স স্ক্রিন পুরোপুরি লোড হওয়ার জন্য কাস্টম ৫ সেকেন্ড পজ দেওয়া হলো
            await asyncio.sleep(6)
            
            email_list = []
            print("--> [9] Parsing Emails...")
            
            inbox_locator = page.locator('div[role="option"]')
            count = await inbox_locator.count()
            print(f"--> Found {count} email elements")

            for i in range(min(count, 10)):
                try:
                    item = inbox_locator.nth(i)
                    
                    # aria-label থেকেও ফলব্যাক ডাটা নেওয়ার ব্যবস্থা করা হলো
                    aria_label = await item.get_attribute("aria-label") or ""
                    text = await item.inner_text()
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    if lines:
                        sender = lines[0]
                        subject = lines[1] if len(lines) > 1 else aria_label[:50]
                        preview = lines[2] if len(lines) > 2 else aria_label
                    else:
                        sender = "Outlook Mail"
                        subject = aria_label[:40] if aria_label else "No Subject"
                        preview = aria_label

                    email_list.append({
                        "sender": sender,
                        "subject": subject,
                        "preview": preview
                    })
                except Exception as inner_e:
                    print(f"--> Error parsing email {i}: {inner_e}")
                    continue

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

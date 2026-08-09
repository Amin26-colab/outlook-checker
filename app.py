import os
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
    emails_data = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto("https://login.live.com/", timeout=60000)

            await page.fill('input[type="email"]', email)
            await page.click('input[type="submit"]')
            await page.wait_for_timeout(2000)

            await page.fill('input[type="password"]', password)
            await page.click('input[type="submit"]')
            await page.wait_for_timeout(3000)

            try:
                if await page.is_visible('#acceptButton'):
                    await page.click('#acceptButton')
            except Exception:
                pass

            await page.goto("https://outlook.live.com/mail/0/inbox", timeout=60000)
            await page.wait_for_selector('div[role="option"]', timeout=30000)

            mail_items = await page.query_selector_all('div[role="option"]')
            
            for item in mail_items[:10]:
                try:
                    sender_el = await item.query_selector('span[title]')
                    subject_el = await item.query_selector('div[aria-label]')
                    
                    sender = await sender_el.inner_text() if sender_el else "Unknown Sender"
                    subject = await subject_el.inner_text() if subject_el else "No Subject"

                    emails_data.append({
                        "sender": sender,
                        "subject": subject,
                        "preview": "Logged in & fetched successfully"
                    })
                except Exception:
                    continue

            await browser.close()
            return JSONResponse(content={"success": True, "emails": emails_data})

        except Exception as e:
            await browser.close()
            return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

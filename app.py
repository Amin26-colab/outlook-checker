import os
import asyncio
import re
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
    
    # Extract 5 to 8 digit OTP/Code
    otp_match = re.search(r'\b\d{5,8}\b', text)
    if otp_match:
        otp = otp_match.group(0)

    # Search links inside HTML hrefs first, then raw text
    if html_content:
        links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_content)
        # Filter out common tracking / unsubscribe links if possible
        valid_links = [l for l in links if "linkedin.com" in l or "facebook.com" in l or "instagram.com" in l or "confirm" in l or "verify" in l or "action" in l]
        if valid_links:
            link = valid_links[0]
            
    if not link:
        link_match = re.search(r'https?://[^\s<>"]+', text)
        if link_match:
            link = link_match.group(0)

    return otp, link

@app.post("/fetch-inbox")
async def fetch_inbox(email: str = Form(""), password: str = Form("")):
    print(f"--> [1] Request received for Email: {email}", flush=True)
    
    async with async_playwright() as p:
        print("--> [2] Launching Playwright Chromium...", flush=True)
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
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()

        # Block fonts and images for maximum speed
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

        try:
            print("--> [3] Navigating to login.live.com...", flush=True)
            await page.goto("https://login.live.com/", wait_until="domcontentloaded", timeout=30000)

            print("--> [4] Entering Email...", flush=True)
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            await email_input.wait_for(state="visible", timeout=15000)
            await email_input.fill(email)
            await page.keyboard.press("Enter")

            print("--> [5] Entering Password...", flush=True)
            pass_input = page.locator('input[type="password"], input[name="passwd"]').first
            await pass_input.wait_for(state="visible", timeout=15000)
            await pass_input.fill(password)
            await page.keyboard.press("Enter")

            print("--> [6] Handling Security Prompts...", flush=True)
            await asyncio.sleep(2)
            skip_selectors = ['#iCancel', 'a:has-text("Cancel")', 'a:has-text("Skip")', '#acceptButton', '#idSIButton9', 'button:has-text("Yes")', 'button:has-text("No")']
            for selector in skip_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

            print("--> [7] Navigating to Outlook Inbox...", flush=True)
            await page.goto("https://outlook.live.com/mail/0/inbox", wait_until="domcontentloaded", timeout=40000)
            
            print("--> [8] Waiting for Inbox Render...", flush=True)
            selectors = [
                'div[data-automation-id="ListItem"]',
                'div[role="option"]',
                'div[role="article"]',
                'div[data-convid]'
            ]
            
            inbox_items = None
            for sel in selectors:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                    inbox_items = page.locator(sel)
                    cnt = await inbox_items.count()
                    if cnt > 0:
                        print(f"--> Found {cnt} elements using selector: {sel}", flush=True)
                        break
                except Exception:
                    continue

            email_list = []
            otps = {
                "linkedin": {"code": None, "link": None},
                "facebook": {"code": None, "link": None},
                "instagram": {"code": None, "link": None}
            }

            if inbox_items:
                count = await inbox_items.count()
                for i in range(min(count, 10)):
                    try:
                        item = inbox_items.nth(i)
                        
                        # Click email to open full reading pane
                        await item.click()
                        await asyncio.sleep(1.5)

                        aria_label = await item.get_attribute("aria-label") or ""
                        text = await item.inner_text()
                        
                        # Extract full email body content from reading pane
                        body_content = ""
                        html_content = ""
                        try:
                            body_elem = page.locator('div[aria-label="Message body"], div[data-tabgroup="messageBody"]').first
                            if await body_elem.is_visible():
                                body_content = await body_elem.inner_text()
                                html_content = await body_elem.inner_html()
                        except Exception:
                            body_content = text

                        full_text_for_parsing = (aria_label + "\n" + text + "\n" + body_content).strip()
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        
                        sender = lines[0] if len(lines) > 0 else "Outlook Sender"
                        subject = lines[1] if len(lines) > 1 else (aria_label[:40] if aria_label else "No Subject")
                        preview = body_content if body_content else (" ".join(lines[2:]) if len(lines) > 2 else "No content available")

                        # Extract Date
                        date_match = re.search(r'(\d{1,2}:\d{2}\s?(?:AM|PM)?|\d{1,2}/\d{1,2}/\d{4}|Mon|Tue|Wed|Thu|Fri|Sat|Sun)', aria_label + " " + text, re.IGNORECASE)
                        date_str = date_match.group(0) if date_match else "Recently"

                        email_list.append({
                            "sender": sender,
                            "subject": subject,
                            "preview": preview,
                            "date": date_str
                        })

                        # Social OTP & Link Extraction Logic
                        lower_content = full_text_for_parsing.lower()
                        code, link = extract_otp_and_link(full_text_for_parsing, html_content)

                        if ("linkedin" in lower_content or "linkedin" in sender.lower()) and not otps["linkedin"]["code"]:
                            otps["linkedin"]["code"] = code
                            otps["linkedin"]["link"] = link
                        elif ("facebook" in lower_content or "facebook" in sender.lower()) and not otps["facebook"]["code"]:
                            otps["facebook"]["code"] = code
                            otps["facebook"]["link"] = link
                        elif ("instagram" in lower_content or "instagram" in sender.lower()) and not otps["instagram"]["code"]:
                            otps["instagram"]["code"] = code
                            otps["instagram"]["link"] = link

                    except Exception as inner_e:
                        print(f"--> Error parsing email {i}: {inner_e}", flush=True)
                        continue

            await browser.close()

            if email_list:
                print("--> [SUCCESS] Inbox fetched, Full Body Parsed & Links Extracted!", flush=True)
                return JSONResponse(content={
                    "success": True, 
                    "otps": otps, 
                    "emails": email_list
                })
            else:
                return JSONResponse(content={"success": False, "error": "ইনবক্সে কোনো ইমেইল পাওয়া যায়নি।"}, status_code=400)

        except Exception as e:
            error_msg = str(e)
            print(f"--> [ERROR] Exception occurred: {error_msg}", flush=True)
            await browser.close()
            return JSONResponse(content={"success": False, "error": f"Failed at process: {error_msg}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

import asyncio
from playwright.async_api import async_playwright

async def read_outlook_inbox(email, password):
    async with async_playwright() as p:
        # ব্রাউজার সরাসরি দেখার জন্য headless=False এবং স্লো-মোশন রাখা হয়েছে
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        context = await browser.new_context()
        page = await context.new_page()

        print("Navigating to Microsoft Login...")
        await page.goto("https://login.live.com/", wait_until="domcontentloaded")

        # ১. Email Input ও Next ক্লিক
        print("Entering Email...")
        email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.click()
        
        # কিবোর্ডের মতো আস্তে টাইপ করবে যাতে JS ইভেন্ট ট্র্রিগার হয়
        await email_input.press_sequentially(email, delay=50)
        await asyncio.sleep(1)

        # Enter প্রেস অথবা Next বাটনে ফোর্স ক্লিক
        try:
            await email_input.press("Enter")
        except:
            await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

        # ২. Password Input ও Sign in ক্লিক
        print("Entering Password...")
        pass_input = page.locator('input[type="password"], input[name="passwd"]').first
        await pass_input.wait_for(state="visible", timeout=15000)
        await pass_input.click()
        
        await pass_input.press_sequentially(password, delay=50)
        await asyncio.sleep(1)

        try:
            await pass_input.press("Enter")
        except:
            await page.evaluate('document.querySelector("#idSIButton9, input[type=\\"submit\\"]").click()')

        # ৩. "Let's protect your account" বা সিকিউরিটি প্রম্পট বাইপাস
        print("Checking for Security Prompts...")
        await asyncio.sleep(3)

        # পপআপ স্ক্রিনের Cancel, Skip বা Next বাটন থাকলে হ্যান্ডেল করা
        skip_selectors = ['#iCancel', 'a:has-text("Cancel")', 'a:has-text("Skip")', '#acceptButton', '#idSIButton9']
        for selector in skip_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
            except:
                pass

        # ৪. সরাসরি ইনবক্সে নেভিগেট করা
        print("Navigating directly to Outlook Inbox...")
        await page.goto("https://outlook.live.com/mail/0/", wait_until="domcontentloaded")

        try:
            print("Fetching Emails...")
            # ইনবক্স লোড হওয়ার জন্য ওয়েট
            await page.wait_for_selector('div[role="listbox"], div[role="option"]', timeout=20000)
            
            emails = await page.locator('div[role="option"]').all()
            email_list = []
            
            for item in emails[:5]:
                text = await item.inner_text()
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                if lines:
                    email_list.append(lines)

            await browser.close()
            return email_list

        except Exception as e:
            print("\n❌ Inbox loading failed:", e)
            await browser.close()
            return None

if __name__ == "__main__":
    test_email = input("Enter Email: ")
    test_pass = input("Enter Password: ")

    data = asyncio.run(read_outlook_inbox(test_email, test_pass))
    
    print("\n--- INBOX DATA ---")
    if data:
        for index, mail in enumerate(data, 1):
            print(f"{index}. {' | '.join(mail)}")
    else:
        print("Failed to fetch emails.")
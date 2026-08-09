FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# ফাইল কপি ও ডিপেন্ডেন্সি ইনস্টল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# প্লে-রাইটের প্রয়োজনীয় ব্রাউজার ইনস্টল
RUN playwright install chromium
RUN playwright install-deps

COPY . .

EXPOSE 8000

# PORT ইনভায়রনমেন্ট ভ্যারিয়েবল রিড করার কমান্ড
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]

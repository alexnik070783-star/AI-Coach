import requests
import datetime
import os
import traceback
import statistics
import matplotlib.pyplot as plt
import io
import time

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 НАСТРОЙКИ ---
USER_LAT = "53.23"       
USER_LON = "26.66"
USER_HEIGHT = 182.0      
USER_BIRTH_YEAR = 1983

# --- 📡 ОТПРАВКА (РАЗДЕЛЬНАЯ) ---
def send_telegram(text, photo_buffer=None):
    if not TG_TOKEN or not TG_CHAT_ID: 
        print("❌ ОШИБКА: Нет токенов Telegram!")
        return

    try:
        # 1. График (если есть)
        if photo_buffer:
            print("📤 Отправляю график...")
            photo_buffer.seek(0)
            url_photo = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            files = {'photo': ('chart.png', photo_buffer, 'image/png')}
            data = {'chat_id': TG_CHAT_ID}
            requests.post(url_photo, data=data, files=files)
            time.sleep(1)

        # 2. Текст (отдельно)
        print(f"📤 Отправляю текст ({len(text)} симв)...")
        url_msg = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                requests.post(url_msg, json={"chat_id": TG_CHAT_ID, 'text': part})
                time.sleep(1)
        else:
            requests.post(url_msg, json={"chat_id": TG_CHAT_ID, 'text': text})
            
        print("✅ Всё отправлено.")

    except Exception as e:
        print(f"❌ Ошибка отправки TG: {e}")

def get_ai_advice(prompt):
    try:
        if not GOOGLE_API_KEY: return "Ошибка: Нет GOOGLE_KEY."
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        models_url = f"{base_url}/models?key={GOOGLE_API_KEY}"
        data = requests.get(models_url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']; break
        gen_url = f"{base_url}/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(gen_url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"AI Error: {e}"

def get_weather():
    try:
        base = "https://api.open-meteo.com/v1/forecast"
        params = f"?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(base + params, timeout=10).json()
        if 'current_weather' not in res: return "Нет погоды"
        cur = res['current_weather']
        return f"{cur.get('temperature')}°C,

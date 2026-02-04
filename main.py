import requests
import datetime
import os
import traceback
import statistics
import matplotlib.pyplot as plt
import io

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 НАСТРОЙКИ ---
USER_LAT = "53.23"       # Несвиж
USER_LON = "26.66"
USER_HEIGHT = 182.0      
USER_BIRTH_YEAR = 1983

# --- 📡 ОТПРАВКА ---
def send_telegram(text, photo_buffer=None):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        if photo_buffer:
            photo_buffer.seek(0)
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            files = {'photo': ('chart.png', photo_buffer, 'image/png')}
            data = {'chat_id': TG_CHAT_ID, 'caption': text[:1024]}
            requests.post(url, data=data, files=files)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, 'text': text}
            requests.post(url, json=data)
    except Exception as e:
        print(f"TG Error: {e}")

def get_ai_advice(prompt):
    try:
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
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч"
    except: return "Ошибка погоды"

def generate_charts(wellness_data):
    if not wellness_data or len(wellness_data) < 2: return None
    dates, weights, hrvs = [], [], []
    for day in wellness_data[-14:]:
        dt_str = day.get('id', '')[5:] 
        w = day.get('weight')
        h = day.get('hrv')
        if w: 
            dates.append(dt_str)
            weights.append(float(w))
            hrvs.append(h if h else 0)
    if not dates: return None
    plt.style.use('dark_background')
    fig, ax1 = plt.subplots(figsize=(10, 5))
    color = 'tab:red'
    ax1.set_xlabel('Дата')
    ax1.set_ylabel('Вес (кг)', color=color)
    ax1.plot(dates, weights, color=color, marker='o', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)
    if any(hrvs):
        ax2 = ax1.twinx() 
        color = 'tab:green'
        ax2.set_ylabel('HRV (ms)', color=color)
        ax2.bar(dates, hrvs, color=color, alpha

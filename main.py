import requests
import datetime
import os
import io
import traceback

# --- 1. НАСТРОЙКА ГРАФИКИ ---
import matplotlib
matplotlib.use('Agg') # Рисуем без монитора
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

def send_telegram_photo(caption, photo_file):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
        files = {"photo": photo_file}
        requests.post(url, data=data, files=files)
    except Exception as e:
        print(f"Ошибка фото: {e}")

def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка текста: {e}")

def create_pro_charts(history_data, power_curve_data):
    # Проверка на пустые данные
    if not history_data or not isinstance(history_data, list): return None

    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
    plt.subplots_adjust(hspace=0.3)

    # === ГРАФИК 1: ФОРМА ===
    dates, ctl, atl, tsb = [], [], [], []
    # Сортируем и защищаемся от битых данных
    clean_history = [d for d in history_data if isinstance(d, dict) and 'id' in d]
    
    for day in sorted(clean_history, key=lambda x: x['id']):
        dates.append(datetime.date.fromisoformat(day['id']))
        ctl.append(day.get('ctl', 0))
        atl.append(day.get('atl', 0))
        tsb.append(day.get('tsb', 0))

    ax1.plot(dates, ctl, color='#2196F3', linewidth=2, label='Fitness')
    ax1.plot(dates, atl, color='#9C27B0', alpha=0.6, label='Fatigue')
    ax1.fill_between(dates, tsb, 0, where=[t >= 0 for t in tsb], color='green', alpha=0.2)
    ax1.fill_between(dates, tsb, 0, where=[t < 0 for t in tsb], color='orange', alpha=0.2)
    ax1.legend(loc='upper left')
    ax1.set_title("Fitness & Form", fontsize=12)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))

    # === ГРАФИК 2: МОЩНОСТЬ ===
    # Безопасное извлечение точек
    points = []
    if isinstance(power_curve_data, dict):
        points = power_curve_data.get('points', [])
    
    if points:
        valid = [p for p in points if isinstance(p, list) and len(p) >= 2 and p[0] <= 7200 and p[1] > 0]
        if valid:
            secs = [p[0] for p in valid]
            watts = [p[1] for p in valid]
            ax2.set_xscale('log')
            ax2.plot(secs, watts, color='#E91E63', linewidth=2)
            ax2.set_title("Power Curve", fontsize=12)
            
            # Отметки
            targets = {15: "15s", 60: "1m", 300: "5m", 1200: "20m"}
            for d, l in targets.items():
                # Ищем ближайшую точку
                closest = min(valid, key=lambda x: abs(x[0]-d))
                ax2.annotate(f"{l}\n{closest[1]}W", (closest[0], closest[1]), 
                             xytext=(0,10), textcoords='offset points', ha='center', fontsize=9, fontweight='bold')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def get_ai_advice(prompt):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        models = requests.get(url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in models:
            for m in models['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']; break
        
        api = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(api, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"ИИ молчит. {e}"

def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=42)).isoformat()
        end = today.isoformat()
        
        # 1. Загрузка данных
        hist = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        raw_curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?old

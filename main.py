import requests
import datetime
import os
import io
import traceback
import json

# --- 1. ГРАФИКА ---
import matplotlib
matplotlib.use('Agg') # Рисуем в памяти
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- ОТПРАВКА (БЕЗ MARKDOWN) ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка отправки текста: {e}")

def send_telegram_photo(caption, photo_file):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        data = {"chat_id": TG_CHAT_ID, "caption": caption}
        photo_file.seek(0)
        files = {"photo": ('chart.png', photo_file, 'image/png')}
        resp = requests.post(url, data=data, files=files)
        
        if resp.status_code != 200:
            send_telegram_text(f"⚠️ График не прошел (Код {resp.status_code}). Совет тренера:\n\n{caption}")
    except Exception as e:
        send_telegram_text(f"⚠️ Ошибка фото: {e}")
        send_telegram_text(caption)

# --- ГРАФИКИ ---
def create_charts(history_data, power_curve_data):
    if not history_data or not isinstance(history_data, list): return None

    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
    plt.subplots_adjust(hspace=0.3)

    # Данные
    dates, ctl, tsb, weight = [], [], [], []
    clean_hist = [d for d in history_data if isinstance(d, dict) and 'id' in d]
    
    for day in sorted(clean_hist, key=lambda x: x['id']):
        dates.append(datetime.date.fromisoformat(day['id']))
        ctl.append(day.get('ctl', 0))
        tsb.append(day.get('tsb', 0))
        weight.append(day.get('weight', None))

    # График 1: Fitness
    ax1.plot(dates, ctl, color='blue', linewidth=2, label='Fitness')
    ax1.fill_between(dates, tsb, 0, where=[t >= 0 for t in tsb], color='green', alpha=0.3)
    ax1.fill_between(dates, tsb, 0, where=[t < 0 for t in tsb], color='orange', alpha=0.3)
    ax1.set_title(f"Fitness & Weight (Last 42 days)")
    ax1.legend(loc='upper left')

    # Вес (справа)
    if any(w is not None for w in weight):
        ax1r = ax1.twinx()
        valid_w = [(d, w) for d, w in zip(dates, weight) if w is not None]
        if valid_w:
            wd, ww = zip(*valid_w)
            ax1r.plot(wd, ww, color='red', linestyle='--', linewidth=2, label='Weight')
    
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))

    # График 2: Power Curve
    points = []
    if isinstance(power_curve_data, dict):
        points = power_curve_data.get('points', [])
    
    if points:
        valid = [p for p in points if isinstance(p, list) and len(p)>=2 and p[0] <= 7200 and p[1] > 0]
        if valid:
            secs = [p[0] for p in valid]
            watts = [p[1] for p in valid]
            ax2.set_xscale('log')
            ax2.plot(secs, watts, color='purple', linewidth=2)
            ax2.set_title("Power Curve")
            
            targets = {15: "15s", 60: "1m", 300: "5m", 1200: "20m"}
            for d, l in targets.items():
                closest = min(valid, key=lambda x: abs(x[0]-d))
                ax2.annotate(f"{l}\n{closest[1]}W", (closest[0], closest[1]), 
                             xytext=(0,

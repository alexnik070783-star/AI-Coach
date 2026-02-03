import requests
import datetime
import os
import io
import traceback
import json

# --- 1. ГРАФИКА (Без экрана) ---
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- ОТПРАВКА (С ЗАЩИТОЙ) ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка текста: {e}")

def send_telegram_photo(caption, photo_file):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
        # Важно: photo_file.name нужен для телеграма, даже если файл в памяти
        photo_file.name = 'chart.png' 
        files = {"photo": photo_file}
        resp = requests.post(url, data=data, files=files)
        
        # Если Телеграм отказал - шлем текст с ошибкой
        if resp.status_code != 200:
            send_telegram_text(f"{caption}\n\n⚠️ *График не пролез:* `{resp.text}`")
    except Exception as e:
        send_telegram_text(f"{caption}\n\n⚠️ *Ошибка отправки фото:* `{e}`")

# --- ГРАФИКИ ---
def create_charts(history_data, power_curve_data):
    if not history_data or not isinstance(history_data, list): return None

    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
    plt.subplots_adjust(hspace=0.3)

    # === ГРАФИК 1: ФИТНЕС + ВЕС ===
    dates, ctl, tsb, weight = [], [], [], []
    
    clean_hist = [d for d in history_data if isinstance(d, dict) and 'id' in d]
    
    for day in sorted(clean_hist, key=lambda x: x['id']):
        dates.append(datetime.date.fromisoformat(day['id']))
        ctl.append(day.get('ctl', 0))
        tsb.append(day.get('tsb', 0))
        weight.append(day.get('weight', None))

    # Ось слева (Fitness)
    ax1.plot(dates, ctl, color='#2196F3', linewidth=2, label='Fitness (CTL)')
    ax1.fill_between(dates, tsb, 0, where=[t >= 0 for t in tsb], color='green', alpha=0.2)
    ax1.fill_between(dates, tsb, 0, where=[t < 0 for t in tsb], color='orange', alpha=0.2)
    ax1.set_title("Fitness vs Weight", fontsize=12)
    ax1.legend(loc='upper left')

    #

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

# --- ОТПРАВКА ---
def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка текста: {e}")

def send_telegram_photo(caption, photo_file):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        data = {"chat_id": TG_CHAT_ID, "caption": caption}
        
        # Перематываем файл в начало
        photo_file.seek(0)
        # Явно задаем имя файла, чтобы Телеграм не ругался (Код 400)
        files = {"photo": ('chart.png', photo_file, 'image/png')}
        
        resp = requests.post(url, data=data, files=files)
        
        if resp.status_code != 200:
            # Если график не прошел, шлем подробную ошибку от Телеграма
            send_telegram_text(f"⚠️ График не прошел (Код {resp.status_code}):\nTelegam ответил: {resp.text}\n\nСовет тренера:\n{caption}")
    except Exception as e:
        send_telegram_text(f"⚠️ Ошибка отправки фото (Python): {e}")
        send_telegram_text(caption)

# --- ГРАФИКИ ---
def create_charts(history_data, power_curve_data):
    if not history_data or not isinstance(history_data, list): return None

    # Проверка: если данных меньше 2 дней, график строить бессмысленно
    clean_hist = [d for d in history_data if isinstance(d, dict) and 'id' in d]
    if len(clean_hist) < 2:
        return None

    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots

import requests
import datetime
import os
import statistics

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 📡 ОТПРАВКА ---
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
        requests.post(url, json=data)
    except Exception as e:
        print(f"TG Error: {e}")

# --- 🕵️‍♂️ АУДИТ (ГЛАВНАЯ ФУНКЦИЯ) ---
def run_audit():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        
        # 1. Берем данные за 90 дней (Квартал)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=90)).isoformat()
        end = today.isoformat()
        
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        
        print(f"Скачиваю архив с {start} по {end}...")
        activities = requests.get(f"{base_api}/activities?oldest={start}&newest={end}", auth=auth).json()
        wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()

        if not activities:
            send_telegram("❌ В архиве за 90 дней пусто. Интервалс ничего не отдал.")
            return

        # --- АНАЛИЗ 1: ОБЪЕМЫ ---
        total_time = 0
        ride_count = 0
        run_count = 0
        zwift_count = 0
        
        for a in activities:
            total_time += a.get('moving_time', 0)
            atype = a.get('type')
            
            if atype == 'Ride': ride_count += 1
            if atype == 'VirtualRide': 
                ride_count += 1
                zwift_count += 1
            if atype == 'Run' or atype == 'Walk': run_count += 1
        
        # --- АНАЛИЗ 2: ВЕС ---
        # С

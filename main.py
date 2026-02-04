import requests
import datetime
import os
import traceback
import statistics

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 НАСТРОЙКИ ---
USER_LAT = "53.23"       # Несвиж
USER_LON = "26.66"
USER_HEIGHT = 182.0      # <-- Твой рост (константа)

# --- ФУНКЦИИ ---
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_ai_advice(prompt):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        data = requests.get(url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']
                    break
        
        api = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(api, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"AI Error: {e}"

def get_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url, timeout=10).json()
        if 'current_weather' not in res:
            return "Нет погоды"
        
        cur = res['current_weather']
        dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        idx = int((cur.get('winddirection') + 22.5) % 360 / 45)
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч ({dirs[idx]})"
    except Exception:
        return "Ошибка погоды"

# --- 👤 ПОЛУЧЕНИЕ ВОЗРАСТА ---
def get_athlete_profile(auth):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        profile = requests.get(url, auth=auth).json()
        
        dob_str = profile.get('dob')
        age = 35 # Дефолт
        if dob_str:
            dob = datetime.datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
        return age
    except Exception:
        return 35

# --- 🥗 АНАЛИЗ ПИТАНИЯ (ЗАЩИЩЕННЫЙ) ---
def analyze_nutrition(wellness_data, age):
    # 1. Авто-вес (с защитой от None)
    current_weight = 78.0 
    for day in reversed(wellness_data):
        w = day.get('weight')
        if w and float(w) > 0:
            current_weight = float(w)
            break

    # 2. BMR
    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * age) + 5
    daily_norm = bmr * 1.2 
    
    # 3. Еда (с защитой от None)
    if not wellness_data:
        return f"Вес: {current_weight}кг. Нет данных.", 0, current_weight
    
    last_day_with_food = None
    for day in reversed(wellness_data):
        # Используем (val or 0), чтобы превратить None в 0
        kcal = day.get('kcalConsumed') or 0
        if kcal > 0:
            last_day_with_food = day
            break
            
    if not last_day_with_food:
        return f"⚠️ Вес {current_weight}кг. Данные о еде не найдены (или они равны 0).", 0, current_weight

    # Безопасное извлечение
    eaten = last_day_with_food.get('kcalConsumed') or 0
    prot = last_day_with_food.get('protein') or 0
    fat = last_day_with_food.get('fat') or 0
    carbs = last_day_with_food.get('carbs') or 0
    
    balance = eaten - daily_norm
    
    report = f"""
    📊 ПИТАНИЕ (Вес {current_weight}кг, Возраст {age}):
    • Съедено: {eaten} ккал
    • Норма (Life): ~{int(daily_norm)} ккал
    • Б/Ж/У: {prot} / {fat} / {carbs}
    • Белок: {prot / current_weight:.1f} г/кг
    """
    return report, balance, current_weight

# --- 🧠 БИОМЕТРИКА ---
def analyze_neuro(wellness_data):
    if not wellness_data or len(wellness_data) < 2:
        return "Мало данных", "GREEN"
    
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    sleep_list = [d.get('sleepSecs') for d in wellness_data if d.get('sleepSecs')]
    today_hrv = hrv_list[-1] if hrv_list else None
    
    status = "GREEN"
    details = []
    
    if today_hrv and len(hrv_list) > 3:
        avg = statistics.mean(hrv_list[:-1])
        diff = ((today_hrv - avg)/avg)*100
        if diff < -10: 
            status = "RED"
            details.append(f"HRV упал ({diff:.0f}%)")
        else:
            details.append(f"HRV норм")
            
    if sleep_list:
        last_sleep = sleep_list[-1] / 3600
        if last_sleep < 6:
            status = "RED" if status == "RED" else "YELLOW"
            details.append(f"Сон {last_sleep:.1f}ч (Мало)")
        else:
            details.append(f"Сон {last_sleep:.1f}ч")
            
    return ", ".join(details), status

# --- ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=7)).isoformat()
        end = today.isoformat()
        
        wellness = requests.get(f"https://intervals

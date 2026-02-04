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
USER_LAT = "53.23"
USER_LON = "26.66"
USER_HEIGHT = 182.0

# --- ФУНКЦИИ ---
def send_telegram(text):
    print(f"📡 Пытаюсь отправить в Telegram...")
    if not TG_TOKEN or not TG_CHAT_ID:
        print("❌ ОШИБКА: Нет ключей TG_TOKEN или TG_CHAT_ID в Secrets!")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text}
        res = requests.post(url, json=data)
        if res.status_code == 200:
            print("✅ Telegram: Успешно отправлено!")
        else:
            print(f"❌ Telegram Error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def get_ai_advice(prompt):
    print("🤖 Стучусь к ИИ (Gemini)...")
    if not GOOGLE_API_KEY:
        print("❌ ОШИБКА: Нет GOOGLE_KEY!")
        return "Ошибка: Нет ключа AI"
        
    try:
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        models_url = f"{base_url}/models?key={GOOGLE_API_KEY}"
        data = requests.get(models_url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']
                    break
        
        gen_url = f"{base_url}/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(gen_url, json={"contents": [{"parts": [{"text": prompt}]}]})
        answer = res.json()['candidates'][0]['content']['parts'][0]['text']
        print("✅ ИИ ответил.")
        return answer
    except Exception as e:
        print(f"❌ Ошибка ИИ: {e}")
        return f"AI Error: {e}"

def get_weather():
    try:
        base = "https://api.open-meteo.com/v1/forecast"
        params = f"?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(base + params, timeout=10).json()
        if 'current_weather' not in res: return "Нет погоды"
        cur = res['current_weather']
        dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        idx = int((cur.get('winddirection') + 22.5) % 360 / 45)
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч ({dirs[idx]})"
    except: return "Ошибка погоды"

# --- ПРОФИЛЬ ---
def get_athlete_profile(auth):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        profile = requests.get(url, auth=auth).json()
        dob_str = profile.get('dob')
        age = 35 
        if dob_str:
            dob = datetime.datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except: return 35

# --- АНАЛИЗ ---
def analyze_nutrition(wellness_data, age):
    current_weight = 78.0 
    for day in reversed(wellness_data):
        w = day.get('weight')
        if w and float(w) > 0:
            current_weight = float(w)
            break
            
    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * age) + 5
    daily_norm = bmr * 1.2 
    
    if not wellness_data: return "Нет данных", 0, current_weight
    
    last_day_with_food = None
    for day in reversed(wellness_data):
        kcal = day.get('kcalConsumed') or 0
        if kcal > 0:
            last_day_with_food = day
            break
    
    if not last_day_with_food:
        return f"Вес {current_weight}кг. Данные о еде не найдены.", 0, current_weight

    eaten = last_day_with_food.get('kcalConsumed') or 0
    balance = eaten - daily_norm
    report = f"Съедено: {eaten} ккал. Баланс: {balance:+.0f} ккал"
    return report, balance, current_weight

def analyze_neuro(wellness_data):
    if not wellness_data: return "Нет данных", "GREEN"
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    rhr_list = [d.get('restingHR') for d in wellness_data if d.get('restingHR')]
    sleep_list = [d.get('sleepSecs') for d in wellness_data if d.get('sleepSecs')]
    last_day = wellness_data[-1]
    
    status = "GREEN"
    details = []
    
    # RHR
    if last_day.get('restingHR') and len(rhr_list) > 3:
        avg = statistics.mean(rhr_list[:-1])
        diff = last_day.get('restingHR') - avg
        if diff > 5: 
            status = "RED"
            details.append(f"Пульс +{diff:.0f}")
        elif diff > 2:
            status = "YELLOW"
            details.append(f"Пульс высоковат")
            
    # HRV
    if last_day.get('hrv') and len(hrv_list) > 3:
        avg = statistics.mean(hrv_list[:-1])
        diff = ((last_day.get('hrv') - avg)/avg)*100
        if diff < -15: 
            status = "RED" if status != "RED" else "RED"
            details.append(f"HRV -{abs(diff):.0f}%")
            
    # Sleep
    if sleep_list:
        if (sleep_list[-1]/3600) < 6: details.append("Мало сна")
        
    return ", ".join(details) or "Норма", status

# --- ЗАПУСК ---
def run_coach():
    print("--- 🚀 ЗАПУСК СКРИПТА (V25.1 DEBUG) ---")
    
    if not INTERVALS_ID or not INTERVALS_API_KEY:
        print("❌ ОШИБКА: Нет ключей INTERVALS_ID или INTERVALS_KEY")
        return

    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=14)).isoformat()
        end = today.isoformat()
        
        print(f"📥 Скачиваю данные Intervals ({start} - {end})...")
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        w_url = f"{base_api}/wellness?oldest={start}&newest={end}"
        wellness = requests.get(w_url, auth=auth).json()
        e_url = f"{base_api}/events?oldest={end}&newest={end}"
        events = requests.get(e_url, auth=auth).json()
        print(f"✅ Данные получены. Дней wellness: {len(wellness)}")
        
        user_age = get_athlete_profile(auth)
        weather_msg = get_weather()
        
        nutri_text, balance, actual_weight = analyze_nutrition(wellness, user_age)
        bio_text, bio_status = analyze_neuro(wellness)
        
        print(f"📊 Анализ: Вес {actual_weight}, Статус {bio_status}")

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        prompt = f"""
        Ты тренер. Краткий отчет.
        Данные: Вес {actual_weight}, {user_age} лет.
        Статус: {bio_status} ({bio_text}).
        Еда: {nutri_text}.
        Погода: {weather_msg}.
        План: {plan_txt}.
        Дай совет по тренировке и еде.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🔍 DEBUG REPORT:\n\n{advice}")
        print("--- 🏁 КОНЕЦ СКРИПТА ---")

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {traceback.format_exc()}")
        send_telegram(f"CRASH: {e}")

if __name__ == "__main__":
    run_coach()

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
USER_HEIGHT = 182.0      # Рост (см)
USER_BIRTH_YEAR = 1983   # <-- ИСПРАВИЛ (07.07.1983)

# --- ФУНКЦИИ ---
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

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

# --- 🥗 ПИТАНИЕ ---
def analyze_nutrition(wellness_data, current_age):
    current_weight = 78.0 
    for day in reversed(wellness_data):
        w = day.get('weight')
        if w and float(w) > 0:
            current_weight = float(w)
            break
            
    # Динамический расчет BMR (учитывает возраст)
    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * current_age) + 5
    daily_norm = bmr * 1.2 
    
    if not wellness_data: return "Нет данных", 0, current_weight
    
    last_day_with_food = None
    for day in reversed(wellness_data):
        kcal = day.get('kcalConsumed') or 0
        if kcal > 0:
            last_day_with_food = day
            break
            
    eaten = (last_day_with_food.get('kcalConsumed') if last_day_with_food else 0) or 0
    balance = eaten - daily_norm
    
    report = f"Съедено: {eaten} ккал. Баланс: {balance:+.0f} ккал"
    return report, balance, current_weight

# --- 🧬 БИОМЕТРИКА ---
def analyze_neuro(wellness_data):
    if not wellness_data: return "Нет данных", "GREEN"
    
    last_day = wellness_data[-1]
    today_hrv = last_day.get('hrv')
    today_rhr = last_day.get('restingHR')
    today_spo2 = last_day.get('spO2')
    readiness = last_day.get('readiness')
    
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    rhr_list = [d.get('restingHR') for d in wellness_data if d.get('restingHR')]
    
    details = []
    status = "GREEN"
    
    # 1. HRV
    if today_hrv:
        avg_hrv = statistics.mean(hrv_list[:-1]) if len(hrv_list) > 1 else today_hrv
        diff_hrv = ((today_hrv - avg_hrv)/avg_hrv)*100
        txt = f"HRV {today_hrv:.0f}ms"
        if diff_hrv < -10: 
            txt += f" (📉 -{abs(diff_hrv):.0f}%)"
            status = "RED"
        details.append(txt)
    else:
        details.append("HRV -")

    # 2. RHR
    if today_rhr:
        avg_rhr = statistics.mean(rhr_list[:-1]) if len(rhr_list) > 1 else today_rhr
        diff_rhr = today_rhr - avg_rhr
        txt = f"RHR {today_rhr:.0f}"
        if diff_rhr > 5:
            txt += f" (📈 +{diff_rhr:.0f}!)"
            status = "RED" if status != "RED" else "RED"
        details.append(txt)
    else:
        details.append("RHR -")

    # 3. Доп
    if today_spo2: details.append(f"SpO2 {today_spo2}%")
    if readiness: details.append(f"Готовность {readiness}%")
        
    return ", ".join(details), status

# --- ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=14)).isoformat()
        end = today.isoformat()
        
        # 1. СЧИТАЕМ ВОЗРАСТ (С учетом дня рождения)
        # Если сегодня ДО дня рождения - вычитаем 1 год
        is_birthday_passed = (today.month, today.day) >= (7, 7) # 7 июля
        real_age = today.year - USER_BIRTH_YEAR - (0 if is_birthday_passed else 1)
        
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"{base_api}/events?oldest={end}&newest={end}", auth=auth).json()
        weather_msg = get_weather()
        
        ctl = 0.0
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl')); break
        
        nutri_text, balance, actual_weight = analyze_nutrition(wellness, real_age)
        bio_text, bio_status = analyze_neuro(wellness)

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        prompt = f"""
        Ты личный тренер (биохакер).
        
        ДАННЫЕ:
        - Возраст: {real_age} лет (ДР: 07.07.{USER_BIRTH_YEAR}).
        - Вес: {actual_weight} кг.
        - БИОМЕТРИКА: {bio_text}.
        - CTL: {ctl:.1f}.
        - Погода: {weather_msg}.
        - Питание: {nutri_text}.
        
        ИНСТРУКЦИЯ:
        1. БИОМЕТРИКА: Оцени состояние (HRV, Пульс).
        2. ПИТАНИЕ: Дай совет исходя из дефицита. Если <500 ккал, напомни проверить запись.
        3. ПЛАН: Адаптируй под погоду и статус.
        
        Формат:
        🧬 БИОМЕТРИКА: ...
        🥗 ПИТАНИЕ: ...
        🚀 ПЛАН: ...
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🤖 COACH V25.3 (1983):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

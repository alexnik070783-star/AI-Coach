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
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # 1. Модель
        models_url = f"{base_url}/models?key={GOOGLE_API_KEY}"
        data = requests.get(models_url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']
                    break
        
        # 2. Генерация
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
        
        if 'current_weather' not in res:
            return "Нет погоды"
        
        cur = res['current_weather']
        dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        idx = int((cur.get('winddirection') + 22.5) % 360 / 45)
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч ({dirs[idx]})"
    except Exception:
        return "Ошибка погоды"

# --- 👤 ПРОФИЛЬ ---
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
    except Exception:
        return 35

# --- 🥗 ПИТАНИЕ (КАЛОРИИ) ---
def analyze_nutrition(wellness_data, age):
    current_weight = 78.0 
    for day in reversed(wellness_data):
        w = day.get('weight')
        if w and float(w) > 0:
            current_weight = float(w)
            break

    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * age) + 5
    daily_norm = bmr * 1.2 
    
    if not wellness_data:
        return f"Вес: {current_weight}кг. Нет данных.", 0, current_weight
    
    last_day_with_food = None
    for day in reversed(wellness_data):
        kcal = day.get('kcalConsumed') or 0
        if kcal > 0:
            last_day_with_food = day
            break
            
    if not last_day_with_food:
        return f"⚠️ Вес {current_weight}кг. Данные о еде не найдены (0 ккал).", 0, current_weight

    eaten = last_day_with_food.get('kcalConsumed') or 0
    balance = eaten - daily_norm
    
    report = f"""
    📊 ПИТАНИЕ (Вес {current_weight}кг):
    • Съедено: {eaten} ккал
    • Норма (Life): ~{int(daily_norm)} ккал
    • Баланс: {balance:+.0f} ккал
    """
    return report, balance, current_weight

# --- 🧬 БИОХАКИНГ (ПОЛНЫЙ СКАН) ---
def analyze_neuro(wellness_data):
    if not wellness_data or len(wellness_data) < 2:
        return "Мало данных", "GREEN"
    
    # Собираем списки данных
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    rhr_list = [d.get('restingHR') for d in wellness_data if d.get('restingHR')]
    sleep_list = [d.get('sleepSecs') for d in wellness_data if d.get('sleepSecs')]
    
    # Последние данные
    last_day = wellness_data[-1]
    today_hrv = last_day.get('hrv')
    today_rhr = last_day.get('restingHR')
    today_spo2 = last_day.get('spO2')
    readiness = last_day.get('readiness') # Готовность от Intervals
    bp_sys = last_day.get('systolic')
    
    status = "GREEN"
    details = []
    
    # 1. HRV (Вариабельность)
    if today_hrv and len(hrv_list) > 3:
        avg_hrv = statistics.mean(hrv_list[:-1]) # Среднее без сегодня
        diff_hrv = ((today_hrv - avg_hrv) / avg_hrv) * 100
        if diff_hrv < -15: 
            status = "RED"
            details.append(f"HRV упал ({diff_hrv:.0f}%)")
        elif diff_hrv < -5:
            if status == "GREEN": status = "YELLOW"
            details.append(f"HRV ниже нормы")
        else:
            details.append(f"HRV ок")

    # 2. RHR (Пульс покоя) - Важнейший маркер!
    if today_rhr and len(rhr_list) > 3:
        avg_rhr = statistics.mean(rhr_list[:-1])
        diff_rhr = today_rhr - avg_rhr
        if diff_rhr > 5:
            status = "RED"
            details.append(f"Пульс покоя +{diff_rhr:.0f} уд! (Усталость?)")
        elif diff_rhr > 2:
            if status == "GREEN": status = "YELLOW"
            details.append(f"Пульс покоя высоковат")
        else:
            details.append(f"Пульс {today_rhr} (Норм)")

    # 3. SpO2 (Кислород)
    if today_spo2:
        if today_spo2 < 95:
            status = "RED"
            details.append(f"SpO2 низкий ({today_spo2}%)")
        else:
            details.append(f"SpO2 {today_spo2}%")
            
    # 4. Сон
    if sleep_list:
        last_sleep = sleep_list[-1] / 3600
        if last_sleep < 6:
            if status == "GREEN": status = "YELLOW"
            details.append(f"Сон {last_sleep:.1f}ч (Мало)")
        else:
            details.append(f"Сон {last_sleep:.1f}ч")

    # Итоговый отчет
    full_text = ", ".join(details)
    if readiness:
        full_text += f". Готовность системы: {readiness}%"
        
    return full_text, status

# --- ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Берем 14 дней для лучшей статистики
        start = (today - datetime.timedelta(days=14)).isoformat()
        end = today.isoformat()
        
        # URLs
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        w_url = f"{base_api}/wellness?oldest={start}&newest={end}"
        wellness = requests.get(w_url, auth=auth).json()
        
        e_url = f"{base_api}/events?oldest={end}&newest={end}"
        events = requests.get(e_url, auth=auth).json()
        
        weather_msg = get_weather()
        user_age = get_athlete_profile(auth)
        
        ctl = 0.0
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break
        
        nutri_text, balance, actual_weight = analyze_nutrition(wellness, user_age)
        bio_text, bio_status = analyze_neuro(wellness)

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        prompt = f"""
        Ты умный тренер-биохакер. Анализируй глубоко.
        
        ДАННЫЕ АТЛЕТА:
        - Вес: {actual_weight} кг. Возраст: {user_age}.
        - Цель: Рекомпозиция.
        - CTL (Фитнес): {ctl:.1f}.
        - БИОМЕТРИКА: {bio_status} ({bio_text}).
        - Погода: {weather_msg}.
        - План в календаре: {plan_txt}.
        
        ОТЧЕТ ПО ПИТАНИЮ:
        {nutri_text}
        
        ЗАДАЧА:
        1. ОЦЕНКА СОСТОЯНИЯ (Приоритет №1):
           - Посмотри на Пульс Покоя (RHR) и HRV. 
           - Если пульс вырос, а HRV упал -> Это стресс/болезнь. Отменяй тяжелую тренировку!
           - Если SpO2 ниже 95 -> Предупреди о гипоксии/здоровье.
           
        2. ТРЕНИРОВКА:
           - Адаптируй план под "Здоровье" и "Погоду".
           - Если статус RED -> Только легкая растяжка или сон.
           
        3. СОВЕТ ПО ЕДЕ:
           - Исходя из дефицита калорий.
        
        Ответь:
        🧬 СОСТОЯНИЕ: ... (Твой анализ биометрии)
        🚀 ТРЕНИРОВКА: ...
        🥗 ПИТАНИЕ: ...
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🧬 COACH V25 (BIO-HACKER):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

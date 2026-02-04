import requests
import datetime
import os
import traceback
import statistics

# --- КЛЮЧИ (Берем из Secrets) ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 КООРДИНАТЫ (НЕСВИЖ - ЖЕСТКО ВШИТЫ) ---
USER_LAT = "53.23"
USER_LON = "26.66"

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        data = requests.get(url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']; break
        
        api = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(api, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"AI Error: {e}"

# --- ПОГОДА (ОТЛАЖЕННАЯ) ---
def get_weather():
    try:
        # Добавил timeout, чтобы не висело
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url, timeout=10).json()
        
        if 'current_weather' not in res:
            return f"Ошибка API погоды: {res}" # Покажет ошибку, если она есть
            
        cur = res['current_weather']
        temp = cur.get('temperature')
        wind_s = cur.get('windspeed')
        wind_d = cur.get('winddirection')
        
        # Компас
        dirs = ["С (Север)", "СВ", "В (Восток)", "ЮВ", "Ю (Юг)", "ЮЗ", "З (Запад)", "СЗ"]
        idx = int((wind_d + 22.5) % 360 / 45)
        
        return f"{temp}°C, Ветер {wind_s} км/ч ({dirs[idx]})"
    except Exception as e:
        return f"Сбой погоды: {str(e)}"

# --- 🩺 АНАЛИЗ ЗДОРОВЬЯ ---
def analyze_recovery(wellness_data):
    if not isinstance(wellness_data, list) or len(wellness_data) < 2:
        return "Нет данных о пульсе", "Неизвестно ⚪️"
    
    rhr_list = [day.get('restingHR') for day in wellness_data if day.get('restingHR')]
    
    if not rhr_list:
        return "Пульс покоя не измерен", "Нет данных ⚪️"

    today_rhr = rhr_list[-1]
    avg_rhr = statistics.mean(rhr_list[:-1]) if len(rhr_list) > 1 else today_rhr
    diff = today_rhr - avg_rhr
    
    status = ""
    if diff > 6:
        status = f"🔴 ОСТОРОЖНО! (+{diff:.1f} уд). Возможен стресс."
    elif diff > 3:
        status = f"🟡 Внимание (+{diff:.1f} уд). Не перегружайся."
    elif diff < -2:
        status = f"🟢 ОТЛИЧНО! (-{abs(diff):.1f} уд). Ты свеж."
    else:
        status = f"🟢 Норма ({today_rhr} уд)."
        
    return f"{today_rhr} уд/мин (Средний: {avg_rhr:.1f})", status

# --- ГЛАВНЫЙ ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=30)).isoformat()
        end = today.isoformat()
        
        # 1. ЗАГРУЗКА
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()
        weather_msg = get_weather()

        # 2. ФИТНЕС
        ctl = 0.0
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break
        
        # 3. ЗДОРОВЬЕ
        rhr_val, rhr_status = analyze_recovery(wellness)

        # 4. ПЛАН
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 5. AI ПРОМПТ
        prompt = f"""
        Ты умный тренер по триатлону.
        
        ДАННЫЕ:
        1. Фитнес (CTL): {ctl:.1f}.
        2. ЗДОРОВЬЕ: {rhr_val}. СТАТУС: {rhr_status}.
        3. ПОГОДА (Несвиж): {weather_msg}.
        4. ПЛАН: {plan_txt}.
        
        АЛГОРИТМ:
        1. ЗДОРОВЬЕ ГЛАВНЕЕ ВСЕГО. 
           - Если статус 🔴 -> Только Отдых.
           - Если 🟢 -> Можно работать.
           
        2. АНАЛИЗ ПОГОДЫ:
           - Температура < 5°C -> "INDOOR" (Станок/Дорожка).
           - Ветер > 25 км/ч -> "INDOOR" или учитывать ветер.
           - Тепло -> "OUTDOOR".
           
        3. ЗАДАНИЕ:
           - Если CTL < 10 и Здоровье 🟢 -> Игнорируй "Отдых", дай базу (40-60 мин, Зона 2).
           - Укажи конкретно: "Велостанок" или "Улица".
        
        Ответь коротко:
        ❤️ ЗДОРОВЬЕ: ...
        🌤 ПОГОДА: ...
        🚀 ЗАДАНИЕ: ...
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🩺 COACH V18.1 (FIXED):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Critical Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

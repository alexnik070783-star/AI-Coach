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

# --- 🌍 КООРДИНАТЫ (НЕСВИЖ) ---
USER_LAT = os.environ.get("USER_LAT", "53.23") 
USER_LON = os.environ.get("USER_LON", "26.66")

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

# --- ПОГОДА ---
def get_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url).json()
        if 'current_weather' not in res: return "Нет погоды"
        cur = res['current_weather']
        dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        idx = int((cur.get('winddirection') + 22.5) % 360 / 45)
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч ({dirs[idx]})"
    except:
        return "Ошибка погоды"

# --- 🩺 АНАЛИЗ ЗДОРОВЬЯ (НОВОЕ) ---
def analyze_recovery(wellness_data):
    if not isinstance(wellness_data, list) or len(wellness_data) < 2:
        return "Нет данных о пульсе", "Неизвестно"
    
    # Собираем пульс покоя (restingHR) за последние 7 дней
    rhr_list = [day.get('restingHR') for day in wellness_data if day.get('restingHR')]
    
    if not rhr_list:
        return "Пульс покоя не измерен", "Нет данных"

    today_rhr = rhr_list[-1] # Последнее измерение
    avg_rhr = statistics.mean(rhr_list[:-1]) if len(rhr_list) > 1 else today_rhr
    
    diff = today_rhr - avg_rhr
    
    # Логика Светофора
    status = ""
    if diff > 6:
        status = f"🔴 ОСТОРОЖНО! Пульс +{diff:.1f} уд. к норме. Возможен стресс/болезнь."
    elif diff > 3:
        status = f"🟡 Внимание. Пульс +{diff:.1f} уд. Не перегружайся."
    elif diff < -2:
        status = f"🟢 ОТЛИЧНО! Пульс -{abs(diff):.1f} уд. Ты супер-восстановлен."
    else:
        status = f"🟢 Норма. Пульс стабилен ({today_rhr} уд)."
        
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

        # 2. АНАЛИЗ
        ctl = 0.0
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break
        
        # Новый блок здоровья
        rhr_val, rhr_status = analyze_recovery(wellness)

        # 3. ПЛАН
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. AI ПРОМПТ
        prompt = f"""
        Ты умный тренер по триатлону (Вело + Бег).
        
        ДАННЫЕ АТЛЕТА:
        1. Фитнес (CTL): {ctl} (Уровень: Базовый).
        2. ЗДОРОВЬЕ (Пульс покоя): {rhr_val}.
        3. СТАТУС ВОССТАНОВЛЕНИЯ: {rhr_status}.
        4. Погода: {weather_msg}.
        5. План: {plan_txt}.
        
        АЛГОРИТМ РЕШЕНИЯ:
        
        ШАГ 1: ПРОВЕРКА ЗДОРОВЬЯ (Приоритет №1)
        - Если статус "🔴 ОСТОРОЖНО" -> Игнорируй всё, дай команду ОТДЫХАТЬ или сделать совсем легкую растяжку/йогу. Никаких нагрузок.
        - Если статус "🟡 Внимание" -> Снизь интенсивность (только Зона 1-2, без интервалов).
        - Если статус "🟢" -> Работаем по полной.

        ШАГ 2: ВЫБОР ТРЕНИРОВКИ (Если здоровье позволяет)
        - Анализ погоды:
             * Холодно/Ветер/Дождь -> "Indoor Режим" (Станок или Дорожка).
             * Тепло -> "Outdoor Режим" (Вело или Бег на улице).
        
        - Корректировка плана:
             * Если CTL < 10 и Здоровье 🟢 -> Отменяй "Отдых", давай базу (40-60 мин Зона 2).
        
        ФОРМАТ ОТВЕТА:
        ❤️ ЗДОРОВЬЕ: ... (Твой вердикт по пульсу)
        🌤 ПОГОДА: ...
        🚀 ЗАДАНИЕ: ... (Четкая инструкция что делать)
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🩺 COACH V18 (BIO-HACKER):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Critical Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

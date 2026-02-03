import requests
import datetime
import os
import traceback

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 КООРДИНАТЫ (УЖЕ ИСПРАВЛЕНЫ) ---
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

# --- ПОГОДА ---
def get_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url).json()
        
        if 'current_weather' not in res:
            return f"Не удалось получить погоду"
            
        cur = res['current_weather']
        temp = cur.get('temperature')
        wind_s = cur.get('windspeed')
        wind_d = cur.get('winddirection')
        
        # Компас
        dirs = ["С (Север)", "СВ", "В (Восток)", "ЮВ", "Ю (Юг)", "ЮЗ", "З (Запад)", "СЗ"]
        idx = int((wind_d + 22.5) % 360 / 45)
        dir_text = dirs[idx]
        
        return f"🌡 {temp}°C, 💨 Ветер: {wind_s} км/ч, Направление: {dir_text}"
    except Exception as e:
        return f"Ошибка погоды: {e}"

# --- ГЛАВНЫЙ ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=60)).isoformat()
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

        # 3. ПЛАН
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. AI
        prompt = f"""
        Ты велотренер и стратег.
        
        ДАННЫЕ:
        - Фитнес (CTL): {ctl} (База).
        - План: {plan_txt}.
        - ПОГОДА: {weather_msg}.
        
        ТВОЯ ЗАДАЧА:
        1. Если ветер > 20 км/ч, скажи: "Выезжай ПРОТИВ ветра (на [Сторона]), чтобы возвращаться по ветру".
        2. Если холодно или дождь -> "Сегодня Zwift/Беговая дорожка".
        3. Если погода ОК -> "Все на улицу!".
        
        Ответь коротко:
        🌤 ПОГОДА: ...
        🧭 СТРАТЕГИЯ: ...
        🚴 СОВЕТ: ...
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🌪 AERO COACH V16.2:\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

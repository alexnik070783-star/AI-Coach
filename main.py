import requests
import datetime
import os
import traceback

# --- КЛЮЧИ И КООРДИНАТЫ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
# Координаты (если нет в секретах, поставь свои цифры здесь вместо os.environ...)
USER_LAT = os.environ.get("USER_LAT") 
USER_LON = os.environ.get("USER_LON")

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

# --- ПОГОДНЫЙ БЛОК ---
def get_weather():
    if not USER_LAT or not USER_LON:
        return "Нет координат (добавь USER_LAT/USER_LON в Secrets)"
    
    try:
        # Open-Meteo API (Бесплатно, без ключа)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url).json()
        
        if 'current_weather' not in res:
            return "Ошибка погоды"
            
        cur = res['current_weather']
        temp = cur.get('temperature')
        wind_speed = cur.get('windspeed')
        wind_dir = cur.get('winddirection') # Градусы
        
        # Перевод градусов в направление
        directions = ["С (Север)", "СВ (Северо-Восток)", "В (Восток)", "ЮВ (Юго-Восток)", 
                      "Ю (Юг)", "ЮЗ (Юго-Запад)", "З (Запад)", "СЗ (Северо-Запад)"]
        # Формула: (градусы + 22.5) / 45
        idx = int((wind_dir + 22.5) % 360 / 45)
        dir_text = directions[idx]
        
        return f"🌡 {temp}°C, 💨 Ветер: {wind_speed} км/ч ({dir_text})"
    except Exception as e:
        return f"Сбой погоды: {e}"

def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=60)).isoformat()
        end = today.isoformat()
        
        # 1. СБОР ДАННЫХ
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

        # 4. AI ЗАДАЧА
        prompt = f"""
        Ты велотренер-стратег.
        
        ДАННЫЕ:
        - Фитнес (CTL): {ctl} (Базовый уровень).
        - План: {plan_txt}.
        - ПОГОДА ЗА ОКНОМ: {weather_msg}.
        
        ТВОЯ ЗАДАЧА:
        1. Если погода хорошая для улицы (ветер < 25 км/ч, тепло) -> Предложи маршрут.
           ВАЖНО: Посоветуй, куда ехать сначала, чтобы бороться с ветром на свежих ногах.
           (Пример: "Ветер Северный, значит выезжай на Север, чтобы вернуться по ветру").
           
        2. Если погода "нелетная" (сильный ветер > 30 км/ч, холод) -> Рекомендуй Zwift/Бег.
        
        3. Если CTL низкий, но погода супер -> Мотивируй выйти на улицу, это лучшее время для базы.
        
        Будь краток. Формат: "🌤 ПОГОДА / 🚴 ТРЕНИРОВКА / 🧭 СТРАТЕГИЯ ВЕТРА".
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🌪 AERO COACH V16:\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

import requests
import datetime
import os
import json
import traceback

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

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

def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Данные за 60 дней
        start = (today - datetime.timedelta(days=60)).isoformat()
        end = today.isoformat()
        
        # 1. ЗАГРУЗКА ДАННЫХ
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # 2. ПОИСК ФИТНЕСА (CTL)
        ctl = 0.0
        # Ищем последний известный CTL
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break
        
        # Оценка уровня
        level_status = "Новичок/Возврат" if ctl < 20 else "В форме"

        # План из календаря
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 3. AI ЗАДАЧА (МУЛЬТИСПОРТ)
        prompt = f"""
        Ты тренер по триатлону и бегу.
        
        ДАННЫЕ АТЛЕТА:
        - Фитнес (CTL): {ctl} ({level_status}).
        - План в календаре: {plan_txt}.
        
        ТВОЯ ЗАДАЧА:
        Предложи ДВА варианта тренировки на сегодня, чтобы атлет выбрал сам в зависимости от погоды:
        
        1. ВАРИАНТ "УЛИЦА" (Если погода хорошая):
           - Предложи бег или вело на свежем воздухе.
           - Дай конкретное задание (пульс, время).
           
        2. ВАРИАНТ "ДОМ" (Если плохая погода):
           - Предложи велостанок (Zwift) или беговую дорожку.
           - Конкретное задание.
        
        Если CTL низкий (<10), настаивай на том, чтобы сделать ХОТЯ БЫ ОДИН из этих вариантов, даже если в плане отдых. Нам нужна база.
        
        Будь краток. Структура: "☀️ ПОГОДА OK", "🌧 ПОГОДА ПЛОХАЯ".
        Никаких советов про еду.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🏃🚴 COACH V15 (MULTI-SPORT):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

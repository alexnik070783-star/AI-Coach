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
        return f"Ошибка AI: {e}"

def run_coach():
    send_telegram("🧐 V11.0: Ищу данные (даже вчерашние)...")
    
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=42)).isoformat()
        end = today.isoformat()
        
        # Загрузка
        hist = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        raw_curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # --- 1. УМНЫЙ ПОИСК TSB (Ищем не null) ---
        last_valid_day = {}
        if isinstance(hist, list):
            # Перебираем с конца (от сегодня к прошлому)
            for day in reversed(hist):
                if day.get('tsb') is not None:
                    last_valid_day = day
                    break
        
        ctl = last_valid_day.get('ctl', '?')
        tsb = last_valid_day.get('tsb', '?')
        tsb_date = last_valid_day.get('id', 'Неизвестно')
        
        # --- 2. ПЫЛЕСОС МОЩНОСТИ ---
        target_curve = []
        
        # Собираем все кривые в кучу
        all_curves = []
        if isinstance(raw_curves, list):
            all_curves = raw_curves
        elif isinstance(raw_curves, dict):
            all_curves = [raw_curves]
            
        # Ищем любую кривую, где есть точки
        for c in all_curves:
            points = c.get('points', [])
            if points and len(points) > 0:
                target_curve = points
                break # Берем первую попавшуюся с данными
        
        # Считаем ватты
        power_msg = "Профиль мощности: Данных нет (0W)."
        if target_curve:
            def get_w(s):
                # Ищем точку
                p = min([p for p in target_curve if isinstance(p, list)], key=lambda x: abs(x[0]-s), default=None)
                return p[1] if p else 0
            
            p15s = get_w(15)
            p1m = get_w(60)
            p5m = get_w(300)
            p20m = get_w(1200)
            
            if p20m > 0:
                power_msg = f"МОЩНОСТЬ (Спринт/1м/5м/FTP): {p15s}W / {p1m}W / {p5m}W / {p20m}W"

        # План
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # Промпт
        prompt = f"""
        Ты велотренер.
        
        ДАННЫЕ АТЛЕТА (на дату {tsb_date}):
        - TSB (Форма): {tsb} (Если >0 - свеж, если <-10 - устал)
        - CTL (Фитнес): {ctl}
        
        {power_msg}
        
        ПЛАН СЕГОДНЯ: {plan_txt}
        
        ЗАДАЧА:
        1. Если TSB положительный (>0) -> ПРЕДЛОЖИ ТРЕНИРОВКУ. Игнорируй план "Отдых".
           Предложи что-то интересное (например, Sweet Spot или короткие ускорения), раз атлет свеж.
        2. Если TSB сильно в минусе -> Тогда подтверди отдых.
        3. Дай очень краткий комментарий по мощности (какой тип гонщика?).
        
        НИКАКИХ СОВЕТОВ ПО ПИТАНИЮ. Только спорт.
        Без Markdown форматирования.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🚴 COACH V11 🚴\n\n{advice}")

    except Exception as e:
        send_telegram(f"Ошибка: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

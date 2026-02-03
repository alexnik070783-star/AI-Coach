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
    send_telegram("🔍 Ищу данные мощности...")
    
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=42)).isoformat()
        end = today.isoformat()
        
        # Загрузка
        hist = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        raw_curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        last = hist[-1] if (isinstance(hist, list) and hist) else {}
        
        # --- ЛОГИКА ПОИСКА МОЩНОСТИ (ИЩЕМ INDOOR) ---
        target_curve = []
        curve_source = "Нет"
        
        if isinstance(raw_curves, list):
            # 1. Сначала ищем конкретно кривую за последние 42 дня или 84 дня (Currency)
            # 2. Если нет, ищем кривую 'indoor' (Все время)
            # 3. Если нет, берем любую, где есть данные
            
            # Попытка найти самую свежую кривую с данными
            for c in raw_curves:
                points = c.get('points', [])
                if not points: continue
                
                # Приоритет: данные за последние 42-90 дней
                if '42d' in c.get('id', '') or '84d' in c.get('id', ''):
                    target_curve = points
                    curve_source = f"Актуальная ({c['id']})"
                    break
            
            # Если не нашли актуальную, ищем любую Indoor
            if not target_curve:
                for c in raw_curves:
                    if 'indoor' in c.get('id', '').lower() and c.get('points'):
                        target_curve = c['points']
                        curve_source = "Indoor (Все время)"
                        break
            
            # Если всё еще нет, берем самую первую не пустую
            if not target_curve:
                for c in raw_curves:
                    if c.get('points'):
                        target_curve = c['points']
                        curve_source = f"Резервная ({c.get('id')})"
                        break

        # Считаем ватты
        power_msg = f"Профиль мощности ({curve_source}): Данных нет."
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
                power_msg = f"Мощность ({curve_source}):\nSprint(15s): {p15s}W\n1 min: {p1m}W\nVO2(5m): {p5m}W\nFTP(20m): {p20m}W"

        # План
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # Промпт
        prompt = f"""
        Ты велотренер.
        
        ДАННЫЕ АТЛЕТА:
        - TSB (Форма): {last.get('tsb', '?')}
        - Фитнес (CTL): {last.get('ctl', '?')}
        
        {power_msg}
        
        ПЛАН ПО КАЛЕНДАРЮ: {plan_txt}
        
        ТВОЯ ЗАДАЧА:
        1. Если TSB положительный (>0) и атлет свеж -> ПРЕДЛОЖИ ТРЕНИРОВКУ, даже если в плане отдых. Скажи: "Ты свеж, давай покрутим".
        2. Если есть данные мощности -> Проанализируй их. (Например: "У тебя сильный спринт" или "Слабая база 20мин").
        3. Если данных мощности всё равно нет (0W) -> Напиши: "Чтобы я увидел профиль, нужно провести пару заездов с датчиком на станке".
        
        Отвечай без Markdown (без звездочек), просто текст.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🚴 COACH V10 🚴\n\n{advice}")

    except Exception as e:
        send_telegram(f"Ошибка: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

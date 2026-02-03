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
    send_telegram("🧐 V13: Ищу ЛЮБЫЕ данные мощности...")
    
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Ищем далеко назад (60 дней), чтобы найти хоть что-то
        start = (today - datetime.timedelta(days=60)).isoformat()
        end = today.isoformat()
        
        # 1. ЗАГРУЗКА
        activities = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?oldest={start}&newest={end}", auth=auth).json()
        curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()

        # 2. ПОИСК ФИТНЕСА (CTL/TSB)
        ctl, tsb = '?', '?'
        last_date = '?'
        
        # Ищем в Wellness (надежнее для TSB)
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = day.get('ctl')
                    tsb = day.get('tsb')
                    last_date = day.get('id')
                    break
        
        # Если в Wellness пусто, пробуем Activities
        if ctl == '?' and isinstance(activities, list) and len(activities) > 0:
            last_act = sorted(activities, key=lambda x: x['start_date_local'])[-1]
            ctl = last_act.get('icu_ctl') or last_act.get('ctl') or '?'
            tsb = last_act.get('icu_tsb') or '?'
            last_date = last_act['start_date_local'][:10]

        # 3. ПОИСК МОЩНОСТИ (БЕЗ ФИЛЬТРОВ)
        best_curve = []
        max_power = 0
        curve_name = "Нет"
        available_curves = [] # Для отладки

        if isinstance(curves, list):
            for c in curves:
                c_id = c.get('id', 'NoID')
                points = c.get('points', [])
                available_curves.append(c_id)
                
                if not points: continue
                
                # Ищем максимальную мощность на 15 сек (Спринт), чтобы оценить крутизну кривой
                p15 = next((p[1] for p in points if p[0] == 15), 0)
                
                # Берем ту кривую, где спринт мощнее (значит там есть реальные замеры)
                if p15 > max_power:
                    max_power = p15
                    best_curve = points
                    curve_name = c_id

        # Собираем статистику
        if best_curve:
            def get_w(s):
                p = min([p for p in best_curve], key=lambda x: abs(x[0]-s), default=None)
                return p[1] if p else 0
            
            p15s, p1m, p5m, p20m = get_w(15), get_w(60), get_w(300), get_w(1200)
            power_msg = f"МОЩНОСТЬ (Источник: {curve_name}):\n15s: {p15s}W\n1m: {p1m}W\n5m: {p5m}W\n20m: {p20m}W"
        else:
            power_msg = f"МОЩНОСТЬ НЕ НАЙДЕНА.\nЯ видел такие кривые: {', '.join(available_curves)}.\nВсе они пустые."

        # План
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. AI
        prompt = f"""
        Ты велотренер.
        
        ДАННЫЕ АТЛЕТА (актуальны на {last_date}):
        - CTL (Фитнес): {ctl} (Если <10 - начальный уровень/возврат)
        - TSB (Форма): {tsb}
        
        {power_msg}
        
        ПЛАН СЕГОДНЯ: {plan_txt}
        
        ЗАДАЧА:
        1. Оцени форму. Если CTL очень низкий (как сейчас), скажи, что мы строим базу с нуля.
        2. Если TSB позволяет -> Предложи тренировку (Sweet Spot или Base), игнорируя отдых.
        3. Проанализируй мощность (если есть цифры). Скажи, сильный ли спринт или база.
        
        Отвечай текстом.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🚴 COACH V13 🚴\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

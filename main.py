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
    send_telegram("🕵️‍♂️ V12: Сканирую тренировки и кривые...")
    
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Берем данные за 30 дней
        start = (today - datetime.timedelta(days=30)).isoformat()
        end = today.isoformat()
        
        # 1. ЗАГРУЗКА
        # Тренировки (Activities) - самый надежный источник TSB
        activities = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?oldest={start}&newest={end}", auth=auth).json()
        # Здоровье (для сна)
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        # Кривые мощности
        curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        # План
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # 2. ПОИСК ФИТНЕСА (TSB/CTL)
        # Сначала ищем в последней активности (самый точный метод)
        last_ride_stats = "Данных нет"
        ctl, tsb = '?', '?'
        
        if isinstance(activities, list) and len(activities) > 0:
            # Сортируем и берем последнюю
            last_act = activities[0] # API обычно отдает новые первыми, но проверим
            # На всякий случай найдем самую свежую по дате
            last_act = sorted(activities, key=lambda x: x['start_date_local'])[-1]
            
            ctl = last_act.get('icu_ctl') or last_act.get('ctl') or '?'
            tsb = last_act.get('icu_tsb') or '?'
            last_ride_stats = f"Данные из тренировки от {last_act['start_date_local'][:10]}"

        # Если в активностях пусто, пробуем Wellness
        if tsb == '?' and isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('tsb') is not None:
                    tsb = day.get('tsb')
                    ctl = day.get('ctl')
                    last_ride_stats = f"Данные из Wellness от {day['id']}"
                    break

        # 3. ПОИСК МОЩНОСТИ (ПЕРЕБОР ВСЕГО)
        # Мы просто берем кривую с самыми большими цифрами (она скорее всего и есть нужная)
        best_curve = []
        max_watts_found = 0
        curve_name = "Нет"

        if isinstance(curves, list):
            for c in curves:
                points = c.get('points', [])
                if not points: continue
                
                # Ищем 20-минутный пик, чтобы понять, реальная это кривая или мусор
                p20 = next((p[1] for p in points if p[0] == 1200), 0)
                
                # Если эта кривая мощнее предыдущей найденной - берем её
                if p20 > max_watts_found:
                    max_watts_found = p20
                    best_curve = points
                    curve_name = c.get('id', 'Unknown')

        # Формируем отчет по мощности
        power_msg = f"Профиль мощности: Не найден (ID кривых: {[c.get('id') for c in curves] if isinstance(curves, list) else 'Error'})"
        
        if best_curve:
            def get_w(s):
                p = min([p for p in best_curve], key=lambda x: abs(x[0]-s), default=None)
                return p[1] if p else 0
            
            p15s, p1m, p5m, p20m = get_w(15), get_w(60), get_w(300), get_w(1200)
            power_msg = f"МОЩНОСТЬ (источник: {curve_name}):\nSprint(15s): {p15s}W\n1 min: {p1m}W\nVO2(5m): {p5m}W\nFTP(20m): {p20m}W"

        # План
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. AI ЗАДАЧА
        prompt = f"""
        Ты велотренер.
        
        ИСТОЧНИК ДАННЫХ: {last_ride_stats}
        - Фитнес (CTL): {ctl}
        - Форма (TSB): {tsb} (Плюс = свеж, Минус = устал)
        
        {power_msg}
        
        ПЛАН СЕГОДНЯ: {plan_txt}
        
        ТВОЯ ЗАДАЧА:
        1. Проанализируй TSB.
        2. Если TSB > 0 (или близко к нулю) -> ПРЕДЛОЖИ ТРЕНИРОВКУ! Скажи: "Ты свеж, план 'Отдых' отменяем. Давай поработаем". Предложи тему (Sweet Spot или VO2).
        3. Если TSB < -10 -> Подтверди отдых.
        4. Если есть цифры мощности, скажи, какой это тип гонщика (Спринтер? Темповик?).
        
        Отвечай текстом без форматирования.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🚴 COACH V12 🚴\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

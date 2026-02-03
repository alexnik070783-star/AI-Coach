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

# --- ОТПРАВКА (ТОЛЬКО ТЕКСТ) ---
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        # parse_mode='Markdown' убрали, чтобы не было ошибок с жирным шрифтом
        data = {"chat_id": TG_CHAT_ID, "text": text}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# --- AI МОЗГИ ---
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
        
        if res.status_code != 200:
            return f"Ошибка Google AI: {res.text}"
            
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Сбой AI: {e}"

# --- ГЛАВНАЯ ФУНКЦИЯ ---
def run_coach():
    send_telegram("🧐 Анализирую данные...")
    
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Берем данные за 42 дня для контекста
        start = (today - datetime.timedelta(days=42)).isoformat()
        end = today.isoformat()
        
        # 1. Загрузка данных
        # Wellness (Самочувствие)
        hist = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        
        # Power Curves (Кривые мощности)
        raw_curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        
        # Events (План)
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # 2. Обработка данных
        last = hist[-1] if (isinstance(hist, list) and hist) else {}
        
        # Извлекаем кривую (защита от ошибок списка/словаря)
        season_curve = {}
        if isinstance(raw_curves, list) and len(raw_curves) > 0: season_curve = raw_curves[0]
        elif isinstance(raw_curves, dict): season_curve = raw_curves
        
        # Данные мощности
        power_stats = "Нет данных мощности"
        points = season_curve.get('points', [])
        if points:
            # Ищем лучшие ватты за 15с, 1м, 5м, 20м
            def get_w(s): 
                # Берем точку, ближайшую к s секундам
                p = min([p for p in points if isinstance(p, list)], key=lambda x: abs(x[0]-s), default=None)
                return p[1] if p else 0
            
            p15s = get_w(15)
            p1m = get_w(60)
            p5m = get_w(300)
            p20m = get_w(1200)
            power_stats = f"Спринт(15с): {p15s}W, 1мин: {p1m}W, 5мин: {p5m}W, 20мин: {p20m}W"

        # План текстом
        plan_txt = "По календарю: Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 3. ФОРМИРУЕМ ЗАДАЧУ ДЛЯ AI
        prompt = f"""
        Ты элитный велотренер. Твоя задача — анализ формы и рекомендации по тренировке.
        
        ВАЖНО: Игнорируй советы по питанию. Сосредоточься только на велоспорте.
        
        ДАННЫЕ АТЛЕТА СЕГОДНЯ:
        - Фитнес (CTL): {last.get('ctl', '?')}
        - Усталость (ATL): {last.get('atl', '?')}
        - Форма (TSB): {last.get('tsb', '?')} (Если плюс — свежий, минус — уставший)
        - Самочувствие (HRV/Сон): HRV {last.get('hrv', '-')}, Сон {last.get('sleepSecs', 0)/3600:.1f}ч.
        
        ПРОФИЛЬ МОЩНОСТИ (Сезон):
        {power_stats}
        
        ПЛАН ИЗ КАЛЕНДАРЯ:
        {plan_txt}
        
        ИНСТРУКЦИЯ К ДЕЙСТВИЮ:
        1. Проанализируй TSB и ощущения.
        2. ЕСЛИ В ПЛАНЕ "ОТДЫХ", НО TSB ВЫСОКИЙ (атлет свежий) -> Предложи сделать тренировку! Не заставляй отдыхать, если силы есть. Предложи варианты (например, Zone 2 или Intervals).
        3. ЕСЛИ TSB ОЧЕНЬ НИЗКИЙ (<-20) -> Настаивай на отдыхе.
        4. Дай краткий анализ профиля мощности (над чем работать, глядя на цифры).
        
        Ответ пиши коротко, по делу, без "воды".
        """
        
        advice = get_ai_advice(prompt)

        # 4. ОТПРАВКА
        message = f"🚴 COACH ANALYST 🚴\n\n{advice}"
        send_telegram(message)

    except Exception as e:
        err = traceback.format_exc()[-400:]
        send_telegram(f"🔥 ОШИБКА СКРИПТА:\n{err}")

if __name__ == "__main__":
    run_coach()

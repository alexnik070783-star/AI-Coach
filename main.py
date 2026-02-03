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
        
        # 1. ЗАГРУЗКА
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # 2. ПОИСК ФИТНЕСА
        ctl = 0.0
        tsb_status = "Неизвестно"
        
        # Ищем последний известный CTL
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break
        
        # ЛОГИКА "ZERO TO HERO"
        # Если CTL низкий, мы ПРИНУДИТЕЛЬНО считаем атлета свежим
        if ctl < 10:
            tsb_status = "Свеж (CTL низкий, начало сезона)"
            override_rest = True
        else:
            tsb_status = "В рабочем режиме"
            override_rest = False

        # 3. ПОИСК МОЩНОСТИ
        max_power = 0
        has_power_data = False
        
        if isinstance(curves, list):
            for c in curves:
                points = c.get('points', [])
                if points:
                    # Проверяем, есть ли там хоть что-то выше 100 ватт (защита от глюков)
                    p_max = next((p[1] for p in points if p[0] == 15), 0)
                    if p_max > 50:
                        has_power_data = True
                        break
        
        power_instruction = ""
        if not has_power_data:
            power_instruction = "ВАЖНО: Данных мощности НЕТ. Твоя главная задача — заставить атлета сделать тренировку, чтобы собрать данные!"

        # План
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. AI
        prompt = f"""
        Ты жесткий, но справедливый велотренер.
        
        ДАННЫЕ АТЛЕТА:
        - Фитнес (CTL): {ctl} (Это очень низкий уровень, начало с нуля).
        - Статус: {tsb_status}.
        - {power_instruction}
        
        ПЛАН В КАЛЕНДАРЕ: {plan_txt}
        
        ТВОЯ ЗАДАЧА (ПРИОРИТЕТ ВЫСОКИЙ):
        1. Если CTL < 5, ЗАПРЕТИ ОТДЫХАТЬ. Скажи: "Какой отдых? Мы еще не начали!".
        2. Если данных мощности нет, дай задание: "Сделай 45-60 минут в зоне 2 (разговорный темп) или заедь в Zwift, чтобы мы получили первые цифры".
        3. Будь краток и мотивируй начать прямо сейчас.
        
        Никаких советов про еду. Только крутить педали.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"🚀 ТРЕНЕР V14 (РЕЖИМ СТАРТА):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

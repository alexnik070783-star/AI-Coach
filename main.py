import requests
import datetime
import os
import json

# Получаем ключи из "сейфа" GitHub
INTERVALS_ID = os.environ["INTERVALS_ID"]
INTERVALS_API_KEY = os.environ["INTERVALS_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_KEY"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=data)

def get_best_model():
    # Ищем рабочую модель Google
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        data = requests.get(url).json()
        for model in data.get('models', []):
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                return model['name']
    except:
        pass
    return "models/gemini-pro" # Запасной вариант

def run_coach():
    # Определяем время (UTC). В Европе утро ~6-8 UTC, вечер ~20-22 UTC
    now_hour = datetime.datetime.now().hour
    is_morning = now_hour < 12
    
    today = datetime.date.today().isoformat()
    auth = ('API_KEY', INTERVALS_API_KEY)
    
    # Загрузка данных
    try:
        w = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness/{today}", auth=auth).json()
        # Для вечера берем выполненные активности
        activities = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?oldest={today}&newest={today}", auth=auth).json()
        # Для утра берем план
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={today}&newest={today}", auth=auth).json()
    except Exception as e:
        send_telegram(f"❌ Ошибка получения данных: {e}")
        return

    # Формирование контекста
    plan_text = ""
    for item in events:
        if item.get('type') in ['Ride', 'Run', 'Swim', 'Workout']:
            plan_text += f"- План: {item.get('name')}\n"
            
    done_text = ""
    for item in activities:
        # Проверяем, что активность реальная (есть время движения)
        if item.get('moving_time', 0) > 0:
            done_text += f"- Сделано: {item.get('name')} (Load: {item.get('icu_training_load', 0)})\n"

    # Разные промпты для утра и вечера
    if is_morning:
        mode = "УТРО"
        prompt = f"""
        Ты тренер. Сейчас утро ({today}).
        Данные восстановления: HRV {w.get('hrv', 'н/д')}, Пульс {w.get('restingHR', 'н/д')}, Сон {w.get('sleepSecs', 0)/3600:.1f}ч.
        План на сегодня: {plan_text if plan_text else "Отдых"}.
        
        Задача: Оцени готовность и дай настрой на день. Коротко.
        """
    else:
        mode = "ВЕЧЕР"
        prompt = f"""
        Ты тренер. Сейчас вечер ({today}), 22:00.
        План был: {plan_text if plan_text else "Отдых"}.
        По факту выполнено: {done_text if done_text else "Ничего не записано"}.
        Данные дня: Усталость {w.get('soreness', 'н/д')}.
        
        Задача: Подведи итог дня. Если тренировка сделана — похвали. Если пропущена — спроси почему. 
        Напомни про важность сна. Коротко.
        """

    # Запрос к AI
    model_name = get_best_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            # Отправка в Telegram
            message = f"🚴‍♂️ *ОТЧЕТ ТРЕНЕРА ({mode})*\n\n{ai_text}"
            send_telegram(message)
        else:
            send_telegram(f"Ошибка AI: {response.text}")
    except Exception as e:
        send_telegram(f"Сбой скрипта: {e}")

if __name__ == "__main__":
    run_coach()

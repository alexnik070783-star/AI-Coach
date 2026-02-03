import requests
import datetime
import os
import matplotlib.pyplot as plt
import io

# Получаем ключи
INTERVALS_ID = os.environ["INTERVALS_ID"]
INTERVALS_API_KEY = os.environ["INTERVALS_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_KEY"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

# --- ФУНКЦИИ ОТПРАВКИ ---
def send_telegram_photo(caption, photo_file):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    files = {"photo": photo_file}
    requests.post(url, data=data, files=files)

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=data)

# --- РИСОВАНИЕ ГРАФИКОВ ---
def create_wellness_chart(w):
    # Данные для графика
    labels = ['HRV', 'Сон', 'Энергия', 'Настроение']
    
    # Нормализуем данные для красоты (примерно)
    # HRV: берем текущее / 50 (условная норма) * 100
    hrv_val = w.get('hrv', 0) or 0
    hrv_score = min((hrv_val / 60) * 100, 100) # 60ms как база
    
    # Сон: часы / 8 * 100
    sleep_val = (w.get('sleepSecs', 0) or 0) / 3600
    sleep_score = min((sleep_val / 8) * 100, 100)
    
    # Энергия и настроение (1-4) -> в %
    energy_score = (w.get('energy', 0) or 0) * 25
    mood_score = (w.get('mood', 0) or 0) * 25

    values = [hrv_score, sleep_score, energy_score, mood_score]
    colors = ['#4CAF50' if v > 70 else '#FFC107' if v > 40 else '#F44336' for v in values]

    # Рисуем
    plt.figure(figsize=(6, 4))
    bars = plt.bar(labels, values, color=colors)
    plt.title(f"Заряд батарейки: {datetime.date.today()}", fontsize=14)
    plt.ylim(0, 110)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    
    # Добавляем цифры над столбиками
    real_values = [f"{int(hrv_val)}ms", f"{sleep_val:.1f}ч", f"{w.get('energy','-')}/4", f"{w.get('mood','-')}/4"]
    for bar, text in zip(bars, real_values):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, text, 
                 ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Сохраняем в память (буфер)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

# --- ИИ ---
def get_ai_advice(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        # Ищем модель
        models = requests.get(url).json()
        model_name = "models/gemini-1.5-flash" # По умолчанию
        for m in models.get('models', []):
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                model_name = m['name']
                break
        
        # Запрос
        api_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        resp = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return resp.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Ошибка ИИ: {e}"

# --- ГЛАВНАЯ ЛОГИКА ---
def run_coach():
    now_hour = datetime.datetime.now().hour
    is_morning = now_hour < 12
    today = datetime.date.today().isoformat()
    auth = ('API_KEY', INTERVALS_API_KEY)
    
    try:
        w = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness/{today}", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={today}&newest={today}", auth=auth).json()
    except Exception as e:
        send_telegram_text(f"❌ Ошибка данных: {e}")
        return

    # Формируем план текстом
    plan_text = ""
    for item in events:
        if item.get('type') in ['Ride', 'Run', 'Swim', 'Workout']:
            plan_text += f"- {item.get('name')}\n"
            
    if is_morning:
        # 1. Генерируем картинку
        photo = create_wellness_chart(w)
        
        # 2. Генерируем совет
        prompt = f"""
        Ты тренер. Утро ({today}).
        Атлет: HRV {w.get('hrv',0)}, Сон {w.get('sleepSecs',0)/3600:.1f}ч.
        План: {plan_text}.
        Дай короткий, жесткий или хвалебный совет (2 предложения).
        """
        advice = get_ai_advice(prompt)
        
        # 3. Отправляем ФОТО + Текст
        send_telegram_photo(f"📊 *Утренний статус*\n\n{advice}", photo)
        
    else:
        # Вечером пока только текст (можно добавить график выполненной работы позже)
        activities = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?oldest={today}&newest={today}", auth=auth).json()
        done_text = ""
        for act in activities:
            done_text += f"- {act.get('name')} (Load: {act.get('icu_training_load',0)})\n"
            
        prompt = f"""
        Вечер 22:00. План был: {plan_text}. Сделано: {done_text}.
        Подведи итог дня.
        """
        advice = get_ai_advice(prompt)
        send_telegram_text(f"🌙 *Итоги дня*\n\n{advice}")

if __name__ == "__main__":
    run_coach()

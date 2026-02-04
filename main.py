import requests
import datetime
import os
import traceback
import statistics
import matplotlib.pyplot as plt
import io

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 НАСТРОЙКИ ---
USER_LAT = "53.23"       # Несвиж
USER_LON = "26.66"
USER_HEIGHT = 182.0      
USER_BIRTH_YEAR = 1983

def send_telegram(text, photo_buffer=None):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        if photo_buffer:
            photo_buffer.seek(0)
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            files = {'photo': ('chart.png', photo_buffer, 'image/png')}
            data = {'chat_id': TG_CHAT_ID, 'caption': text[:1024]}
            requests.post(url, data=data, files=files)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, 'text': text}
            requests.post(url, json=data)
    except Exception as e:
        print(f"TG Error: {e}")

def get_ai_advice(prompt):
    try:
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        models_url = f"{base_url}/models?key={GOOGLE_API_KEY}"
        data = requests.get(models_url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in data:
            for m in data['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']; break
        gen_url = f"{base_url}/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(gen_url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"AI Error: {e}"

def get_weather():
    try:
        base = "https://api.open-meteo.com/v1/forecast"
        params = f"?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(base + params, timeout=10).json()
        if 'current_weather' not in res: return "Нет погоды"
        cur = res['current_weather']
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч"
    except: return "Ошибка погоды"

# --- 📊 ГРАФИКИ (Только вечером) ---
def generate_charts(wellness_data):
    if not wellness_data or len(wellness_data) < 2: return None
    dates, weights, hrvs = [], [], []
    for day in wellness_data[-14:]:
        dt_str = day.get('id', '')[5:] 
        w = day.get('weight')
        h = day.get('hrv')
        if w: 
            dates.append(dt_str)
            weights.append(float(w))
            hrvs.append(h if h else 0)

    if not dates: return None

    plt.style.use('dark_background')
    fig, ax1 = plt.subplots(figsize=(10, 5))
    color = 'tab:red'
    ax1.set_xlabel('Дата')
    ax1.set_ylabel('Вес (кг)', color=color)
    ax1.plot(dates, weights, color=color, marker='o', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)
    if any(hrvs):
        ax2 = ax1.twinx() 
        color = 'tab:green'
        ax2.set_ylabel('HRV (ms)', color=color)
        ax2.bar(dates, hrvs, color=color, alpha=0.3)
        ax2.tick_params(axis='y', labelcolor=color)
    plt.title('Баланс: Вес vs Стресс (HRV)')
    fig.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# --- ПОЛУЧЕНИЕ ДАННЫХ ---
def get_data(auth, days=14):
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days)).isoformat()
    end = today.isoformat()
    base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
    wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()
    events = requests.get(f"{base_api}/events?oldest={end}&newest={end}", auth=auth).json()
    return wellness, events

# --- 🌅 УТРО: АНАЛИЗ ГОТОВНОСТИ ---
def run_morning(auth, wellness, weather):
    last_day = wellness[-1]
    
    # Метрики
    hrv = last_day.get('hrv')
    rhr = last_day.get('restingHR')
    spo2 = last_day.get('spO2')
    sleep = last_day.get('sleepSecs', 0) / 3600
    
    # Сравнения
    hrv_list = [d.get('hrv') for d in wellness if d.get('hrv')]
    avg_hrv = statistics.mean(hrv_list) if hrv_list else 0
    
    prompt = f"""
    Ты спортивный физиолог. Сейчас 07:00 утра.
    АТЛЕТ: 115+ кг. Задача: Похудение и выносливость.
    
    METRICS:
    - HRV: {hrv} (Обычно {avg_hrv:.0f}).
    - Пульс покоя: {rhr}.
    - SpO2: {spo2}%.
    - Сон: {sleep:.1f} часов.
    - Погода: {weather}.
    
    ЗАДАЧА:
    Ответь ТОЛЬКО на один вопрос: **Можно ли сегодня тренироваться?**
    Если HRV упал или мало спал -> СКАЖИ "ОТДЫХ" или "ЛЕГКАЯ ПРОГУЛКА".
    Если всё ок -> СКАЖИ "МОЖНО ГАЗОВАТЬ".
    Не пиши про еду. Только готовность организма.
    """
    advice = get_ai_advice(prompt)
    send_telegram(f"🌅 УТРЕННИЙ СКАНЕР\n\n{advice}")

# --- 🥗 ОБЕД: КОНТРОЛЬ ПИТАНИЯ ---
def run_lunch(auth, wellness):
    # Данные берем свежие
    last_day = wellness[-1]
    eaten = last_day.get('kcalConsumed') or 0
    
    # Расчет BMR для 115 кг
    bmr = (10 * 115) + (6.25 * 182) - (5 * 41) + 5
    daily_target = bmr * 1.2 # Базовый уровень без спорта (около 2500)
    left = daily_target - eaten
    
    prompt = f"""
    Ты диетолог. Сейчас 14:00 (Обед).
    Атлет (115 кг) уже съел: {eaten} ккал.
    Цель (Базовая): {daily_target:.0f} ккал.
    Осталось на вечер: {left:.0f} ккал.
    
    ЗАДАЧА:
    1. Оцени, много ли съедено к обеду?
    2. Что посоветуешь на УЖИН, чтобы влезть в норму? (Белок? Овощи? Убрать углеводы?)
    Будь краток. Только про еду.
    """
    advice = get_ai_advice(prompt)
    send_telegram(f"🥗 ОБЕДЕННЫЙ КОНТРОЛЬ\n\n{advice}")

# --- 🌙 ВЕЧЕР: ИТОГИ ДНЯ ---
def run_evening(auth, wellness, events, weather):
    # 1. Тренировка
    url = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?limit=1"
    acts = requests.get(url, auth=auth).json()
    act_txt = "Тренировок не было."
    if acts:
        last = acts[0]
        if last.get('start_date_local', '')[:10] == datetime.date.today().isoformat():
            act_type = last.get('type')
            ef = last.get('ef')
            avg_hr = last.get('average_heartrate')
            cad = last.get('average_cadence')
            act_txt = f"{act_type}: Пульс {avg_hr}, Каденс {cad}, EF {ef}."
            if act_type == 'Run' and cad and cad < 150: act_txt += " (ОПАСНО! Низкий каденс)."
            
    # 2. Питание Итого
    last_day = wellness[-1]
    eaten = last_day.get('kcalConsumed') or 0
    burned = last_day.get('kcalActive') or 0
    balance = eaten - (2500 + burned) # Примерный баланс
    
    # 3. Прогноз
    tsb = last_day.get('tsb', 0)
    forecast = "Усталость 📉" if tsb < -20 else "Свежесть 🔋"

    prompt = f"""
    Ты главный тренер. Итоги дня (22:00).
    
    1. ТРЕНИРОВКА: {act_txt}
    2. ПИТАНИЕ: Съел {eaten}, Сжег {burned}. Баланс: {balance:.0f}.
    3. СОСТОЯНИЕ: TSB {tsb}. Прогноз на завтра: {forecast}.
    
    ЗАДАЧА:
    Подведи итог. Хвали, если тренировка была (особенно если каденс ок). Ругай, если переел. Дай установку на сон.
    """
    advice = get_ai_advice(prompt)
    chart = generate_charts(wellness)
    send_telegram(f"🌙 ИТОГИ ДНЯ\n\n{advice}", chart)

# --- ⚙️ ГЛАВНЫЙ МОЗГ ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        wellness, events = get_data(auth)
        weather = get_weather()
        
        # Определяем время (UTC)
        # GitHub Actions: 
        # 04:00 UTC = 07:00 УТРО
        # 11:00 UTC = 14:00 ОБЕД
        # 19:00 UTC = 22:00 ВЕЧЕР
        hour_utc = datetime.datetime.utcnow().hour
        
        if 0 <= hour_utc < 6:
            run_morning(auth, wellness, weather)
        elif 6 <= hour_utc < 15:
            run_lunch(auth, wellness)
        else:
            run_evening(auth, wellness, events, weather)

    except Exception as e:
        send_telegram(f"System Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

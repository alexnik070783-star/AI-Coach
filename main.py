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
USER_BIRTH_YEAR = 1983   # 07.07.1983

# --- 📡 ОТПРАВКА (ТЕКСТ + ФОТО) ---
def send_telegram(text, photo_buffer=None):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        if photo_buffer:
            # Отправка фото с подписью
            photo_buffer.seek(0)
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            files = {'photo': ('chart.png', photo_buffer, 'image/png')}
            data = {'chat_id': TG_CHAT_ID, 'caption': text[:1024]} # Ограничение TG на подпись
            requests.post(url, data=data, files=files)
        else:
            # Просто текст
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, 'text': text}
            requests.post(url, json=data)
    except Exception as e:
        print(f"Ошибка отправки TG: {e}")

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

# --- 📊 ГРАФИКИ (FEATURE #1) ---
def generate_charts(wellness_data):
    if not wellness_data or len(wellness_data) < 5: return None
    
    dates = []
    weights = []
    hrvs = []
    
    # Берем последние 14 дней
    for day in wellness_data[-14:]:
        dt_str = day.get('id', '')[5:] # MM-DD
        w = day.get('weight')
        h = day.get('hrv')
        
        if w: 
            dates.append(dt_str)
            weights.append(float(w))
            hrvs.append(h if h else 0)

    if not dates: return None

    # Рисуем
    plt.style.use('dark_background')
    fig, ax1 = plt.subplots(figsize=(10, 5))
    
    # Вес (Линия)
    color = 'tab:red'
    ax1.set_xlabel('Дата')
    ax1.set_ylabel('Вес (кг)', color=color)
    ax1.plot(dates, weights, color=color, marker='o', linewidth=2, label='Вес')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)

    # HRV (Столбики) - вторая ось
    if any(hrvs):
        ax2 = ax1.twinx() 
        color = 'tab:green'
        ax2.set_ylabel('HRV (ms)', color=color)
        ax2.bar(dates, hrvs, color=color, alpha=0.3, label='HRV')
        ax2.tick_params(axis='y', labelcolor=color)

    plt.title('Динамика: Вес vs HRV (14 дней)')
    fig.tight_layout()
    
    # Сохраняем в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# --- 🚦 ЗОНЫ И МОЩНОСТЬ (FEATURE #3 & #4) ---
def analyze_last_activity(auth, user_id):
    try:
        # Берем последнюю активность
        url = f"https://intervals.icu/api/v1/athlete/{user_id}/activities?limit=1"
        acts = requests.get(url, auth=auth).json()
        if not acts: return "Нет недавних тренировок."
        
        last = acts[0]
        name = last.get('name', 'Тренировка')
        date = last.get('start_date_local', '')[:10]
        
        # Зоны пульса (если есть)
        zones_txt = ""
        icu_zones = last.get('icu_heart_rate_zones') # Массив секунд в зонах
        if icu_zones and len(icu_zones) >= 5:
            total = sum(icu_zones)
            if total > 0:
                z1_2 = (sum(icu_zones[:2]) / total) * 100
                z3 = (icu_zones[2] / total) * 100
                z4_5 = (sum(icu_zones[3:]) / total) * 100
                zones_txt = f"Зоны пульса: Z1-Z2 {z1_2:.0f}%, Z3 (Мусор?) {z3:.0f}%, Z4+ {z4_5:.0f}%."

        # Мощность (eFTP)
        eftp = last.get('icu_eftp')
        power_txt = f"Расчетный FTP (eFTP): {eftp} Вт." if eftp else "eFTP не определен."
        
        return f"Последняя ({date}): {name}. {power_txt} {zones_txt}"
    except:
        return "Ошибка чтения активности."

# --- ФУНКЦИИ АНАЛИЗА ---
def analyze_data(wellness_data, current_age):
    # Питание
    current_weight = 78.0 
    for day in reversed(wellness_data):
        if day.get('weight'):
            current_weight = float(day.get('weight')); break
            
    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * current_age) + 5
    
    if not wellness_data: return "Нет данных", 0, current_weight, "GREEN", 0, 0
    
    last_day = wellness_data[-1]
    eaten = last_day.get('kcalConsumed') or 0
    active_burn = last_day.get('kcalActive') or 0
    daily_need = (bmr * 1.1) + active_burn
    balance = eaten - daily_need
    
    # Биометрика
    tsb = last_day.get('tsb') or 0
    hrv = last_day.get('hrv')
    rhr = last_day.get('restingHR')
    spo2 = last_day.get('spO2')
    
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    avg_hrv = statistics.mean(hrv_list) if hrv_list else 0
    
    # Текст для ИИ
    nutri_txt = f"Съедено {eaten}, Активность {active_burn}, Баланс {balance:.0f}."
    
    bio_txt = f"HRV {hrv} (Среднее {avg_hrv:.0f}), Пульс {rhr}, SpO2 {spo2}%, TSB {tsb}."
    
    return nutri_txt, bio_txt, current_weight, balance, tsb, hrv, avg_hrv

# --- ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=21)).isoformat() # Берем больше дней для графика
        end = today.isoformat()
        
        # Возраст
        is_birthday_passed = (today.month, today.day) >= (7, 7)
        real_age = today.year - USER_BIRTH_YEAR - (0 if is_birthday_passed else 1)
        
        # Данные
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"{base_api}/events?oldest={end}&newest={end}", auth=auth).json()
        weather_msg = get_weather()
        
        # 1. Анализ последней тренировки (Зоны + FTP)
        last_activity_txt = analyze_last_activity(auth, INTERVALS_ID)
        
        # 2. Основной анализ
        nutri, bio, weight, bal, tsb, hrv, avg_hrv = analyze_data(wellness, real_age)
        
        # 3. График
        chart_buffer = generate_charts(wellness)

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # 4. Прогноз ("Батарейка") - Feature #5
        forecast = "Стабильный"
        if tsb < -20 and hrv and hrv < avg_hrv:
            forecast = "📉 ПАДЕНИЕ! Завтра батарейка сядет. Нужен сон."
        elif tsb > 10:
            forecast = "🔋 ПОЛНЫЙ ЗАРЯД. Можно газовать."

        prompt = f"""
        Ты элитный вело-тренер (биохакер).
        
        ДАННЫЕ ({real_age} лет, {weight} кг):
        
        1. 📊 СОСТОЯНИЕ:
           {bio}
           ПРОГНОЗ БАТАРЕЙКИ НА ЗАВТРА: {forecast}
        
        2. 🚴‍♂️ ТРЕНИРОВКИ:
           {last_activity_txt}
           (Если в зонах пульса Z3 > 30% -> ругай за "мусорные мили". Надо либо Z1/Z2, либо Z5).
           (eFTP - это ориентир силы на сегментах).
           
        3. 🥗 ТОПЛИВО:
           {nutri}
           (Баланс: {bal:.0f} ккал).
           
        4. УСЛОВИЯ:
           Погода: {weather_msg}.
           План: {plan_txt}.
        
        ЗАДАЧА:
        1. Проанализируй зоны пульса последней тренировки. Это была база или мусор?
        2. Дай прогноз на завтра (Батарейка).
        3. Скорректируй план с учетом eFTP и TSB.
        
        Формат:
        🔮 ПРОГНОЗ: ...
        🚴‍♂️ АНАЛИЗ ТРЕНИРОВКИ: ... (Зоны, Мощность)
        🧬 ЗДОРОВЬЕ: ...
        🚀 ПЛАН: ...
        """
        
        advice = get_ai_advice(prompt)
        caption = f"📈 V30.0 ULTIMATE\n\n{advice}"
        
        send_telegram(caption, chart_buffer)

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

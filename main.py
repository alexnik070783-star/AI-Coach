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

# --- 📡 ОТПРАВКА ---
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

# --- 📊 ГРАФИКИ ---
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

# --- 🏃‍♂️🚴‍♂️ УМНЫЙ АНАЛИЗ (MULTI-SPORT) ---
def analyze_last_activity(auth, user_id):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{user_id}/activities?limit=1"
        acts = requests.get(url, auth=auth).json()
        if not acts: return "Нет тренировок", "Rest"
        
        last = acts[0]
        name = last.get('name', 'Тренировка')
        atype = last.get('type', 'Activity') # Ride, Run, Walk...
        date = last.get('start_date_local', '')[:10]
        
        # Общие данные
        avg_hr = last.get('average_heartrate')
        max_hr = last.get('max_heartrate')
        ef = last.get('ef')
        rpe = last.get('perceived_exertion')
        feel = last.get('feel')

        stats = []
        stats.append(f"Вид: {atype}")
        if avg_hr: stats.append(f"Пульс: {avg_hr} (Макс {max_hr})")
        if ef: stats.append(f"EF: {ef:.2f}")
        if rpe: stats.append(f"RPE: {rpe}")
        if feel: stats.append(f"Feel: {feel}")

        # --- СПЕЦИФИКА ВЕЛО (Ride, VirtualRide) ---
        if atype in ['Ride', 'VirtualRide']:
            cad = last.get('average_cadence')
            power = last.get('average_watts')
            norm_power = last.get('normalized_power')
            
            if power: stats.append(f"Мощность: {power} Вт (NP {norm_power})")
            if cad: 
                c_txt = f"Каденс: {cad}"
                if cad < 75: c_txt += " (НИЗКИЙ! Ломаешь колени)"
                stats.append(c_txt)
                
        # --- СПЕЦИФИКА БЕГ (Run, Walk) ---
        elif atype in ['Run', 'Walk']:
            cad = last.get('average_cadence') # Intervals обычно шлет SPM (шаги)
            pace = last.get('average_speed') # м/с
            
            # Конвертация темпа
            pace_str = "-"
            if pace:
                mins_per_km = 16.6667 / pace
                pm = int(mins_per_km)
                ps = int((mins_per_km - pm) * 60)
                pace_str = f"{pm}:{ps:02d} /км"
            stats.append(f"Темп: {pace_str}")
            
            # Анализ каденса бега
            if cad:
                # Если гармин шлет пары шагов (58), умножаем на 2 мысленно для анализа
                # Но выводим как есть
                c_txt = f"Каденс: {cad}"
                if cad < 150 and cad > 10: 
                    # Скорее всего это пары шагов (58*2=116) или очень медленный бег
                    c_txt += " (ОПАСНО! Редкие шаги = Ударная нагрузка. Старайся чаще!)"
                stats.append(c_txt)
                
            if avg_hr and avg_hr > 150:
                stats.append("⚠️ ВНИМАНИЕ: Высокий пульс для бега! Переходи на шаг.")

        return f"Последняя ({date}): {name}. " + ", ".join(stats), atype
    except:
        return "Ошибка активности", "Error"

# --- ОБЩИЙ АНАЛИЗ ---
def analyze_data(wellness_data, current_age):
    current_weight = 78.0 
    for day in reversed(wellness_data):
        if day.get('weight'):
            current_weight = float(day.get('weight')); break
            
    bmr = (10 * current_weight) + (6.25 * USER_HEIGHT) - (5 * current_age) + 5
    
    if not wellness_data: return "Нет данных", 0, current_weight, 0, 0, 0
    
    last_day = wellness_data[-1]
    eaten = last_day.get('kcalConsumed') or 0
    active_burn = last_day.get('kcalActive') or 0
    daily_need = (bmr * 1.1) + active_burn
    balance = eaten - daily_need
    
    tsb = last_day.get('tsb') or 0
    hrv = last_day.get('hrv')
    rhr = last_day.get('restingHR')
    spo2 = last_day.get('spO2')
    
    nutri_txt = f"Съедено {eaten}, Расход {active_burn}, Баланс {balance:.0f}."
    bio_txt = f"HRV {hrv}, Пульс {rhr}, SpO2 {spo2}%, TSB {tsb}."
    return nutri_txt, bio_txt, current_weight, balance, tsb, hrv

# --- ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=14)).isoformat()
        end = today.isoformat()
        
        is_birthday_passed = (today.month, today.day) >= (7, 7)
        real_age = today.year - USER_BIRTH_YEAR - (0 if is_birthday_passed else 1)
        
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"{base_api}/events?oldest={end}&newest={end}", auth=auth).json()
        weather_msg = get_weather()
        
        last_act_txt, act_type = analyze_last_activity(auth, INTERVALS_ID)
        nutri, bio, weight, bal, tsb, hrv = analyze_data(wellness, real_age)
        chart_buffer = generate_charts(wellness)

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        forecast = "Нейтральный"
        if tsb < -20: forecast = "📉 Усталость."
        elif tsb > 10: forecast = "🔋 Свежесть."

        prompt = f"""
        Ты элитный тренер по триатлону и биохакер.
        ДАННЫЕ АТЛЕТА: {real_age} лет, вес {weight} кг.
        
        1. 📊 СОСТОЯНИЕ:
           {bio} (ПРОГНОЗ: {forecast})
        
        2. 🏃‍♂️🚴‍♂️ ПОСЛЕДНЯЯ ТРЕНИРОВКА ({act_type}):
           {last_act_txt}
           
           ПРАВИЛА АНАЛИЗА:
           - Если это ВЕЛО (Ride): Ругай за каденс < 75. Хвали за EF > 1.1.
           - Если это БЕГ (Run): КРИТИЧЕСКИ ВАЖНО для веса 100кг+! 
             Если каденс < 150 (или < 75 пар), напиши: "Ты втыкаешься в асфальт! Убьешь колени. Делай мелкие частые шаги!".
             Если пульс > 150 при низком темпе, напиши: "Сердце на пределе! Переходи на шаг, бегать рано!".
        
        3. 🥗 ТОПЛИВО: {nutri}
        4. УСЛОВИЯ: {weather_msg}. ПЛАН: {plan_txt}.
        
        ЗАДАЧА:
        Дай жесткий, но заботливый совет. Если была беговая тренировка с плохими показателями - категорически запрети бегать быстро.
        """
        
        advice = get_ai_advice(prompt)
        caption = f"🤖 V33.0 MULTI-SPORT\n\n{advice}"
        
        send_telegram(caption, chart_buffer)

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

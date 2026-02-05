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
USER_LAT = "53.23"       
USER_LON = "26.66"
USER_HEIGHT = 182.0      
USER_BIRTH_YEAR = 1983

# --- 📡 ОТПРАВКА (С ЛОГАМИ) ---
def send_telegram(text, photo_buffer=None):
    print(f"📤 Пытаюсь отправить в Telegram: {text[:50]}...")
    if not TG_TOKEN or not TG_CHAT_ID: 
        print("❌ ОШИБКА: Нет TG_TOKEN или TG_CHAT_ID в Secrets!")
        return
    try:
        if photo_buffer:
            photo_buffer.seek(0)
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            files = {'photo': ('chart.png', photo_buffer, 'image/png')}
            data = {'chat_id': TG_CHAT_ID, 'caption': text[:1024]}
            res = requests.post(url, data=data, files=files)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {"chat_id": TG_CHAT_ID, 'text': text}
            res = requests.post(url, json=data)
        
        if res.status_code != 200:
            print(f"❌ Telegram API Error: {res.text}")
        else:
            print("✅ Сообщение отправлено успешно.")
            
    except Exception as e:
        print(f"❌ Ошибка отправки TG: {e}")

def get_ai_advice(prompt):
    try:
        if not GOOGLE_API_KEY: return "Ошибка: Нет GOOGLE_KEY."
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

# --- БЕЗОПАСНЫЙ ЗАПРОС ---
def safe_api_get(url, auth):
    try:
        res = requests.get(url, auth=auth)
        if res.status_code != 200:
            print(f"⚠️ API Error {res.status_code}: {res.text[:100]}")
            return []
        data = res.json()
        if isinstance(data, list): return data
        return [] 
    except Exception as e:
        print(f"⚠️ Request Error: {e}")
        return []

def get_data(auth, days=21):
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days)).isoformat()
    end = today.isoformat()
    base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
    
    print("Запрос данных wellness...")
    wellness = safe_api_get(f"{base_api}/wellness?oldest={start}&newest={end}", auth)
    
    print("Запрос данных events...")
    events = safe_api_get(f"{base_api}/events?oldest={end}&newest={end}", auth)
    
    return wellness, events

# --- 🛡 БЕЗОПАСНОСТЬ ---
def check_safety_triggers(wellness_data):
    if not wellness_data or len(wellness_data) < 2: return {}
    last = wellness_data[-1]
    prev = wellness_data[-2]
    
    water_alert = ""
    w_today = last.get('weight')
    w_prev = prev.get('weight')
    if w_today and w_prev and (float(w_today) > float(w_prev) + 1.2):
        water_alert = f"⚠️ Вес +{float(w_today)-float(w_prev):.1f} кг! Это вода."

    virus_alert = ""
    hrv = last.get('hrv')
    rhr = last.get('restingHR')
    hrv_list = [d.get('hrv') for d in wellness_data[:-1] if d.get('hrv')]
    rhr_list = [d.get('restingHR') for d in wellness_data[:-1] if d.get('restingHR')]
    if hrv and rhr and hrv_list and rhr_list:
        avg_hrv = statistics.mean(hrv_list)
        avg_rhr = statistics.mean(rhr_list)
        if (hrv < avg_hrv * 0.8) and (rhr > avg_rhr * 1.05):
            virus_alert = "⛔️ ТРЕВОГА: HRV упал, пульс вырос. Похоже на вирус!"

    ramp_alert = ""
    atl_today = last.get('atl') or 0
    atl_last = wellness_data[-8].get('atl') if len(wellness_data) > 8 else 0
    if atl_last > 10 and atl_today > atl_last * 1.3:
        ramp_alert = "🛑 ОПАСНО: Нагрузка выросла >30% за неделю."

    return {"water": water_alert, "virus": virus_alert, "ramp": ramp_alert}

# --- 🌅 УТРО ---
def run_morning(auth, wellness, weather):
    if not wellness:
        send_telegram("🌅 Утро: Данных wellness нет (пустой список). Проверь синхронизацию.")
        return

    last_day = wellness[-1]
    hrv = last_day.get('hrv')
    rhr = last_day.get('restingHR')
    sleep = last_day.get('sleepSecs', 0)/3600
    alerts = check_safety_triggers(wellness)
    safety_msg = "\n".join([v for k,v in alerts.items() if v and k != 'ramp'])
    
    prompt = f"""
    Физиолог. 07:00. Атлет 115 кг.
    HRV {hrv}, Пульс {rhr}, Сон {sleep:.1f}ч.
    АЛЕРТЫ: {safety_msg}
    Можно тренить?
    """
    advice = get_ai_advice(prompt)
    caption = "🌅 УТРО"
    if alerts.get('virus'): caption += " ⛔️"
    send_telegram(f"{caption}\n\n{advice}")

# --- 🥗 ОБЕД ---
def run_lunch(auth, wellness):
    if not wellness:
        send_telegram("🥗 Обед: Нет данных wellness.")
        return
        
    eaten = wellness[-1].get('kcalConsumed') or 0
    bmr = (10*115) + (6.25*182) - (5*41) + 5
    left = (bmr * 1.2) - eaten
    prompt = f"Диетолог. 14:00. Съел {eaten}. Остаток {left:.0f}. Совет на ужин?"
    send_telegram(f"🥗 ОБЕД\n\n{get_ai_advice(prompt)}")

# --- 🌙 ВЕЧЕР ---
def run_evening(auth, wellness, events, weather):
    if not wellness:
        send_telegram("🌙 Вечер: Нет данных wellness для отчета.")
        return

    today_iso = datetime.date.today().isoformat()
    
    # 1. Тренировка
    url = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities?limit=1"
    acts = safe_api_get(url, auth)
    
    act_txt = "Отдых"
    if acts and acts[0].get('start_date_local', '')[:10] == today_iso:
        l = acts[0]
        act_txt = f"{l.get('type')}: EF {l.get('ef')}, Cad {l.get('average_cadence')}"

    # 2. Безопасность
    alerts = check_safety_triggers(wellness)
    
    # 3. Данные дня
    last = wellness[-1]
    bal = (last.get('kcalConsumed') or 0) - (2500 + (last.get('kcalActive') or 0))
    tsb = last.get('tsb', 0)
    
    # 4. Стратегия
    strategic_report = ""
    if datetime.datetime.today().weekday() == 6:
        start_90 = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        acts_90 = safe_api_get(f"{base_api}/activities?oldest={start_90}&newest={today_iso}", auth)
        well_90 = safe_api_get(f"{base_api}/wellness?oldest={start_90}&newest={today_iso}", auth)
        
        if acts_90 and well_90:
            total_acts = len(acts_90)
            discipline = (total_acts / 39) * 100 
            w_start = next((d['weight'] for d in well_90 if d.get('weight')), 0)
            w_end = next((d['weight'] for d in reversed(well_90) if d.get('weight')), 0)
            w_delta = float(w_end) - float(w_start) if w_start and w_end else 0
            strategic_report = f"📊 КВАРТАЛ: Тренировок {total_acts} ({discipline:.0f}%), Вес {w_delta:+.1f} кг"

    prompt = f"""
    Тренер. 22:00.
    ТРЕНИРОВКА: {act_txt}
    БАЛАНС: {bal:.0f} ккал. TSB: {tsb}.
    {strategic_report}
    Итог дня.
    """
    
    advice = get_ai_advice(prompt)
    chart = generate_charts(wellness)
    caption = "🌙 ИТОГИ"
    if strategic_report: caption += " + 📊"
    
    send_telegram(f"{caption}\n\n{advice}", chart)

# --- ЗАПУСК ---
def run_coach():
    print("🚀 Start Coach V38.0...")
    try:
        if not TG_TOKEN:
            print("❌ ОШИБКА: TG_TOKEN не найден!")
            return

        auth = ('API_KEY', INTERVALS_API_KEY)
        wellness, events = get_data(auth)
        weather = get_weather()
        
        h = datetime.datetime.utcnow().hour
        print(f"🕒 Время UTC: {h}")
        
        if 0 <= h < 6: 
            print("Режим: УТРО")
            run_morning(auth, wellness, weather)
        elif 6 <= h < 15: 
            print("Режим: ОБЕД")
            run_lunch(auth, wellness)
        else: 
            print("Режим: ВЕЧЕР")
            run_evening(auth, wellness, events, weather)
            
    except Exception as e:
        err_msg = f"Global Error: {traceback.format_exc()}"
        print(err_msg)
        send_telegram(err_msg[-300:])

if __name__ == "__main__":
    run_coach()

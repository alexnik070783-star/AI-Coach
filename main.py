import requests
import datetime
import os
import traceback
import statistics

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 🌍 КООРДИНАТЫ (НЕСВИЖ) ---
USER_LAT = "53.23"
USER_LON = "26.66"

# --- ФУНКЦИИ ---
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

def get_weather():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={USER_LAT}&longitude={USER_LON}&current_weather=true&windspeed_unit=kmh"
        res = requests.get(url, timeout=10).json()
        if 'current_weather' not in res: return "Нет погоды"
        cur = res['current_weather']
        dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
        idx = int((cur.get('winddirection') + 22.5) % 360 / 45)
        return f"{cur.get('temperature')}°C, Ветер {cur.get('windspeed')} км/ч ({dirs[idx]})"
    except Exception as e:
        return f"Погода: {str(e)}"

# --- 💤 DEEP SLEEP & HRV ANALYSIS ---
def analyze_neuro(wellness_data):
    if not isinstance(wellness_data, list) or len(wellness_data) < 2:
        return "Мало данных для анализа (нужна неделя).", "GRAY"
    
    # 1. Извлекаем списки (фильтруем None)
    hrv_list = [d.get('hrv') for d in wellness_data if d.get('hrv')]
    sleep_time_list = [d.get('sleepSecs') for d in wellness_data if d.get('sleepSecs')]
    sleep_score_list = [d.get('sleepScore') for d in wellness_data if d.get('sleepScore')]

    # Берем "Сегодня" (последний элемент)
    today_hrv = hrv_list[-1] if hrv_list else None
    today_time = sleep_time_list[-1] if sleep_time_list else None
    today_score = sleep_score_list[-1] if sleep_score_list else None

    report_lines = []
    overall_status = "GREEN"

    # --- АНАЛИЗ HRV ---
    if today_hrv and len(hrv_list) > 3:
        avg_hrv = statistics.mean(hrv_list[:-1])
        diff_pct = ((today_hrv - avg_hrv) / avg_hrv) * 100
        
        icon = "🟢"
        if diff_pct < -10: 
            icon, overall_status = "🔴", "RED"
        elif diff_pct < -5: 
            icon = "🟡"
            if overall_status != "RED": overall_status = "YELLOW"
            
        report_lines.append(f"• HRV: {today_hrv:.0f}ms (Ср: {avg_hrv:.0f}) -> {icon} {diff_pct:+.1f}%")
    else:
        report_lines.append(f"• HRV: {today_hrv if today_hrv else 'Нет'}")

    # --- АНАЛИЗ ВРЕМЕНИ СНА (Time) ---
    if today_time and len(sleep_time_list) > 3:
        avg_time = statistics.mean(sleep_time_list[:-1])
        diff_pct = ((today_time - avg_time) / avg_time) * 100
        
        # Форматируем в часы:минуты
        def to_hm(secs): return f"{int(secs//3600)}ч{int((secs%3600)//60)}м"
        
        icon = "🟢"
        if diff_pct < -15: # Спал на 15% меньше обычного
            icon, overall_status = "🔴", "RED"
        elif diff_pct < -10:
            icon = "🟡"
            if overall_status != "RED": overall_status = "YELLOW"
            
        report_lines.append(f"• Сон (Время): {to_hm(today_time)} (Ср: {to_hm(avg_time)}) -> {icon}")
    else:
        report_lines.append(f"• Сон (Время): Нет данных")

    # --- АНАЛИЗ КАЧЕСТВА СНА (Score) ---
    if today_score and len(sleep_score_list) > 3:
        avg_score = statistics.mean(sleep_score_list[:-1])
        diff = today_score - avg_score
        
        icon = "🟢"
        if diff < -10: # Оценка упала на 10 пунктов
            icon, overall_status = "🔴", "RED"
        elif diff < -5:
            icon = "🟡"
            if overall_status != "RED": overall_status = "YELLOW"

        report_lines.append(f"• Сон (Оценка): {today_score:.0f} (Ср: {avg_score:.0f}) -> {icon}")
    else:
         # Если оценки нет, не пишем ошибку, просто пропускаем или пишем 'Нет'
         if today_score: report_lines.append(f"• Сон (Оценка): {today_score}")

    return "\n".join(report_lines), overall_status

# --- ГЛАВНЫЙ ЗАПУСК ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        # Берем 14 дней для статистики
        start = (today - datetime.timedelta(days=14)).isoformat()
        end = today.isoformat()
        
        wellness = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()
        weather_msg = get_weather()

        ctl = 0.0
        if isinstance(wellness, list):
            for day in reversed(wellness):
                if day.get('ctl') is not None:
                    ctl = float(day.get('ctl'))
                    break

        # БИОМЕТРИКА V20
        bio_text, bio_status = analyze_neuro(wellness)

        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        prompt = f"""
        Ты тренер-биохакер.
        
        ДАННЫЕ АТЛЕТА:
        1. Фитнес (CTL): {ctl:.1f}.
        2. АНАЛИЗ ВОССТАНОВЛЕНИЯ (Сравнение со средним за неделю):
        {bio_text}
        (Общий статус системы: {bio_status})
        3. ПОГОДА (Несвиж): {weather_msg}.
        4. ПЛАН: {plan_txt}.
        
        АЛГОРИТМ РЕШЕНИЯ:
        1. ОЦЕНКА БИОМЕТРИКИ:
           - Если Статус RED (Упал сон или HRV) -> Организм не восстановился. Снижай нагрузку или давай полный отдых.
           - Если Статус YELLOW -> Аккуратно.
           - Если Статус GREEN -> Можно работать.

        2. ТРЕНИРОВКА:
           - Погода Плохая -> Indoor.
           - Если биометрика GREEN и CTL < 10 -> Отменяй отдых, давай базу.
           
        Ответь:
        🧬 БИОМЕТРИКА: ... (Краткий анализ сна и HRV)
        🌤 ПОГОДА: ...
        🚀 ВЕРДИКТ: ... (Задание)
        """
        
        advice = get_ai_advice(prompt)
        send_telegram(f"💤 COACH V20 (SLEEP ANALYTICS):\n\n{advice}")

    except Exception as e:
        send_telegram(f"Error: {traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

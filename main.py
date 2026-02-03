import requests
import datetime
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
import math

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ["INTERVALS_ID"]
INTERVALS_API_KEY = os.environ["INTERVALS_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_KEY"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

# --- НАСТРОЙКИ ГРАФИКОВ ---
plt.style.use('bmh') # Стиль, похожий на Intervals

def send_telegram_photo(caption, photo_file):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    files = {"photo": photo_file}
    requests.post(url, data=data, files=files)

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=data)

# --- ГЕНЕРАЦИЯ СЛОЖНЫХ ГРАФИКОВ ---
def create_pro_charts(history_data, power_curve_data):
    # Создаем картинку с 2 графиками
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
    plt.subplots_adjust(hspace=0.3)

    # === ГРАФИК 1: ФИТНЕС / УСТАЛОСТЬ (42 дня) ===
    dates = []
    ctl = [] # Fitness (Blue)
    atl = [] # Fatigue (Purple)
    tsb = [] # Form (Grey/Orange)

    for day in history_data:
        d = datetime.date.fromisoformat(day['id'])
        dates.append(d)
        ctl.append(day.get('ctl', 0))
        atl.append(day.get('atl', 0))
        tsb.append(day.get('tsb', 0))

    # Рисуем линии как на Intervals.icu
    ax1.plot(dates, ctl, color='#03A9F4', linewidth=2, label='Fitness (CTL)') # Голубой
    ax1.plot(dates, atl, color='#9C27B0', linewidth=1, label='Fatigue (ATL)', alpha=0.7) # Фиолетовый
    
    # Закрашиваем зоны TSB
    ax1.fill_between(dates, tsb, 0, where=[t >= 0 for t in tsb], color='#4CAF50', alpha=0.3, label='Fresh (+)')
    ax1.fill_between(dates, tsb, 0, where=[t < 0 for t in tsb], color='#FF9800', alpha=0.3, label='Tired (-)')
    
    # Добавляем серую линию TSB
    ax1.plot(dates, tsb, color='gray', linewidth=1, linestyle='--')

    ax1.set_title("Динамика формы (42 дня)", fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend(loc='upper left', fontsize=8)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))

    # === ГРАФИК 2: КРИВАЯ МОЩНОСТИ (Power Curve) ===
    # Данные приходят в формате [[secs, watts], [secs, watts]...]
    points = power_curve_data.get('points', [])
    
    if points:
        secs = [p[0] for p in points if p[0] <= 7200] # Берем до 2 часов (7200 сек)
        watts = [p[1] for p in points if p[0] <= 7200]
        
        # Логарифмическая шкала для оси X (как в Intervals)
        ax2.set_xscale('log')
        ax2.plot(secs, watts, color='#E91E63', linewidth=2) # Розовая линия
        
        ax2.set_title("Кривая мощности (Сезон)", fontsize=12, fontweight='bold')
        ax2.set_ylabel("Ватты (W)")
        ax2.grid(True, which="both", ls="-", alpha=0.2)

        # Подписываем ключевые точки (15s, 1m, 5m, 20m)
        key_durations = {15: "15s", 60: "1m", 300: "5m", 1200: "20m"}
        
        for dur, label in key_durations.items():
            # Ищем ближайшее значение в данных
            closest_p = min(points, key=lambda x: abs(x[0] - dur))
            w = closest_p[1]
            # Ставим точку и текст
            ax2.scatter(dur, w, color='black', zorder=5)
            ax2.annotate(f"{label}\n{w}W", (dur, w), xytext=(0, 10), textcoords='offset points', ha='center', fontweight='bold')
            
        # Настройка подписей оси X (чтобы было красиво)
        ax2.set_xticks([15, 60, 300, 1200, 3600])
        ax2.set_xticklabels(["15s", "1m", "5m", "20m", "1h"])
    else:
        ax2.text(0.5, 0.5, "Нет данных Power Curve", ha='center')

    # Сохраняем
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    buf.seek(0)
    plt.close()
    return buf

# --- ИИ ---
def get_ai_advice(prompt):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        data = requests.get(url).json()
        model_name = "models/gemini-1.5-flash"
        for m in data.get('models', []):
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                model_name = m['name']
                break
        
        api_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        resp = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return resp.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Ошибка ИИ: {e}"

# --- ГЛАВНАЯ ЛОГИКА ---
def run_coach():
    today = datetime.date.today()
    auth = ('API_KEY', INTERVALS_API_KEY)
    
    # 1. Данные для Fitness графика (последние 42 дня)
    start_date = (today - datetime.timedelta(days=42)).isoformat()
    end_date = today.isoformat()
    
    try:
        print("Загружаю историю wellness...")
        history = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start_date}&newest={end_date}", auth=auth).json()
        
        print("Загружаю Power Curve...")
        # Запрашиваем кривые
        curves_resp = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        # Ищем кривую текущего сезона (или последнюю доступную)
        season_curve = {}
        for c in curves_resp:
            # Обычно первая кривая самая актуальная, или ищем по id
            season_curve = c
            break
            
        # План на сегодня
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end_date}&newest={end_date}", auth=auth).json()
        
    except Exception as e:
        send_telegram_text(f"❌ Ошибка получения данных: {e}")
        return

    # Извлекаем ключевые цифры мощности для ИИ
    power_stats = "Нет данных мощности."
    points = season_curve.get('points', [])
    if points:
        # Функция поиска ватт по секундам
        def get_watts(s):
            val = min(points, key=lambda x: abs(x[0] - s))
            return val[1]
        
        p_15s = get_watts(15)
        p_1m = get_watts(60)
        p_5m = get_watts(300)
        p_20m = get_watts(1200)
        p_eftp = history[-1].get('eftp', 'н/д')
        
        power_stats = f"Спринт (15с): {p_15s}W\n1 мин: {p_1m}W\nVo2Max (5 мин): {p_5m}W\nFTP (20 мин): {p_20m}W\nТекущий eFTP: {p_eftp}W"

    # Текст плана
    plan_text = ""
    for item in events:
        if item.get('type') in ['Ride', 'Run', 'Swim', 'Workout']:
            plan_text += f"- {item.get('name')}\n"
    if not plan_text: plan_text = "Отдых"

    # Время суток
    is_morning = datetime.datetime.now().hour < 12

    if is_morning:
        # Генерируем картинку
        photo = create_pro_charts(history, season_curve)
        
        # Данные последнего дня
        last = history[-1]
        
        prompt = f"""
        Ты аналитик велоспорта.
        
        ДАННЫЕ АТЛЕТА:
        1. Фитнес (CTL): {last.get('ctl')}
        2. Форма (TSB): {last.get('tsb')} (Если минус — устал, если плюс — свеж)
        
        МОЩНОСТЬ (Сезон):
        {power_stats}
        
        ПЛАН НА СЕГОДНЯ:
        {plan_text}
        
        ЗАДАЧА:
        Проанализируй цифры. 
        1. Оцени профиль мощности (спринтер, темповик или горняк?).
        2. Дай совет по сегодняшней тренировке с учетом TSB и eFTP.
        """
        
        advice = get_ai_advice(prompt)
        send_telegram_photo(f"🚴‍♂️ *Pro Аналитика*\n\n{advice}", photo)
    
    else:
        send_telegram_text("🌙 День окончен. Данные обновлены.")

if __name__ == "__main__":
    run_coach()

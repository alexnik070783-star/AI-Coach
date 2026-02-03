import requests
import datetime
import os
import io
import traceback

# --- 1. ГРАФИКА ---
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- ОТПРАВКА ---
def send_telegram_photo(caption, photo_file):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
        files = {"photo": photo_file}
        requests.post(url, data=data, files=files)
    except Exception as e:
        print(f"Error sending photo: {e}")

def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=data)
    except Exception as e:
        print(f"Error sending text: {e}")

# --- ГРАФИКИ (ВЕС + ФОРМА) ---
def create_charts(history_data, power_curve_data):
    if not history_data or not isinstance(history_data, list): return None

    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
    plt.subplots_adjust(hspace=0.3)

    # === ГРАФИК 1: ФОРМА + ВЕС ===
    dates, ctl, tsb, weight = [], [], [], []
    
    clean_hist = [d for d in history_data if isinstance(d, dict) and 'id' in d]
    
    for day in sorted(clean_hist, key=lambda x: x['id']):
        dates.append(datetime.date.fromisoformat(day['id']))
        ctl.append(day.get('ctl', 0))
        tsb.append(day.get('tsb', 0))
        # Если веса нет, берем None, чтобы график не падал в ноль
        w = day.get('weight', None)
        weight.append(w)

    # Ось 1 (Слева): Фитнес (CTL)
    ax1.plot(dates, ctl, color='#2196F3', linewidth=2, label='Fitness (CTL)')
    ax1.fill_between(dates, tsb, 0, where=[t >= 0 for t in tsb], color='green', alpha=0.2, label='Fresh')
    ax1.fill_between(dates, tsb, 0, where=[t < 0 for t in tsb], color='orange', alpha=0.2, label='Tired')
    
    ax1.set_title("Fitness & Weight Trend", fontsize=12)
    ax1.set_ylabel("Fitness / Form")
    ax1.legend(loc='upper left')

    # Ось 2 (Справа): ВЕС (Красная линия)
    # Рисуем только если есть данные веса
    if any(w is not None for w in weight):
        ax1_right = ax1.twinx()
        # Фильтруем None для красивой линии
        valid_dates = [d for d, w in zip(dates, weight) if w is not None]
        valid_weight = [w for w in weight if w is not None]
        
        ax1_right.plot(valid_dates, valid_weight, color='#D32F2F', linewidth=2, linestyle='--', label='Weight (kg)')
        ax1_right.set_ylabel("Weight (kg)", color='#D32F2F')
        ax1_right.tick_params(axis='y', labelcolor='#D32F2F')
        # Легенду веса добавляем вручную или просто подписываем ось

    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))

    # === ГРАФИК 2: МОЩНОСТЬ ===
    points = []
    if isinstance(power_curve_data, dict):
        points = power_curve_data.get('points', [])
    
    if points:
        valid = [p for p in points if isinstance(p, list) and len(p)>=2 and p[0] <= 7200 and p[1] > 0]
        if valid:
            secs = [p[0] for p in valid]
            watts = [p[1] for p in valid]
            ax2.set_xscale('log')
            ax2.plot(secs, watts, color='#E91E63', linewidth=2)
            ax2.set_title("Season Power Curve", fontsize=12)
            
            targets = {15: "15s", 60: "1m", 300: "5m", 1200: "20m"}
            for d, l in targets.items():
                closest = min(valid, key=lambda x: abs(x[0]-d))
                ax2.annotate(f"{l}\n{closest[1]}W", (closest[0], closest[1]), 
                             xytext=(0,10), textcoords='offset points', ha='center', fontweight='bold')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

# --- AI ---
def get_ai_advice(prompt):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        models = requests.get(url).json()
        model = "models/gemini-1.5-flash"
        if 'models' in models:
            for m in models['models']:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model = m['name']; break
        
        api = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GOOGLE_API_KEY}"
        res = requests.post(api, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"AI error: {e}"

# --- MAIN ---
def run_coach():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=42)).isoformat()
        end = today.isoformat()
        
        # Загрузка
        hist = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/wellness?oldest={start}&newest={end}", auth=auth).json()
        raw_curves = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/power-curves", auth=auth).json()
        events = requests.get(f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/events?oldest={end}&newest={end}", auth=auth).json()

        # Данные кривой мощности
        season_curve = {}
        if isinstance(raw_curves, list) and len(raw_curves) > 0: season_curve = raw_curves[0]
        elif isinstance(raw_curves, dict): season_curve = raw_curves

        # План текстом
        plan_txt = "Отдых"
        if isinstance(events, list):
            plans = [e['name'] for e in events if e.get('type') in ['Ride','Run','Swim','Workout']]
            if plans: plan_txt = ", ".join(plans)

        # Графики
        photo = None
        try:
            photo = create_charts(hist, season_curve)
        except Exception as e:
            print(f"Chart fail: {e}")

        # --- СБОР ДАННЫХ ДЛЯ ДИЕТОЛОГА ---
        last = hist[-1] if (isinstance(hist, list) and hist) else {}
        
        # Ищем вес сегодня и 42 дня назад
        current_weight = last.get('weight', None)
        start_weight = None
        if isinstance(hist, list) and len(hist) > 0:
            start_weight = hist[0].get('weight', None)
        
        weight_msg = "Вес не указан."
        if current_weight:
            weight_msg = f"Текущий вес: {current_weight}kg."
            if start_weight:
                diff = current_weight - start_weight
                weight_msg += f" (Изменение за 6 недель: {diff:+.1f}kg)."

        # Промпт Диетолога
        prompt = f"""
        Ты велотренер и нутрициолог.
        
        ДАННЫЕ АТЛЕТА:
        - Fitness (CTL): {last.get('ctl','?')}
        - Form (TSB): {last.get('tsb','?')}
        - {weight_msg}
        
        ПЛАН НА СЕГОДНЯ:
        {plan_txt}
        
        ЗАДАЧА:
        1. Оцени тренировочную нагрузку.
        2. Если вес растет или стоит — дай совет по питанию (углеводы/белки).
        3. Если вес падает слишком быстро — предупреди о потере мощности.
        Будь краток и конкретен.
        """
        advice = get_ai_advice(prompt)

        # Отправка
        caption = f"🥗 *Coach & Diet*\n\n{advice}"
        if photo:
            send_telegram_photo(caption, photo)
        else:
            send_telegram_text(caption)

    except Exception as e:
        send_telegram_text(f"🔥 ERROR:\n{traceback.format_exc()[-300:]}")

if __name__ == "__main__":
    run_coach()

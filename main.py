import requests
import datetime
import os
import statistics

# --- КЛЮЧИ ---
INTERVALS_ID = os.environ.get("INTERVALS_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# --- 📡 ОТПРАВКА ---
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {"chat_id": TG_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
        requests.post(url, json=data)
    except Exception as e:
        print(f"TG Error: {e}")

# --- 🕵️‍♂️ АУДИТ (ГЛАВНАЯ ФУНКЦИЯ) ---
def run_audit():
    try:
        auth = ('API_KEY', INTERVALS_API_KEY)
        
        # 1. Берем данные за 90 дней (Квартал)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=90)).isoformat()
        end = today.isoformat()
        
        base_api = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}"
        
        print(f"Скачиваю архив с {start} по {end}...")
        
        # Загружаем активности
        activities = requests.get(f"{base_api}/activities?oldest={start}&newest={end}", auth=auth).json()
        # Загружаем здоровье (вес)
        wellness = requests.get(f"{base_api}/wellness?oldest={start}&newest={end}", auth=auth).json()

        if not activities:
            send_telegram("❌ В архиве за 90 дней пусто. Возможно, проблема с датами или ключами.")
            return

        # --- АНАЛИЗ 1: ОБЪЕМЫ ---
        total_time = 0
        ride_count = 0
        run_count = 0
        zwift_count = 0
        
        for a in activities:
            total_time += a.get('moving_time', 0)
            atype = a.get('type')
            
            if atype == 'Ride': ride_count += 1
            if atype == 'VirtualRide': 
                ride_count += 1
                zwift_count += 1
            if atype == 'Run' or atype == 'Walk': run_count += 1
        
        # --- АНАЛИЗ 2: ВЕС ---
        # Фильтруем дни, где был указан вес
        weights = [float(d['weight']) for d in wellness if d.get('weight')]
        
        if weights:
            start_w = weights[0] # Вес в начале
            end_w = weights[-1]  # Вес сейчас
            delta_w = end_w - start_w
        else:
            start_w = 0
            end_w = 0
            delta_w = 0
        
        # --- АНАЛИЗ 3: ДИСЦИПЛИНА ---
        # 90 дней / 7 = 12.8 недель. 
        # Цель: 3 тренировки в неделю = 38 тренировок за период.
        total_acts = len(activities)
        target_acts = 38
        consistency_score = (total_acts / target_acts) * 100
        if consistency_score > 100: consistency_score = 100
        
        # --- ГЕНЕРАЦИЯ ОТЧЕТА ---
        report = f"🕵️‍♂️ **ГЛУБОКИЙ АУДИТ (90 ДНЕЙ)**\n"
        report += f"📅 Период: {start} — {end}\n\n"
        
        # БЛОК 1: АКТИВНОСТЬ
        report += f"📊 **БАЗА:**\n"
        report += f"• Всего тренировок: **{total_acts}**\n"
        report += f"• Вело (Станок/Улица): **{ride_count}** (из них Zwift: {zwift_count})\n"
        report += f"• Бег/Ходьба: **{run_count}**\n"
        report += f"• Часов в работе: **{total_time/3600:.1f} ч**\n"
        
        icon_cons = "🔥" if consistency_score > 80 else "⚠️"
        report += f"• Дисциплина: **{consistency_score:.0f}%** {icon_cons}\n\n"
        
        # БЛОК 2: ВЕС
        if start_w and end_w:
            icon_w = "📉" if delta_w <= 0 else "📈"
            report += f"⚖️ **ВЕС:**\n"
            report += f"Было: {start_w:.1f} кг -> Стало: {end_w:.1f} кг\n"
            report += f"Итог: **{delta_w:+.1f} кг** {icon_w}\n\n"
        else:
            report += f"⚖️ **ВЕС:** Нет данных веса за этот период.\n\n"
        
        # БЛОК 3: ВЕРДИКТ
        report += f"🧠 **ВЫВОДЫ ТРЕНЕРА:**\n"
        
        # Профиль
        if run_count > ride_count:
            report += "👉 **Профиль:** Ты больше БЕГАЕШЬ. При весе 115 кг это большой риск для коленей. Смести баланс на Вело (50/50).\n"
        elif ride_count > 0:
            report += "👉 **Профиль:** Ты ВЕЛОСИПЕДИСТ. Это супер. Станок бережет суставы и качает сердце.\n"
            
        # Прогресс веса
        if delta_w > 0.5:
            report += "⚠️ **Внимание:** Вес растет (+). Ты тренируешься, но ешь больше нормы. Слабое звено — ужин.\n"
        elif delta_w < -1.0:
            report += "✅ **Отлично:** Вес уходит уверенно. Система работает.\n"
        elif start_w == 0:
             report += "⚠️ **Нет данных:** Начни взвешиваться!\n"
        else:
            report += "🔄 **Плато:** Вес стоит. Проверь калории.\n"

        # Дисциплина
        if consistency_score < 60:
            report += "⚠️ **Главный хвост:** РЕГУЛЯРНОСТЬ. Часто пропускаешь. Надо чаще, пусть и короче.\n"
        
        send_telegram(report)
        print("Отчет отправлен успешно.")

    except Exception as e:
        send_telegram(f"Ошибка аудита: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    run_audit()

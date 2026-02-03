import os
import requests

# Берем ключи
TOKEN = os.environ.get("TG_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")

def test_telegram():
    print("--- ЗАПУСК ДИАГНОСТИКИ ---")
    
    # 1. Проверяем, видит ли GitHub ключи
    if not TOKEN:
        print("❌ ОШИБКА: GitHub не видит TG_TOKEN! Проверь Secrets.")
        return
    if not CHAT_ID:
        print("❌ ОШИБКА: GitHub не видит TG_CHAT_ID! Проверь Secrets.")
        return
        
    print(f"✅ Токен найден (начинается на: {TOKEN[:5]}...)")
    print(f"✅ ID чата найден (начинается на: {CHAT_ID[:2]}...)")

    # 2. Пробуем отправить тестовое сообщение
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": "🔔 ПРОВЕРКА СВЯЗИ: Если ты это читаешь, значит бот работает!"}
    
    print(f"📤 Отправляю запрос на: {url.replace(TOKEN, 'HIDDEN')}")
    
    response = requests.post(url, json=data)
    
    # 3. Читаем ответ от Telegram
    print(f"📡 Код ответа: {response.status_code}")
    print(f"📝 Текст ответа: {response.text}")
    
    if response.status_code == 200:
        print("✅ УСПЕХ! Сообщение должно прийти.")
    else:
        print("❌ ПРОВАЛ! Смотри 'description' выше, там причина.")
        # Специально ломаем скрипт, чтобы загорелся красный крестик
        raise Exception("Тест не пройден")

if __name__ == "__main__":
    test_telegram()

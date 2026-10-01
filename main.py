import os
import sys
import json
import requests
import tempfile
import threading
import time
from flask import Flask

print("=" * 60)
print(" ЗАПУСК БОТА")
print("=" * 60)

GROQ_KEY = os.environ.get("GROQ_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
MEMORY_FILE = "memory.json"

print(f"🔑 GROQ_KEY есть: {bool(GROQ_KEY)}")
print(f"🔑 TG_TOKEN есть: {bool(TG_TOKEN)}")
print(f" PORT: {os.environ.get('PORT', 'не задан')}")

if not GROQ_KEY or not TG_TOKEN:
    print("❌ ОШИБКА: Не хватает ключей!")
    sys.exit(1)

# Flask для health check
app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

@app.route('/health')
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    print(f" Flask запускается на порту {port}")
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# Запускаем Flask в фоновом потоке
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
print("✅ Flask запущен в фоновом потоке")

time.sleep(2)  # Даём Flask время запуститься

# Функции бота
def load_memory(user_id):
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            return data.get(str(user_id), "Память пуста.")
    return "Память пуста."

def save_memory(user_id, fact):
    data = {}
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
    user_key = str(user_id)
    if user_key not in data:
        data[user_key] = ""
    data[user_key] += f"- {fact}\n"
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f)

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def download_file(file_id):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}"
        resp = requests.get(url, timeout=10).json()
        if not resp.get("ok"):
            print(f"❌ Ошибка getFile: {resp}")
            return None
        file_path = resp["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}"
        r = requests.get(file_url, timeout=30)
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp.write(r.content)
        tmp.close()
        print(f"📥 Файл скачан: {tmp.name}")
        return tmp.name
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        return None

def transcribe_audio(file_path):
    try:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}"}
        with open(file_path, "rb") as f:
            files = {"file": ("voice.ogg", f, "audio/ogg")}
            data = {"model": "whisper-large-v3", "language": "ru"}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        os.unlink(file_path)
        print(f"🎤 Whisper статус: {resp.status_code}")
        if resp.status_code != 200:
            print(f" Whisper ошибка: {resp.text[:200]}")
            return None
        return resp.json().get("text", "").strip()
    except Exception as e:
        print(f"❌ Ошибка транскрипции: {e}")
        return None

def ask_groq(text, memory):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "openai/gpt-oss-20b",
            "messages": [
                {"role": "system", "content": "Ты — ИИ-ассистент Даниила. Отвечай кратко на русском."},
                {"role": "user", "content": f"Память:\n{memory}\n\nВопрос: {text}"}
            ],
            "temperature": 0.7,
            "max_tokens": 512
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code != 200:
            return f" Ошибка ИИ: {response.status_code}"
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Ошибка: {e}"

# ГЛАВНЫЙ ЦИКЛ БОТА
print("=" * 60)
print("✅ БОТ ЗАПУЩЕН! Жду сообщений...")
print("=" * 60)

offset = 0

while True:
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 30}
        )
        updates = response.json().get("result", [])
        
        for update in updates:
            offset = update["update_id"] + 1
            
            if "message" not in update:
                continue
            
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            
            # Текст
            text = msg.get("text", "").strip()
            if text:
                print(f"📩 Текст от {user_id}: {text}")
                
                if text == "/start":
                    send_message(chat_id, "Привет! Я ИИ-ассистент с голосом \n\nКоманды:\n/запомни <факт>\n/память\n\nПишите или говорите!")
                elif text.startswith("/запомни "):
                    save_memory(user_id, text[len("/запомни "):])
                    send_message(chat_id, "✅ Запомнил")
                elif text == "/память":
                    send_message(chat_id, f"💾 {load_memory(user_id)}")
                elif not text.startswith("/"):
                    memory = load_memory(user_id)
                    send_message(chat_id, ask_groq(text, memory))
                continue
            
            # Голосовое
            voice = msg.get("voice")
            if voice:
                print(f"🎤 Голосовое от {user_id}!")
                send_message(chat_id, " Слушаю...")
                
                file_id = voice["file_id"]
                file_path = download_file(file_id)
                
                if not file_path:
                    send_message(chat_id, "❌ Не удалось скачать голос")
                    continue
                
                text = transcribe_audio(file_path)
                
                if not text:
                    send_message(chat_id, "❌ Не удалось распознать речь")
                    continue
                
                print(f"🎤 Распознано: {text}")
                memory = load_memory(user_id)
                answer = ask_groq(text, memory)
                send_message(chat_id, answer)
                
    except Exception as e:
        print(f" Общая ошибка: {e}")
        time.sleep(5)

import os
import json
import requests
import tempfile
from flask import Flask

GROQ_KEY = os.environ.get("GROQ_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
MEMORY_FILE = "memory.json"

app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

port = int(os.environ.get("PORT", 8080))

def run():
    app.run(host='0.0.0.0', port=port)

import threading
t = threading.Thread(target=run)
t.daemon = True
t.start()

print(f" GROQ_KEY есть: {bool(GROQ_KEY)}")
print(f"🔑 TG_TOKEN есть: {bool(TG_TOKEN)}")

if not GROQ_KEY or not TG_TOKEN:
    print(" Не хватает ключей!")
    exit(1)

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
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def download_file(file_id):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_id}"
    resp = requests.get(url).json()
    if not resp.get("ok"):
        return None
    file_path = resp["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_path}"
    r = requests.get(file_url)
    
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.write(r.content)
    tmp.close()
    return tmp.name

def transcribe_audio(file_path):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    with open(file_path, "rb") as f:
        files = {"file": ("voice.ogg", f, "audio/ogg")}
        data = {"model": "whisper-large-v3-turbo", "language": "ru"}
        resp = requests.post(url, headers=headers, files=files, data=data)
    os.unlink(file_path)
    if resp.status_code != 200:
        return None
    return resp.json().get("text", "").strip()

def ask_groq(text, memory):
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
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        return f"Ошибка ИИ: {response.status_code}"
    return response.json()["choices"][0]["message"]["content"]

def handle_text(chat_id, user_id, text):
    if not text or len(text) < 3:
        return
    if text == "/start":
        send_message(chat_id, "Привет! Я ИИ-ассистент с голосом \n\nКоманды:\n/запомни <факт>\n/память\n\nПишите или говорите!")
    elif text.startswith("/запомни "):
        save_memory(user_id, text[len("/запомни "):])
        send_message(chat_id, "✅ Запомнил")
    elif text == "/память":
        send_message(chat_id, f" {load_memory(user_id)}")
    elif not text.startswith("/"):
        memory = load_memory(user_id)
        send_message(chat_id, ask_groq(text, memory))

print("✅ Бот запущен!")
offset = 0

while True:
    try:
        response = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30})
        updates = response.json().get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            if "message" not in update:
                continue
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            
            # Обработка текста
            text = msg.get("text", "").strip()
            if text:
                handle_text(chat_id, user_id, text)
                continue
            
            # Обработка голосовых
            voice = msg.get("voice")
            if voice:
                file_id = voice["file_id"]
                send_message(chat_id, "🎤 Слушаю...")
                file_path = download_file(file_id)
                if not file_path:
                    send_message(chat_id, "❌ Не удалось скачать голос")
                    continue
                text = transcribe_audio(file_path)
                if not text:
                    send_message(chat_id, "❌ Не удалось распознать речь")
                    continue
                print(f"🎤 Голос: {text}")
                memory = load_memory(user_id)
                answer = ask_groq(text, memory)
                send_message(chat_id, answer)
    except Exception as e:
        print(f"Ошибка: {e}")

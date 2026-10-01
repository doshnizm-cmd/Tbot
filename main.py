import os
import json
import requests
from flask import Flask

GROQ_KEY = os.environ.get("GROQ_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
MEMORY_FILE = "memory.json"

app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

def run():
    app.run(host='0.0.0.0', port=8080)

import threading
t = threading.Thread(target=run)
t.daemon = True
t.start()

print(f"🔑 GROQ_KEY есть: {bool(GROQ_KEY)}")
print(f"🔑 TG_TOKEN есть: {bool(TG_TOKEN)}")

if not GROQ_KEY or not TG_TOKEN:
    print("❌ Не хватает ключей!")
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
        return f"Ошибка: {response.status_code}"
    return response.json()["choices"][0]["message"]["content"]

print("✅ Бот запущен!")
offset = 0

while True:
    try:
        response = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", params={"offset": offset, "timeout": 30})
        updates = response.json().get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()
                user_id = msg["from"]["id"]
                if not text:
                    continue
                if text == "/start":
                    send_message(chat_id, "Привет! Я ИИ-ассистент.\n/запомни <факт>\n/память")
                elif text.startswith("/запомни "):
                    save_memory(user_id, text[len("/запомни "):])
                    send_message(chat_id, "✅ Запомнил")
                elif text == "/память":
                    send_message(chat_id, f"💾 {load_memory(user_id)}")
                elif len(text) >= 3 and not text.startswith("/"):
                    send_message(chat_id, ask_groq(text, load_memory(user_id)))
    except Exception as e:
        print(f"Ошибка: {e}")

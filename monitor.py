import json
import logging
import socket
import subprocess
import time

import requests

CONFIG_PATH = "config.json"
LOG_PATH = "monitor.log"
CHECK_INTERVAL = 60    # секунд между проверками
TCP_TIMEOUT = 5        # таймаут TCP-подключения, сек
PING_TIMEOUT_MS = 5000 # таймаут ping, мс

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

def check_tcp(host, port, timeout):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError as e:
        logging.info("TCP %s:%s недоступен: %s", host, port, e)
        return False

def check_ping(host):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(PING_TIMEOUT_MS), host],
            capture_output=True, text=True,
            timeout=PING_TIMEOUT_MS / 1000 + 5,
        )
        # TTL= в ответе — признак настоящего ответа, а не "unreachable"
        return result.returncode == 0 and "ttl=" in result.stdout.lower()
    except Exception as e:
        logging.info("Ping %s ошибка: %s", host, e)
        return False

def check_host(item):
    port = item.get("port")
    if port in (None, ""):          # порт не задан -> проверяем ping'ом
        return check_ping(item["host"])
    return check_tcp(item["host"], port, TCP_TIMEOUT)

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as e:
        logging.error("Telegram: %s", e)

def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    hosts = config["hosts"]
    state = {}

    logging.info("Запуск мониторинга, хостов: %d", len(hosts))

    # стартовое сообщение: тест бота + начальные статусы
    startup = [f"🟢 Мониторинг запущен, хостов: {len(hosts)}"]
    for item in hosts:
        is_up = check_host(item)
        state[item["name"]] = is_up
        startup.append(f"{'✅' if is_up else '❌'} {item['name']}")
    send_telegram(token, chat_id, "\n".join(startup))

    while True:
        time.sleep(CHECK_INTERVAL)
        for item in hosts:
            name = item["name"]
            is_up = check_host(item)

            if is_up != state[name]:
                status = "✅ ДОСТУПЕН" if is_up else "❌ НЕДОСТУПЕН"
                msg = f"{status} {name} ({item['host']})"
                logging.warning(msg)
                send_telegram(token, chat_id, msg)
                state[name] = is_up

if __name__ == "__main__":
    main()
"""调用 Telegram Bot API 依次发送多条消息（HTML 格式）。"""
import time

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(bot_token: str, chat_id: str, text: str, retries: int = 3) -> bool:
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            print(f"[send_telegram] attempt {attempt} failed: {resp.status_code} {resp.text}")
        except requests.RequestException as e:
            print(f"[send_telegram] attempt {attempt} network error: {e}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    return False


def send_digest(bot_token: str, chat_id: str, messages: list) -> dict:
    """依次发送每一段，某一段失败不影响其它段继续发送。返回发送结果统计。"""
    results = {"sent": 0, "failed": 0}
    for i, msg in enumerate(messages):
        ok = send_message(bot_token, chat_id, msg)
        if ok:
            results["sent"] += 1
        else:
            results["failed"] += 1
            print(f"[send_telegram] message segment {i + 1}/{len(messages)} failed to send after retries")
        time.sleep(0.5)  # 避免触发 Telegram 的速率限制
    return results

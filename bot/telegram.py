"""Minimal Telegram notifier + command listener (no extra dependencies)."""
import logging
import threading
import time

import requests

log = logging.getLogger("bot.telegram")


class Telegram:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, str(chat_id)
        self.enabled = bool(token and chat_id)
        self.api = f"https://api.telegram.org/bot{token}"

    def send(self, text):
        log.info("notify: %s", text.replace("\n", " | "))
        if not self.enabled:
            return
        try:
            requests.post(f"{self.api}/sendMessage",
                          json={"chat_id": self.chat_id, "text": text}, timeout=15)
        except Exception as e:  # never let notifications crash the bot
            log.warning("telegram send failed: %s", e)

    def listen(self, handlers):
        """Run command handlers ({'/status': fn, ...}) in a background thread.
        Only messages from the configured chat are accepted."""
        if not self.enabled:
            return

        def loop():
            offset = None
            while True:
                try:
                    r = requests.get(f"{self.api}/getUpdates",
                                     params={"timeout": 50, "offset": offset}, timeout=60).json()
                    for upd in r.get("result", []):
                        offset = upd["update_id"] + 1
                        msg = upd.get("message") or {}
                        if str(msg.get("chat", {}).get("id")) != self.chat_id:
                            continue
                        cmd = (msg.get("text") or "").split()[0].split("@")[0].lower() if msg.get("text") else ""
                        fn = handlers.get(cmd, handlers.get("/help"))
                        if fn:
                            self.send(fn())
                except Exception as e:
                    log.warning("telegram poll failed: %s", e)
                    time.sleep(10)

        threading.Thread(target=loop, daemon=True).start()

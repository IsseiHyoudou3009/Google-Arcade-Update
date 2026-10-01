#!/usr/bin/env python3
"""
Google Skills Arcade watcher.
Alerts (Telegram + ntfy mobile app) when a NEW month's games appear on the page.

Env vars:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   -> Telegram alert
  NTFY_TOPIC                             -> mobile push via the ntfy app (optional)
  TZ_NAME                                -> default Asia/Kolkata

Run:  python arcade_watch.py            (normal)
      python arcade_watch.py --debug    (prints page text + detection, no alerts)
"""
import json
import os
import html as htmllib
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

URL = "https://go.cloudskillsboost.google/arcade"
STATE = Path(__file__).with_name("state.json")
TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Kolkata"))
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def targets(now):
    """Months we're waiting on: the current month and the next one."""
    nxt_y, nxt_m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return [(now.year, now.month), (nxt_y, nxt_m)]


def fetch_text():
    r = requests.get(URL, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    r.raise_for_status()
    raw = r.text
    # strip tags so snippets are readable; month search still works on the text
    text = re.sub(r"<[^>]+>", " ", raw)
    return htmllib.unescape(text), raw


def find_month(text, month_name):
    m = re.search(rf"\b{month_name}\b", text, re.I)
    if not m:
        return None
    s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
    return " ".join(text[s:e].split())


def notify(title, msg):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": f"{title}\n\n{msg}\n\n{URL}"},
            timeout=20)
        print("telegram:", r.status_code)
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        r = requests.post(
            f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Click": URL, "Tags": "video_game"},
            timeout=20)
        print("ntfy:", r.status_code)


def main():
    debug = "--debug" in sys.argv
    now = datetime.now(TZ)
    text, raw = fetch_text()
    text = text + "\n" + raw  # also search raw HTML/JSON in case text sits in page data

    if "arcade" not in raw.lower():
        print("Page doesn't look like the Arcade page - fetch may have been blocked.")
        sys.exit(1)

    found = {}
    for y, m in targets(now):
        ctx = find_month(text, MONTHS[m - 1])
        if ctx:
            found[f"{y}-{m:02d}"] = ctx

    if debug:
        for name in MONTHS:
            ctx = find_month(text, name)
            if ctx:
                print(f"[{name}] ...{ctx}...")
        print("\nTracked months detected:", json.dumps(found, indent=2))
        return

    first_run = not STATE.exists()
    state = json.loads(STATE.read_text()) if not first_run else {"seen": []}

    if first_run:
        state["seen"] = sorted(found)  # baseline: don't alert for what's already live
        live = ", ".join(found) or "none of the tracked months"
        notify("Arcade watcher is running",
               f"Baseline saved. Currently live: {live}. You'll be alerted when the next month goes live.")
    else:
        for key, ctx in found.items():
            if key not in state["seen"]:
                month_name = MONTHS[int(key[5:]) - 1]
                notify(f"Arcade: {month_name} games are LIVE!", f"Found on the page: ...{ctx}...")
                state["seen"].append(key)

    state["seen"] = sorted(set(state["seen"]))[-6:]
    STATE.write_text(json.dumps(state, indent=2))
    print("done:", state)


if __name__ == "__main__":
    main()

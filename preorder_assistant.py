#!/usr/bin/env python3
"""
Pre-Order Assistant
====================

Watches product pages for any retailer/product you list and alerts you
the instant one looks orderable, so YOU can complete the purchase
yourself in seconds.

This script does NOT log into any retailer, does NOT store or enter
payment/account info, and does NOT complete a purchase. It only reads
public product pages and alerts you (desktop notification + repeated
sound + auto-opening the page in your browser). Checkout is always a
manual step you do yourself.

-------------------------------------------------------------------------
SETUP (run once)
-------------------------------------------------------------------------
    pip install -r requirements.txt
    playwright install chromium

-------------------------------------------------------------------------
RUN
-------------------------------------------------------------------------
    python preorder_assistant.py [path/to/watchlist.json]

If no path is given, it looks for watchlist.json next to this script.
Leave the terminal window open — it checks on a loop until you stop it
(Ctrl+C) or close it. Run it on your own machine, not a cloud server:
retailers are far more likely to trust checks coming from a normal home
IP than a datacenter one, and this needs to run continuously rather
than on any fixed schedule.

-------------------------------------------------------------------------
CUSTOMIZE
-------------------------------------------------------------------------
Edit watchlist.json to add/remove products and adjust the phrase lists
per item if you get false positives/negatives — every retailer's site
wording is a little different, and heavily-JS-rendered pages can
occasionally return inconclusive results. When that happens, the
script just tells you to check manually rather than guessing.
"""

import json
import platform
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Missing dependency. Run: pip install -r requirements.txt && playwright install chromium")
    sys.exit(1)

try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


def _detect_wsl():
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except FileNotFoundError:
        return False


IS_WSL = platform.system() == "Linux" and _detect_wsl()

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "watchlist.json"

# Fallback defaults if a setting is missing from the config file.
DEFAULT_CHECK_INTERVAL_SECONDS = 45
DEFAULT_REALERT_INTERVAL_SECONDS = 300
DEFAULT_CONFIRM_DELAY_SECONDS = 6
DEFAULT_SETTLE_WAIT_MS = 4000


def load_config(path):
    if not path.exists():
        print(f"Config file not found: {path}")
        print("Copy/edit watchlist.json (see README.md) and try again.")
        sys.exit(1)

    with open(path) as f:
        config = json.load(f)

    items = config.get("items", [])
    if not items:
        print(f"No items in {path} — add at least one product to watch.")
        sys.exit(1)

    for item in items:
        for required in ("name", "url", "sold_out_phrases", "in_stock_phrases"):
            if required not in item:
                print(f"Item missing required field {required!r}: {item}")
                sys.exit(1)

    config.setdefault("check_interval_seconds", DEFAULT_CHECK_INTERVAL_SECONDS)
    config.setdefault("realert_interval_seconds", DEFAULT_REALERT_INTERVAL_SECONDS)
    config.setdefault("confirm_delay_seconds", DEFAULT_CONFIRM_DELAY_SECONDS)
    config.setdefault("default_settle_wait_ms", DEFAULT_SETTLE_WAIT_MS)
    return config


def beep(times=5):
    system = platform.system()
    for _ in range(times):
        if system == "Darwin":
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
        elif system == "Windows":
            import winsound
            winsound.Beep(1000, 400)
        elif IS_WSL:
            # Terminal bell isn't reliably audible under WSL — ring through
            # the Windows host instead.
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", "[console]::beep(1000,400)"],
                check=False,
            )
        else:
            print("\a", end="", flush=True)
        time.sleep(0.3)


def open_url(url):
    if IS_WSL:
        # webbrowser.open() reports success under WSL even when no browser
        # actually opens (there's usually no Linux browser installed, and
        # xdg-open doesn't know how to reach the Windows host). Hand off to
        # PowerShell instead so it opens in the real Windows default browser.
        # (Env vars don't cross the WSL/Windows interop boundary, so the URL
        # is embedded directly — safe here since watchlist URLs come from a
        # local config file you control, quoted per PowerShell single-quote
        # escaping rules.)
        quoted = "'" + url.replace("'", "''") + "'"
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath {quoted}"],
            check=False,
        )
    else:
        webbrowser.open(url)


def alert(item_name, url):
    ts = datetime.now().strftime("%H:%M:%S")
    banner = f"[{ts}] LOOKS AVAILABLE: {item_name}\n{url}"
    print("\n" + "=" * 70)
    print(banner)
    print("VERIFY MANUALLY, THEN CHECKOUT YOURSELF.")
    print("=" * 70 + "\n")

    if HAS_PLYER:
        try:
            notification.notify(
                title=f"{item_name} — check now!",
                message=f"{item_name} may be available. Opening the page now.",
                timeout=10,
            )
        except Exception as e:
            print(f"(desktop notification failed: {e})")

    beep()
    open_url(url)


def check_page(browser, item, default_settle_wait_ms):
    # Some sites (Target, notably) render a disabled/placeholder buy button
    # that happens to match an in-stock phrase, then hydrate into their real
    # state a moment later. A single fixed sleep-then-read can catch that
    # placeholder and never see the real state at all — timing is racy, not
    # just slow, so a longer fixed sleep doesn't reliably fix it either.
    # Instead, poll: keep re-reading the page until an explicit sold-out
    # phrase shows up (trusted immediately) or the timeout is exhausted, and
    # only then fall back to whatever the last read shows.
    max_wait_ms = item.get("settle_wait_ms", default_settle_wait_ms)
    poll_interval_ms = 1000

    page = browser.new_page(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        # A page with no viewport/locale set is a giveaway of headless
        # automation — Amazon hard-blocks it outright (a "click to continue"
        # interstitial with no real content), while a page that looks like a
        # normal browser tab gets through fine.
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    try:
        page.goto(item["url"], timeout=20000, wait_until="domcontentloaded")
        elapsed_ms = 0
        text = ""
        while True:
            step = 1500 if elapsed_ms == 0 else poll_interval_ms
            page.wait_for_timeout(step)
            elapsed_ms += step
            text = page.inner_text("body").lower()

            for phrase in item["sold_out_phrases"]:
                if phrase in text:
                    return False  # explicit and final — no need to wait further

            if elapsed_ms >= max_wait_ms:
                break
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] error checking {item['name']}: {e}")
        return None
    finally:
        page.close()

    # No sold-out phrase ever appeared during the whole wait window — only
    # now do we trust a generic in-stock phrase like "add to cart".
    for phrase in item["in_stock_phrases"]:
        if phrase in text:
            return True

    return None  # inconclusive — page structure didn't match known phrases


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    items = config["items"]
    check_interval_seconds = config["check_interval_seconds"]
    realert_interval_seconds = config["realert_interval_seconds"]
    confirm_delay_seconds = config["confirm_delay_seconds"]
    default_settle_wait_ms = config["default_settle_wait_ms"]

    print("Pre-Order Assistant")
    print(f"Watching {len(items)} page(s) every {check_interval_seconds}s (config: {config_path}).")
    print("This tool only watches and alerts. It never logs in, stores payment")
    print("info, or completes a purchase — that part is always up to you.\n")

    last_alert_time = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            while True:
                for item in items:
                    status = check_page(browser, item, default_settle_wait_ms)
                    ts = datetime.now().strftime("%H:%M:%S")
                    url = item["url"]

                    if status is True:
                        last = last_alert_time.get(url, 0)
                        if time.time() - last >= realert_interval_seconds:
                            print(f"[{ts}] {item['name']}: LOOKS AVAILABLE — confirming before alerting...")
                            time.sleep(confirm_delay_seconds)
                            if check_page(browser, item, default_settle_wait_ms) is True:
                                alert(item["name"], url)
                                last_alert_time[url] = time.time()
                            else:
                                print(
                                    f"[{datetime.now().strftime('%H:%M:%S')}] {item['name']}: "
                                    "didn't confirm on recheck — likely a render glitch, still watching"
                                )
                        else:
                            print(f"[{ts}] {item['name']}: LOOKS AVAILABLE")
                    elif status is False:
                        print(f"[{ts}] {item['name']}: not available")
                        last_alert_time.pop(url, None)
                    else:
                        print(f"[{ts}] {item['name']}: inconclusive — check manually")

                time.sleep(check_interval_seconds)
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            # Ctrl+C also interrupts the Playwright driver subprocess, so the
            # close call itself can throw here — we're exiting either way.
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()

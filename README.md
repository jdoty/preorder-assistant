# Pre-Order Assistant

Watches any product page(s) you list and alerts you the instant one
looks orderable — desktop notification, repeated sound, and it
auto-opens the page in your browser so you can check out yourself.

**What this does NOT do:** log into any retailer account, store or enter
payment info, or complete a purchase automatically. Checkout is always
a manual step you do. Automating that part would violate every major
retailer's terms of service and risk your accounts getting banned —
this tool only gets you there fast, it doesn't buy for you.

## Get the code

```bash
git clone https://github.com/jdoty/preorder-assistant.git
cd preorder-assistant
```

## Setup (run once)

Requires Python 3. Set up a virtual environment so dependencies stay
isolated from the rest of your system:

```bash
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

You'll need to run `source .venv/bin/activate` again each time you open
a new terminal to work on this (skip it if you installed the deps
system-wide instead).

## Run

```bash
python preorder_assistant.py
```

Leave the terminal open. It checks every 45 seconds by default and
keeps running until you stop it (Ctrl+C).

Run this on your own computer, not a cloud server or VPS — retailers
are more likely to trust checks coming from a normal home internet
connection, and this needs to run continuously rather than on a fixed
schedule.

To watch a different set of products without touching the default
list, keep multiple config files and point the script at one:

```bash
python preorder_assistant.py my-other-watchlist.json
```

## Customizing

Open `watchlist.json` and edit the `items` list:

- Add a product page URL for any retailer.
- List phrases that mean "not available yet" (`sold_out_phrases`) and
  phrases that mean "available" (`in_stock_phrases`) — these vary by
  site, so tweak them if you notice false positives/negatives in the
  console output.
- Optionally set a per-item `settle_wait_ms` if a particular page needs
  longer than the default to settle into its real state before trusting
  an "add to cart"-style phrase (see Target's entry for an example).

Top-level settings in the same file:

- `check_interval_seconds` — how often each page is re-checked.
- `realert_interval_seconds` — how often it re-alerts you while a
  listing stays available (in case you miss the first alert).
- `confirm_delay_seconds` — how long it waits before re-checking a page
  that looks available, to filter out render glitches, before alerting.
- `default_settle_wait_ms` — default polling window used to catch a
  page settling into its real sold-out/in-stock state.

**Be careful with marketplace listings** (Amazon/Walmart third-party
sellers) — they sometimes list items at a significant markup over
retail price. Only watch the official retailer listing, and double
check the seller and price yourself before buying anything the
assistant flags as available.

## Why it can be wrong sometimes

These are JavaScript-heavy e-commerce pages, and phrase-matching on
rendered text isn't perfect. The assistant errs toward flagging "looks
available" and opening the page for you to verify with your own eyes,
rather than silently deciding on your behalf. If it says "inconclusive,"
that means the page didn't clearly match either phrase list — check it
by hand.

## Known limitations (current console watchlist)

- **Target** currently shows a "press & hold" bot-verification challenge
  on every page load for this product, which hides the real add-to-cart
  state from the automated check. This isn't something the watcher can
  (or should) solve — doing so would mean automating past a retailer's
  anti-bot protection. Expect Target to report "inconclusive" most of
  the time right now; check it by hand periodically. If Target relaxes
  this check later, phrase-matching will start working again with no
  changes needed.
- **GameStop** has moved this item to in-store-only allocation (no
  online ordering), so the page explicitly says "Available In Stores."
  The watcher correctly reports this as "not available" online, but
  that's a GameStop policy, not a bug — it won't start showing "add to
  cart" unless GameStop resumes online sales for this item.

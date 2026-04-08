import requests
import time
import json
import os
import html
from datetime import datetime
from urllib.parse import quote_plus

# =========================================================
# CONFIG
# =========================================================
FEDEX_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiI2NzhlNThmZGM5Njc2ZjAwMDkwZmNiNTciLCJleHAiOjE3NzgyNDcyOTIsInRlbmFudElkIjoiRkRYRlJHSFRfMSIsInVzZXJUeXBlIjoiY2Fycmllcl9kaXNwYXRjaGVyIiwic2Vzc2lvbklkIjoiOTk2OTk3OGItYWNiOC00M2M5LWJlNjMtMjdhZWVlYjUyNGU3In0.LdYoFPhjYRWggZnW489Kc--XqDiOOqtqsCIGZbtWFNM"

TELEGRAM_BOT_TOKEN = "8636504764:AAEp1adhodIBE1_qZ391R7EO5j3eh4SoJ5w"
CHANNEL_ID = "-1003750550317"
OFFERS_GROUP_ID = "-1003651639921"

KEY = "AlzaSyAHpKsviDxi4Rcp8YU9zX1RryymAsAaUKo"
USER_ID = "678e58fdc9676f00090fcb57"
TENANT_ID = "FDXFRGHT_1"
COMPANY_ID = "6584b5a7c839a80009a7a41f"

FORMAT_FOR_CARRIERS_URL = (
    f"https://es-fedex.zuumapp.com/v1/search/shipments/format-for-carriers?key={KEY}"
)

STATE_FILE = "bot_state.json"
POLL_INTERVAL_SECONDS = 10

HEADERS = {
    "Authorization": FEDEX_TOKEN,
    "X-Access-Token": FEDEX_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://carrier-fedex.zuumapp.com",
    "Referer": "https://carrier-fedex.zuumapp.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "X-Action-Source": "Carrier Web",
    "X-Time-Zone": "America/New_York",
}

# =========================================================
# FILE STATE
# =========================================================
def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


state = load_json_file(
    STATE_FILE,
    {
        "offset": 0,
        "posted_messages": {},   # shipment_id -> message_id
        "signatures": {},        # shipment_id -> signature
        "cache": {}              # shipment_id -> load object
    }
)

# =========================================================
# TELEGRAM
# =========================================================
def tg_post(method, payload):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.post(url, json=payload, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "raw": r.text}


def tg_get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 20}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(url, params=params, timeout=40)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "raw": r.text}


def tg_send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_post("sendMessage", payload)


def tg_edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_post("editMessageText", payload)


def tg_answer_callback(callback_query_id, text, show_alert=False):
    payload = {
        "callback_query_id": callback_query_id,
        "text": text[:180],
        "show_alert": show_alert,
    }
    return tg_post("answerCallbackQuery", payload)

# =========================================================
# FEDEX
# =========================================================
def get_detailed_bidding():
    today_str = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "calculateDeadheads": True,
        "includeMyBids": True,
        "includeNewOffers": True,
        "pickupFromDate": today_str,
        "searchType": "lanes",
        "size": 1500,
        "currentUserIds": [USER_ID],
        "tenantIds": [TENANT_ID],
        "pickup": {"type": "anywhere"},
        "dropoff": {"type": "anywhere"},
        "truckType": ["Any"],
        "excludeLoadType": ["Less Than Truck Load (LTL)"],
        "excludeThirdPartyBrokers": ["BANYAN"],
        "companyIds": [COMPANY_ID],
    }

    r = requests.post(
        FORMAT_FOR_CARRIERS_URL,
        json=payload,
        headers=HEADERS,
        timeout=30,
    )

    print("FORMAT STATUS:", r.status_code)

    if r.status_code != 200:
        print(r.text)
        return []

    try:
        data = r.json()
        bidding = data.get("data", {}).get("bidding", [])
        print("DETAILED COUNT:", len(bidding))
        return bidding
    except Exception as e:
        print("FORMAT JSON ERROR:", e)
        print(r.text)
        return []

# =========================================================
# HELPERS
# =========================================================
def esc(value):
    return html.escape(str(value or "N/A"))


def parse_money(value):
    if value is None:
        return 999999999.0
    s = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return 999999999.0


def get_pickup_stop(load):
    pickups = load.get("pickUps", [])
    return pickups[0] if pickups else {}


def get_dropoff_stop(load):
    dropoffs = load.get("dropOffs", [])
    return dropoffs[0] if dropoffs else {}


def get_pickup_location(load):
    return get_pickup_stop(load).get("stop", {}).get("location", {})


def get_dropoff_location(load):
    return get_dropoff_stop(load).get("stop", {}).get("location", {})


def get_offer_status_icon(status):
    s = (status or "").lower()

    if "accepted" in s or "awarded" in s or "winner" in s:
        return "🏆"
    if "declined" in s:
        return "❌"
    if "created" in s:
        return "🟦"
    if "counter" in s:
        return "🔁"
    if "pending" in s:
        return "⏳"
    return "📌"


def get_company_display(user_obj):
    company = user_obj.get("company")

    if isinstance(company, dict):
        return company.get("name", "Unknown Company")

    if isinstance(company, str) and company.strip():
        return company

    return "Unknown Company"


def sort_offers(offers):
    return sorted(offers, key=lambda x: parse_money(x.get("price")))


def detect_winner(offers):
    for offer in offers:
        status = (offer.get("status") or "").lower()
        if "accepted" in status or "awarded" in status or "winner" in status:
            return offer
    return None


def build_map_url(load):
    pickup_loc = get_pickup_location(load)
    dropoff_loc = get_dropoff_location(load)

    p_geo = pickup_loc.get("geoLocation", {})
    d_geo = dropoff_loc.get("geoLocation", {})

    if (
        p_geo.get("lat") is not None
        and p_geo.get("long") is not None
        and d_geo.get("lat") is not None
        and d_geo.get("long") is not None
    ):
        return (
            f"https://www.google.com/maps/dir/"
            f"{p_geo['lat']},{p_geo['long']}/"
            f"{d_geo['lat']},{d_geo['long']}"
        )

    p_addr = pickup_loc.get("fullAddress", "")
    d_addr = dropoff_loc.get("fullAddress", "")
    if p_addr and d_addr:
        return f"https://www.google.com/maps/dir/{quote_plus(p_addr)}/{quote_plus(d_addr)}"

    return None


def build_signature(load):
    offers = load.get("offers", [])
    signature_payload = {
        "updatedAt": load.get("updatedAt"),
        "price": load.get("price"),
        "offers": [
            {
                "id": o.get("_id"),
                "price": o.get("price"),
                "status": o.get("status"),
                "updatedAt": o.get("updatedAt"),
            }
            for o in offers
        ],
    }
    return json.dumps(signature_payload, sort_keys=True)


def build_load_text(load):
    shipment_id = load.get("longId", "N/A")
    load_id = load.get("loadId", "N/A")

    pickup_loc = get_pickup_location(load)
    dropoff_loc = get_dropoff_location(load)
    pickup_stop = get_pickup_stop(load)
    dropoff_stop = get_dropoff_stop(load)

    pickup_city = pickup_loc.get("city", "N/A")
    pickup_state = pickup_loc.get("stateAbbr", "")
    pickup_addr = pickup_loc.get("fullAddress", "N/A")

    dropoff_city = dropoff_loc.get("city", "N/A")
    dropoff_state = dropoff_loc.get("stateAbbr", "")
    dropoff_addr = dropoff_loc.get("fullAddress", "N/A")

    pickup_date = pickup_stop.get("startDateLocalText", "N/A")
    pickup_time = pickup_stop.get("startTimeLocal", "N/A")
    pickup_type = pickup_stop.get("type", "N/A")

    dropoff_date = dropoff_stop.get("startDateLocalText", "N/A")
    dropoff_time = dropoff_stop.get("startTimeLocal", "N/A")
    dropoff_type = dropoff_stop.get("type", "N/A")

    load_info = load.get("load", {})
    current_price = load.get("price", "N/A")
    service = load_info.get("service", "N/A")
    freight_type = load_info.get("type", "N/A")
    reason_code = load_info.get("reasonCode", "N/A")
    hazmat = load_info.get("isHazmat", False)

    offers = sort_offers(load.get("offers", []))
    offers_count = len(offers)
    lowest_offer = offers[0]["price"] if offers else "N/A"
    winner = detect_winner(offers)

    winner_line = "🏆 <b>Winner:</b> Not decided"
    if winner:
        winner_user = winner.get("createdByUser", {})
        winner_name = f"{winner_user.get('firstName', '')} {winner_user.get('lastName', '')}".strip()
        winner_line = f"🏆 <b>Winner:</b> {esc(winner_name)} — {esc(winner.get('price'))}"

    text = (
        f"🚛 <b>NEW LOAD</b>\n\n"
        f"🆔 <b>Shipment ID:</b> {esc(shipment_id)}\n"
        f"📦 <b>Load ID:</b> {esc(load_id)}\n\n"
        f"📍 <b>Pickup:</b> {esc(pickup_city)}, {esc(pickup_state)}\n"
        f"🏠 <b>Pickup address:</b> {esc(pickup_addr)}\n"
        f"📅 <b>Pickup date:</b> {esc(pickup_date)}\n"
        f"⏰ <b>Pickup time:</b> {esc(pickup_time)}\n"
        f"🧾 <b>Pickup type:</b> {esc(pickup_type)}\n\n"
        f"📍 <b>Dropoff:</b> {esc(dropoff_city)}, {esc(dropoff_state)}\n"
        f"🏠 <b>Dropoff address:</b> {esc(dropoff_addr)}\n"
        f"📅 <b>Dropoff date:</b> {esc(dropoff_date)}\n"
        f"⏰ <b>Dropoff time:</b> {esc(dropoff_time)}\n"
        f"🧾 <b>Dropoff type:</b> {esc(dropoff_type)}\n\n"
        f"💵 <b>Current price:</b> {esc(current_price)}\n"
        f"💸 <b>Lowest bid:</b> {esc(lowest_offer)}\n"
        f"{winner_line}\n"
        f"📊 <b>Offers count:</b> {offers_count}\n\n"
        f"🚚 <b>Service:</b> {esc(service)}\n"
        f"📦 <b>Freight type:</b> {esc(freight_type)}\n"
        f"📝 <b>Reason:</b> {esc(reason_code)}\n"
        f"☣️ <b>Hazmat:</b> {esc(hazmat)}"
    )
    return text


def build_offers_text(load):
    shipment_id = load.get("longId", "N/A")
    pickup_loc = get_pickup_location(load)
    dropoff_loc = get_dropoff_location(load)

    pickup_short = f"{pickup_loc.get('city', 'N/A')}, {pickup_loc.get('stateAbbr', '')}".strip(", ")
    dropoff_short = f"{dropoff_loc.get('city', 'N/A')}, {dropoff_loc.get('stateAbbr', '')}".strip(", ")

    offers = sort_offers(load.get("offers", []))

    if not offers:
        return (
            f"📊 <b>VIEW OFFERS</b>\n\n"
            f"🆔 <b>Shipment:</b> {esc(shipment_id)}\n"
            f"🛣 <b>Route:</b> {esc(pickup_short)} → {esc(dropoff_short)}\n\n"
            f"❌ Offer topilmadi."
        )

    lowest = offers[0]
    winner = detect_winner(offers)

    parts = [
        "📊 <b>VIEW OFFERS</b>",
        "",
        f"🆔 <b>Shipment:</b> {esc(shipment_id)}",
        f"🛣 <b>Route:</b> {esc(pickup_short)} → {esc(dropoff_short)}",
        f"📈 <b>Total offers:</b> {len(offers)}",
        f"💸 <b>Lowest bid:</b> {esc(lowest.get('price'))}",
    ]

    if winner:
        winner_user = winner.get("createdByUser", {})
        winner_name = f"{winner_user.get('firstName', '')} {winner_user.get('lastName', '')}".strip()
        parts.append(f"🏆 <b>Winner:</b> {esc(winner_name)} — {esc(winner.get('price'))}")
    else:
        parts.append("🏆 <b>Winner:</b> Not decided")

    parts.append("")
    parts.append("━━━━━━━━━━━━━━")

    for idx, offer in enumerate(offers, 1):
        user = offer.get("createdByUser", {})
        first_name = user.get("firstName", "")
        last_name = user.get("lastName", "")
        full_name = f"{first_name} {last_name}".strip() or "Unknown"
        email = user.get("email", "N/A")
        phone = user.get("phoneNumber", "N/A")
        user_type = user.get("type", "N/A")
        company_name = get_company_display(user)
        price = offer.get("price", "N/A")
        status = offer.get("status", "N/A")
        icon = get_offer_status_icon(status)

        parts.append(f"{icon} <b>{idx}. {esc(price)}</b>")
        parts.append(f"🏢 <b>Company:</b> {esc(company_name)}")
        parts.append(f"👤 <b>Name:</b> {esc(full_name)}")
        parts.append(f"🪪 <b>Type:</b> {esc(user_type)}")
        parts.append(f"📧 <b>Email:</b> {esc(email)}")
        parts.append(f"📞 <b>Phone:</b> {esc(phone)}")
        parts.append(f"📌 <b>Status:</b> {esc(status)}")
        parts.append("━━━━━━━━━━━━━━")

    return "\n".join(parts)


def build_keyboard(load):
    shipment_id = load.get("longId")
    map_url = build_map_url(load)

    row1 = [
        {"text": "📊 View Offers", "callback_data": f"offers|{shipment_id}"}
    ]

    if map_url:
        row2 = [{"text": "🗺 View in Map", "url": map_url}]
    else:
        row2 = [{"text": "🗺 View in Map", "callback_data": f"map|{shipment_id}"}]

    return {"inline_keyboard": [row1, row2]}

# =========================================================
# MAIN LOGIC
# =========================================================
def persist_state():
    save_json_file(STATE_FILE, state)


def refresh_cache_and_sync_channel():
    detailed = get_detailed_bidding()

    if not detailed:
        print("No detailed data returned.")
        return

    new_cache = {}

    for load in detailed:
        shipment_id = load.get("longId")
        if not shipment_id:
            continue

        new_cache[shipment_id] = load
        text = build_load_text(load)
        keyboard = build_keyboard(load)
        signature = build_signature(load)

        old_signature = state["signatures"].get(shipment_id)
        existing_message_id = state["posted_messages"].get(shipment_id)

        if not existing_message_id:
            send_result = tg_send_message(CHANNEL_ID, text, keyboard)
            print("SEND RESULT:", send_result)

            if send_result.get("ok"):
                message_id = send_result["result"]["message_id"]
                state["posted_messages"][shipment_id] = message_id
                state["signatures"][shipment_id] = signature
                print("SENT LOAD:", shipment_id)
        else:
            if signature != old_signature:
                edit_result = tg_edit_message(CHANNEL_ID, existing_message_id, text, keyboard)
                print("EDIT RESULT:", edit_result)
                if edit_result.get("ok"):
                    state["signatures"][shipment_id] = signature
                    print("UPDATED LOAD:", shipment_id)

    state["cache"] = new_cache
    persist_state()


def handle_callback(callback):
    callback_id = callback["id"]
    data = callback.get("data", "")

    if "|" not in data:
        tg_answer_callback(callback_id, "Noto'g'ri callback.", True)
        return

    action, shipment_id = data.split("|", 1)
    load = state.get("cache", {}).get(shipment_id)

    if not load:
        tg_answer_callback(callback_id, "Load cache topilmadi.", True)
        return

    if action == "offers":
        tg_answer_callback(callback_id, "Offers groupga yuborildi.", False)
        offers_text = build_offers_text(load)
        send_result = tg_send_message(OFFERS_GROUP_ID, offers_text)
        print("OFFERS SEND RESULT:", send_result)

    elif action == "map":
        tg_answer_callback(callback_id, "Map link topilmadi.", True)


def process_updates():
    offset = state.get("offset", 0)
    updates = tg_get_updates(offset)

    if not updates.get("ok"):
        print("GET UPDATES ERROR:", updates)
        return

    for upd in updates.get("result", []):
        state["offset"] = upd["update_id"] + 1

        if "callback_query" in upd:
            handle_callback(upd["callback_query"])

    persist_state()

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    print("Bot ishga tushdi...")

    while True:
        try:
            refresh_cache_and_sync_channel()
            process_updates()
        except Exception as e:
            print("ERROR:", e)

        time.sleep(POLL_INTERVAL_SECONDS)

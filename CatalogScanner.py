import requests
import random
import time
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import datetime

ROBLOSECURITY_COOKIE = ""  # Paste your .ROBLOSECURITY cookie here
DISCORD_WEBHOOK_URL = ""   # Add your webhook for Discord notifications

ASSET_TYPE_NAMES = {
    1: "Image", 2: "T-Shirt", 3: "Audio", 4: "Mesh", 5: "Lua",
    8: "Hat", 9: "Place", 10: "Model", 11: "Shirt", 12: "Pants",
    13: "Decal", 18: "Face", 19: "Gear", 21: "Badge", 22: "Game Pass",
    24: "Animation", 25: "Arms", 26: "Legs", 27: "Torso",
    28: "Right Arm", 29: "Left Arm", 30: "Left Leg", 31: "Right Leg",
    41: "Hair Accessory", 42: "Face Accessory", 43: "Neck Accessory",
    44: "Shoulder Accessory", 45: "Front Accessory", 46: "Back Accessory",
    47: "Waist Accessory"
}

OUTPUT_FILES = {
    "clothing": "roblox_old_clothing.txt",
    "places": "roblox_old_places.txt",
    "accessories": "roblox_old_accessories.txt",
    "other": "roblox_old_other.txt"
}

DELAY_BETWEEN_REQUESTS = 0.1  # Increase to 0.5 if rate limited
RATE_LIMIT_BACKOFF = 0.5

CLOTHING_TYPES = [2, 8, 11, 12, 18]
PLACE_TYPES = [9]
ACCESSORY_TYPES = [8, 19, 41, 42, 43, 44, 45, 46, 47]

YEAR_RANGES = {
    2008: (1_000_000, 10_000_000),
    2009: (10_000_001, 20_000_000),
    2010: (20_000_001, 30_000_000),
    2011: (30_000_001, 45_000_000),
    2012: (45_000_001, 65_000_000),
    2013: (65_000_001, 90_000_000),
    2014: (90_000_001, 120_000_000),
    2015: (120_000_001, 150_000_000)
    #Its a big range but it mostly finds items from 2009-2012
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.roblox.com/",
    "Origin": "https://www.roblox.com"
}

if ROBLOSECURITY_COOKIE:
    headers["Cookie"] = f".ROBLOSECURITY={ROBLOSECURITY_COOKIE}"

stats = {
    "scanned": 0,
    "found_clothing": 0,
    "found_places": 0,
    "found_accessories": 0,
    "found_other": 0,
    "rate_limited": 0,
    "authenticated": bool(ROBLOSECURITY_COOKIE)
}

log_output = {
    "clothing": True,
    "places": True,
    "accessories": True,
    "other": True
}

discord_enabled = True
current_delay = DELAY_BETWEEN_REQUESTS
scan_start_time = datetime.datetime.now()


def get_asset_type_name(asset_type_id):
    return ASSET_TYPE_NAMES.get(asset_type_id, f"Unknown ({asset_type_id})")


def get_asset_category(asset_type_id):
    if asset_type_id in CLOTHING_TYPES:
        return "clothing"
    elif asset_type_id in PLACE_TYPES:
        return "places"
    elif asset_type_id in ACCESSORY_TYPES:
        return "accessories"
    return "other"


def get_price_info(data):
    price_robux = data.get("PriceInRobux")
    is_for_sale = data.get("IsForSale", False)
    is_limited = data.get("IsLimited", False)
    is_limited_unique = data.get("IsLimitedUnique", False)
    
    collectibles = data.get("CollectiblesItemDetails", {})
    if collectibles:
        resale_price = collectibles.get("CollectibleLowestResalePrice")
        if resale_price:
            return f"Resale: {resale_price} R$"
    
    if price_robux is None or price_robux == 0:
        return "FREE" if is_for_sale else "Off-Sale (was Free)"
    
    status = "Limited" if is_limited else "Limited U" if is_limited_unique else "For Sale"
    if is_for_sale:
        return f"{price_robux} R$ ({status})"
    return f"Off-Sale (was {price_robux} R$)"


def send_discord_message(asset_id, name, asset_type_name, price_info, category):
    if not discord_enabled or not DISCORD_WEBHOOK_URL:
        return
    try:
        emoji_map = {
            "clothing": "👕",
            "places": "🏠",
            "accessories": "🎩",
            "other": "📦"
        }
        emoji = emoji_map.get(category, "📦")
        
        data = {
            "content": f"{emoji} New Roblox {category.title()} Found!\n"
                      f"**ID:** {asset_id}\n"
                      f"**Name:** {name}\n"
                      f"**Type:** {asset_type_name}\n"
                      f"**Price:** {price_info}"
        }
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=5)
    except Exception as e:
        print(f"Discord error: {e}")


def scan_asset(asset_id):
    global current_delay
    
    try:
        stats["scanned"] += 1
        
        url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
        response = requests.get(url, headers=headers, timeout=5)
        
        log_message(f"[SCAN] ID: {asset_id} | Status: {response.status_code} | Delay: {current_delay:.1f}s")
        
        if response.status_code == 429:
            stats["rate_limited"] += 1
            current_delay = min(current_delay + RATE_LIMIT_BACKOFF, 5.0)
            log_message(f"[RATE LIMIT] Increasing delay to {current_delay:.1f}s")
            update_stats()
            time.sleep(current_delay * 2)
            return
        
        if response.status_code == 401:
            log_message("[AUTH ERROR] Invalid or expired cookie!")
            stats["authenticated"] = False
            update_stats()
            return
        
        if response.status_code == 200:
            current_delay = max(current_delay * 0.98, DELAY_BETWEEN_REQUESTS)
        
        if response.status_code != 200:
            update_stats()
            return
        
        data = response.json()
        
        if "errors" in data:
            update_stats()
            return
        
        name = data.get("Name", "")
        asset_type_id = data.get("AssetTypeId")
        created = data.get("Created", "")
        
        if not name or not asset_type_id:
            update_stats()
            return
        
        asset_type_name = get_asset_type_name(asset_type_id)
        category = get_asset_category(asset_type_id)
        price_info = get_price_info(data)
        
        emoji_map = {"clothing": "👕", "places": "🏠", "accessories": "🎩", "other": "📦"}
        emoji = emoji_map.get(category, "📦")
        
        message = (f"{emoji} [FOUND - {category.upper()}] ID: {asset_id} | Name: {name} | "
                  f"Type: {asset_type_name} | Price: {price_info} | Created: {created}")
        log_message(message)
        
        stats[f"found_{category}"] += 1
        update_stats()
        
        # Write to file if enabled
        if log_output.get(category, True):
            output_file = OUTPUT_FILES[category]
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(f"{asset_id} | {name} | {asset_type_name} | {price_info} | {created}\n")
        
        send_discord_message(asset_id, name, asset_type_name, price_info, category)
        
    except Exception as e:
        log_message(f"[ERROR] ID: {asset_id} | {type(e).__name__}: {e}")
        update_stats()


def scan_random_ids():
    if not ROBLOSECURITY_COOKIE:
        log_message("WARNING: No cookie provided - expect rate limits!\n")
    else:
        log_message("Running with authentication\n")
    
    log_message("Scanner started! Searching 2008-2015 items...\n")
    
    while True:
        year = random.randint(2008, 2015)
        start, end = YEAR_RANGES[year]
        asset_id = random.randint(start, end)
        
        scan_asset(asset_id)
        
        # Add random jitter to avoid detection
        jitter = random.uniform(0.7, 1.3)
        time.sleep(current_delay * jitter)


# GUI 
root = tk.Tk()
root.title("Roblox Catalog Scanner")

text_area = ScrolledText(root, width=120, height=25)
text_area.pack(padx=10, pady=10)

stats_label = tk.Label(root, text="Starting...", font=("Arial", 10))
stats_label.pack(pady=5)


def log_message(message):
    text_area.insert(tk.END, message + "\n")
    text_area.see(tk.END)


def update_stats():
    elapsed = (datetime.datetime.now() - scan_start_time).total_seconds()
    rate = stats['scanned'] / elapsed if elapsed > 0 else 0
    auth = "✓ Auth" if stats["authenticated"] else "✗ No Auth"
    
    stats_label.config(
        text=f"{auth} | Scanned: {stats['scanned']} | "
             f"Clothing: {stats['found_clothing']} | Places: {stats['found_places']} | "
             f"Accessories: {stats['found_accessories']} | Other: {stats['found_other']} | "
             f"Rate Limited: {stats['rate_limited']} | {rate:.1f} scans/sec"
    )


def create_toggle(category, text):
    def toggle():
        log_output[category] = not log_output[category]
        btn.config(text=f"{text}: {'ON' if log_output[category] else 'OFF'}")
    btn = tk.Button(root, text=f"{text}: ON", command=toggle)
    btn.pack(pady=2)
    return btn


def toggle_discord():
    global discord_enabled
    discord_enabled = not discord_enabled
    discord_btn.config(text=f"Discord: {'ON' if discord_enabled else 'OFF'}")


discord_btn = tk.Button(root, text="Discord: ON", command=toggle_discord)
discord_btn.pack(pady=5)

create_toggle("clothing", "Clothing")
create_toggle("places", "Places")
create_toggle("accessories", "Accessories")
create_toggle("other", "Other")

threading.Thread(target=scan_random_ids, daemon=True).start()

root.mainloop()
import requests
import random
import time
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import datetime

ROBLOSECURITY_COOKIE = ""
DISCORD_WEBHOOK_URL = ""
#Paste your .ROBLOSECURITY cookie and discord webhook here

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
    "other": "roblox_old_other.txt",
    "for_sale": "roblox_old_forsale.txt"
}

DELAY_BETWEEN_REQUESTS = 0.1  # Increase to 0.5 if rate limited
RATE_LIMIT_BACKOFF = 0.5

CLOTHING_TYPES = [2, 11, 12, 18]
PLACE_TYPES = [9]
ACCESSORY_TYPES = [8, 19, 41, 42, 43, 44, 45, 46, 47]

YEAR_RANGES_ALL = {
    2007: (0, 2_000_000),
    2008: (2_000_001, 5_000_000),
    2009: (5_000_001, 20_000_000),
    2010: (20_000_001, 40_000_000),
    2011: (40_000_001, 70_000_000),
    2012: (70_000_001, 100_000_000),
    2013: (100_000_001, 120_000_000),
    2014: (120_000_001, 150_000_000),
    #150M+ is 2015
    #140-150M is 2014
    #100-120M is 2013
    #70-100M is 2012
    #40-70M is 2011
    #20-40M is 2010
    #5-20M is 2009
    #-5M is 2008
    #-2M is 2007

}

#These ranges have higher clothes density. So you get more clothes and less places/decals ect.
CLOTHING_FOCUSED_RANGES = {
    2007: [(500_000, 1_000_000), (1_200_000, 1_800_000)],
    2008: [(3_500_000, 4_700_000)],
    2009: [(8_000_000, 14_000_000), (16_000_000, 19_000_000)],
    2010: [(21_000_000, 28_000_000), (33_000_000, 38_000_000)],
    2011: [(44_000_000, 65_000_000)],
    2012: [(73_000_000, 82_000_000), (88_000_000, 100_000_000)],
    2013: [(106_000_000, 122_000_000), (125_000_000, 140_000_000)],
    2014: [(140_000_000, 148_000_000)]
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
    "skipped": 0,
    "found_clothing": 0,
    "found_places": 0,
    "found_accessories": 0,
    "found_other": 0,
    "found_for_sale": 0,
    "rate_limited": 0,
    "authenticated": bool(ROBLOSECURITY_COOKIE)
}

scan_filters = {
    "clothing": True,
    "places": True,
    "accessories": True,
    "other": True
}

clothing_only_mode = False
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
            return f"Resale: {resale_price} R$", True
    
    if price_robux is None or price_robux == 0:
        if is_for_sale:
            return "FREE", True
        else:
            return "Off-Sale (was 0 robux)", False
    
    status = "Limited" if is_limited else "Limited U" if is_limited_unique else "For Sale"
    if is_for_sale:
        return f"{price_robux} R$ ({status})", True
    return f"Off-Sale (was {price_robux} R$)", False


# def send_discord_message(asset_id, name, asset_type_name, price_info, category, is_for_sale):
#     if not discord_enabled or not DISCORD_WEBHOOK_URL:
#         return
#     try:
#         data = {
#             "content": f"New Roblox {category.title()} Found!\n"
#                       f"**ID:** {asset_id}\n"
#                       f"**Name:** {name}\n"
#                       f"**Type:** {asset_type_name}\n"
#                       f"**Price:** {price_info}\n"
#                       f"**Status:** {'FOR SALE!' if is_for_sale else 'Off-Sale'}"
#         }
#         requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=5)
#     except:
#         pass


def scan_asset(asset_id):
    global current_delay
    
    try:
        stats["scanned"] += 1
        
        url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
        response = requests.get(url, headers=headers, timeout=5)
        
        if stats["scanned"] % 100 == 0:
            log_message(f"[PROGRESS] Scanned: {stats['scanned']} | Delay: {current_delay:.1f}s")
        
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
        
        if not scan_filters.get(category, True):
            stats["skipped"] += 1
            update_stats()
            return
        
        price_info, is_for_sale = get_price_info(data)

        message = (f"[FOUND - {category.upper()}] ID: {asset_id} | Name: {name} | "
                  f"Type: {asset_type_name} | Price: {price_info} | Created: {created}")
        log_message(message)
        
        stats[f"found_{category}"] += 1
        
        if is_for_sale:
            stats["found_for_sale"] += 1
        
        update_stats()
        
        # Write to file if enabled
        output_file = OUTPUT_FILES[category]
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{asset_id} | {name} | {asset_type_name} | {price_info} | {created}\n")
        
        if is_for_sale:
            with open(OUTPUT_FILES["for_sale"], "a", encoding="utf-8") as f:
                f.write(f"{asset_id} | {name} | {asset_type_name} | {price_info} | {created}\n")
        
#       send_discord_message(asset_id, name, asset_type_name, price_info, is_for_sale)
        
    except Exception as e:
        log_message(f"[ERROR] ID: {asset_id} | {type(e).__name__}: {e}")
        update_stats()

# Generates random id based on the scan mode
def get_random_asset_id():
    year = random.randint(2007, 2014)
    
    if clothing_only_mode:
        ranges = CLOTHING_FOCUSED_RANGES[year]
        chosen_range = random.choice(ranges)
        return random.randint(chosen_range[0], chosen_range[1])
    else:
        start, end = YEAR_RANGES_ALL[year]
        return random.randint(start, end)


def scan_random_ids():
    if not ROBLOSECURITY_COOKIE:
        log_message("WARNING: No cookie provided - expect rate limits!\n")
    else:
        log_message("Running with authentication\n")
    
    log_message("🔍 Scanner started! Searching 2007-2014 items...\n")

    while True:
        asset_id = get_random_asset_id()
        scan_asset(asset_id)
        
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
    
    mode = "CLOTHING FOCUS" if clothing_only_mode else "ALL TYPES"
    
    stats_label.config(
        text=f"{auth} | Mode: {mode} | Scanned: {stats['scanned']} | Skipped: {stats['skipped']} | "
             f"Clothing: {stats['found_clothing']} | Places: {stats['found_places']} | "
             f"Accessories: {stats['found_accessories']} | Other: {stats['found_other']} | "
             f"For Sale: {stats['found_for_sale']} | Rate Limited: {stats['rate_limited']} | {rate:.1f} scans/sec"
    )


def create_toggle(category, text):
    def toggle():
        scan_filters[category] = not scan_filters[category]
        status = "ON" if scan_filters[category] else "OFF"
        btn.config(
            text=f"{text}: {status}",
            bg="lightgreen" if scan_filters[category] else "lightcoral"
        )
        
        if scan_filters[category]:
            log_message(f"Now scanning {text}")
        else:
            log_message(f"Skipping {text}")
        
        update_stats()
    
    btn = tk.Button(
        root, 
        text=f"{text}: ON", 
        command=toggle,
        bg="lightgreen",
        width=15
    )
    btn.pack(pady=2)
    return btn


def toggle_discord():
    global discord_enabled
    discord_enabled = not discord_enabled
    discord_btn.config(
        text=f"Discord: {'ON' if discord_enabled else 'OFF'}",
        bg="lightgreen" if discord_enabled else "lightcoral"
    )


def toggle_clothing_focus():
    global clothing_only_mode
    clothing_only_mode = not clothing_only_mode
    
    if clothing_only_mode:
        log_message("\nCLOTHING FOCUS MODE ENABLED")
        log_message("   → Scanning ID ranges with higher clothing density")
        log_message("   → Should find more clothing, fewer places/models\n")
        clothing_focus_btn.config(
            text="Clothing Focus: ON",
            bg="gold"
        )
    else:
        log_message("\nALL TYPES MODE")
        log_message("   → Scanning all ID ranges equally\n")
        clothing_focus_btn.config(
            text="Clothing Focus: OFF",
            bg="lightgray"
        )
    
    update_stats()


# Main controls
discord_btn = tk.Button(
    root, 
    text="Discord: ON", 
    command=toggle_discord,
    bg="lightgreen",
    width=15
)
discord_btn.pack(pady=5)

clothing_focus_btn = tk.Button(
    root,
    text="Clothing Focus: OFF",
    command=toggle_clothing_focus,
    bg="lightgray",
    width=15,
    font=("Arial", 10, "bold")
)
clothing_focus_btn.pack(pady=5)

info_label = tk.Label(
    root, 
    text="Clothing Focus scans ID ranges with more clothing items",
    font=("Arial", 9),
    fg="gray"
)
info_label.pack(pady=2)

create_toggle("clothing", "Clothing")
create_toggle("places", "Places")
create_toggle("accessories", "Accessories")
create_toggle("other", "Other")

threading.Thread(target=scan_random_ids, daemon=True).start()

root.mainloop()
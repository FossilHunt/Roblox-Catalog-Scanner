import requests
import random
import time
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import datetime

# PROXY LIST - format: IP:PORT:USERNAME:PASSWORD
RAW_PROXIES = """
31.59.20.176:6754:bpjsqruu:56truchixkgq
23.95.150.145:6114:bpjsqruu:56truchixkgq
198.23.239.134:6540:bpjsqruu:56truchixkgq
45.38.107.97:6014:bpjsqruu:56truchixkgq
198.105.121.200:6462:bpjsqruu:56truchixkgq
64.137.96.74:6641:bpjsqruu:56truchixkgq
216.10.27.159:6837:bpjsqruu:56truchixkgq
23.229.19.94:8689:bpjsqruu:56truchixkgq
""".strip()

def parse_proxies(raw):
    proxies = []
    for line in raw.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split(':')
        if len(parts) == 4:
            ip, port, user, password = parts
            proxy_url = f"http://{user}:{password}@{ip}:{port}"
            proxies.append({
                "http": proxy_url,
                "https": proxy_url,
                "label": f"{ip}:{port}"
            })
    return proxies

class ProxyPool:
    def __init__(self, proxies):
        self.proxies = proxies.copy()
        self.lock = threading.Lock()
        self.index = 0

    def get_next(self):
        with self.lock:
            if not self.proxies:
                return None
            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            return proxy

    def mark_dead(self, proxy):
        with self.lock:
            if proxy in self.proxies:
                self.proxies.remove(proxy)

    def count(self):
        with self.lock:
            return len(self.proxies)

proxy_pool = ProxyPool(parse_proxies(RAW_PROXIES))

ROBLOSECURITY_COOKIE = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_CAEaAhADIhsKBGR1aWQSEzk1NDE2ODkxNDA3MzYxMDcwNTYoAw.H69XLh1s7C7-8Mk1r05enpWkI1OwiUVHJAowuP39PBTeuU74SA-jQg6Me7gbv179YGnYOldhsQqH3vQrEHHFN6JyLKj83FeDytkDOcNN0SaKtrmJ9dYLT1Q3DtDTafInUQInrWsPgQ1aJqKqpoGxMdMT0AlMl4egHzKshr4R3fVi-5bsTOFi0m_QZDyQKS_u5PM-O3nWTxzA629tFkq6sfbqJoh1pX1Oc2oi0NzLP34khPKta2kVO3XJPd0v8mZwjS7XRngfUxwk9WFO6BUXgXP14693u2Mg2f5GQ8EVlZPBPIo9OuTvEoEka9_WwaJIcsN2CQdWrb9cCoQboLXDfgjG-Df1SiqoocEnr1ilxxtzrWN2ETeGxyCPbOP1QaElbCJgo6qC_5WyKd9rYLAHx-O46U7fUpED7hUMpbuLSbeLRGEEXCv6LoOiaT58-Slxjp53JKsfOwGvb38Z73OCksNips0IdMwtThc8ZfVp6woDlxqER0BLO5BBMufiX95mFdtTDx98cs_uppsxBHPe841EzOLRj-A-s-BolRvO5fMrrSiEsYb7FWO4Ybv5bK2biA3Jt_Cs51sZKUXF1Z98WUHZ2xIeE_ap5ck1yeZsLUx5LMEcjHDaLTn6NLTEU4xt1so1gLmmB5S6glo5gOvXQfvzCGi2w91pPkj38wbDpgCEqRjJHMASFkKtaNUq29rM-BDfTnstF5UZPYpvl9zTsJfjSPkZaDHZtBclPGN6oZmJBZ9mfdewraBqcUZxDmNt1OidPCQBkDmbRu1KJlafW0m0rKXXcGj0SzxRfIci9O-w-EUq"
DISCORD_WEBHOOK_URL = ""

# Threads being used - 1 per proxy
THREAD_COUNT = len(parse_proxies(RAW_PROXIES))  

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

# File write lock to prevent corruption
file_lock = threading.Lock()

DELAY_BETWEEN_REQUESTS = 0.1
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
}

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

base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.roblox.com/",
    "Origin": "https://www.roblox.com",
    "Cookie": f".ROBLOSECURITY={ROBLOSECURITY_COOKIE}" if ROBLOSECURITY_COOKIE else ""
}

stats_lock = threading.Lock()
stats = {
    "scanned": 0,
    "skipped": 0,
    "found_clothing": 0,
    "found_places": 0,
    "found_accessories": 0,
    "found_other": 0,
    "found_for_sale": 0,
    "rate_limited": 0,
    "proxy_errors": 0,
    "authenticated": bool(ROBLOSECURITY_COOKIE)
}

def increment_stat(key, amount=1):
    with stats_lock:
        stats[key] += amount

scan_filters = {
    "clothing": True,
    "places": True,
    "accessories": True,
    "other": True
}

time_period_filters = {
    "OG": True,    # 2007-2008
    "early": True, # 2009-2010
    "late": True   # 2011-2014
    }
clothing_only_mode = False
discord_enabled = True
scan_start_time = datetime.datetime.now()

thread_delays = {}
thread_delays_lock = threading.Lock()

def get_thread_delay(thread_id):
    with thread_delays_lock:
        return thread_delays.get(thread_id, DELAY_BETWEEN_REQUESTS)

def set_thread_delay(thread_id, delay):
    with thread_delays_lock:
        thread_delays[thread_id] = delay


def get_asset_type_name(asset_type_id):
    return ASSET_TYPE_NAMES.get(asset_type_id, f"Unknown ({asset_type_id})")

def get_asset_category(asset_type_id):
    if asset_type_id in CLOTHING_TYPES: return "clothing"
    elif asset_type_id in PLACE_TYPES: return "places"
    elif asset_type_id in ACCESSORY_TYPES: return "accessories"
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
        return ("FREE", True) if is_for_sale else ("Off-Sale (was 0 robux)", False)
    status = "Limited" if is_limited else "Limited U" if is_limited_unique else "For Sale"
    return (f"{price_robux} R$ ({status})", True) if is_for_sale else (f"Off-Sale (was {price_robux} R$)", False)

def get_random_asset_id():
    available_years = []
    if time_period_filters["OG"]: available_years.extend([2007, 2008])
    if time_period_filters["early"]: available_years.extend([2009, 2010])
    if time_period_filters["late"]: available_years.extend([2011, 2012, 2013, 2014])
    if not available_years: available_years = list(range(2007, 2015))
    year = random.choice(available_years)
    if clothing_only_mode:
        ranges = CLOTHING_FOCUSED_RANGES[year]
        r = random.choice(ranges)
        return random.randint(r[0], r[1])
    else:
        start, end = YEAR_RANGES_ALL[year]
        return random.randint(start, end)

def write_to_file(filename, line):
    """Thread-safe file writing"""
    with file_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def scan_worker(thread_id, proxy):
    """
    Each thread runs its OWN scanning loop with its OWN proxy
    This means 10 proxies = 10 simultaneous requests = ~10x speed
    """
    set_thread_delay(thread_id, DELAY_BETWEEN_REQUESTS)
    proxy_label = proxy["label"] if proxy else "Direct"

    log_message(f"[THREAD {thread_id}] Started | Proxy: {proxy_label}")

    while True:
        try:
            asset_id = get_random_asset_id()
            url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"

            delay = get_thread_delay(thread_id)

            if proxy:
                response = requests.get(url, headers=base_headers, proxies=proxy, timeout=8)
            else:
                response = requests.get(url, headers=base_headers, timeout=5)

            increment_stat("scanned")

            if response.status_code == 429:
                # Proxy is rate limited
                increment_stat("rate_limited")
                new_delay = min(delay + RATE_LIMIT_BACKOFF, 5.0)
                set_thread_delay(thread_id, new_delay)
                log_message(f"[THREAD {thread_id}] Rate limited | Delay: {new_delay:.1f}s")
                time.sleep(new_delay * 2)
                continue

            if response.status_code == 401:
                log_message(f"[THREAD {thread_id}] Auth error - cookie expired!")
                with stats_lock:
                    stats["authenticated"] = False
                time.sleep(5)
                continue

            if response.status_code == 200:
                # Success - slowly reduce delay back to minimum
                new_delay = max(delay * 0.98, DELAY_BETWEEN_REQUESTS)
                set_thread_delay(thread_id, new_delay)

            if response.status_code != 200:
                time.sleep(delay * random.uniform(0.7, 1.3))
                continue

            data = response.json()
            if "errors" in data or not data.get("Name") or not data.get("AssetTypeId"):
                time.sleep(delay * random.uniform(0.7, 1.3))
                continue

            name = data["Name"]
            asset_type_id = data["AssetTypeId"]
            created = data.get("Created", "")
            asset_type_name = get_asset_type_name(asset_type_id)
            category = get_asset_category(asset_type_id)

            if not scan_filters.get(category, True):
                increment_stat("skipped")
                time.sleep(delay * random.uniform(0.7, 1.3))
                continue

            price_info, is_for_sale = get_price_info(data)

            log_message(f"[T{thread_id}] FOUND: {name} | {asset_type_name} | {price_info}")

            increment_stat(f"found_{category}")
            if is_for_sale:
                increment_stat("found_for_sale")

            write_to_file(OUTPUT_FILES[category],
                         f"{asset_id} | {name} | {asset_type_name} | {price_info} | {created}")

            if is_for_sale:
                write_to_file(OUTPUT_FILES["for_sale"],
                             f"{asset_id} | {name} | {asset_type_name} | {price_info} | {created}")

            update_stats()
            time.sleep(delay * random.uniform(0.7, 1.3))

        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            increment_stat("proxy_errors")
            if proxy:
                log_message(f"[THREAD {thread_id}] Proxy error - retrying in 3s")
            time.sleep(3)
            continue

        except Exception as e:
            time.sleep(1)
            continue


def start_all_threads():
    """Start one thread per proxy"""
    proxies = parse_proxies(RAW_PROXIES)

    log_message(f"Starting {len(proxies)} threads (1 per proxy)...")
    log_message(f"Expected speed: ~{len(proxies) * 2:.0f}-{len(proxies) * 3:.0f} scans/sec\n")

    for i, proxy in enumerate(proxies, 1):
        t = threading.Thread(
            target=scan_worker,
            args=(i, proxy),
            daemon=True
        )
        t.start()
        time.sleep(0.2)

    t = threading.Thread(
        target=scan_worker,
        args=(0, None),  # Thread 0 = no proxy, direct connection
        daemon=True
    )
    t.start()

    log_message(f"All {len(proxies) + 1} threads running!\n")


# GUI
root = tk.Tk()
root.title("Roblox Catalog Scanner - By FossilHunter")

text_area = ScrolledText(root, width=120, height=25)
text_area.pack(padx=10, pady=10)

stats_label = tk.Label(root, text="Starting...", font=("Arial", 10))
stats_label.pack(pady=5)

def log_message(message):
    try:
        text_area.insert(tk.END, message + "\n")
        text_area.see(tk.END)
    except:
        pass

def update_stats():
    try:
        elapsed = (datetime.datetime.now() - scan_start_time).total_seconds()
        rate = stats['scanned'] / elapsed if elapsed > 0 else 0
        auth = "✓" if stats["authenticated"] else "✗"
        periods = []
        if time_period_filters["OG"]: periods.append("07-08")
        if time_period_filters["early"]: periods.append("09-10")
        if time_period_filters["late"]: periods.append("11-14")

        stats_label.config(
            text=f"{auth}Auth | Threads: {THREAD_COUNT+1} | Proxies: {proxy_pool.count()} | "
                 f"Scanned: {stats['scanned']} | Skip: {stats['skipped']} | "
                 f"Clothing: {stats['found_clothing']} | ForSale: {stats['found_for_sale']} | "
                 f"Accessories: {stats['found_accessories']} | Other: {stats['found_other']} | "
                 f"RateLimit: {stats['rate_limited']} | ProxyErr: {stats['proxy_errors']} | "
                 f"{rate:.1f}/sec"
        )
    except:
        pass

def create_toggle(category, text):
    def toggle():
        scan_filters[category] = not scan_filters[category]
        btn.config(text=f"{text}: {'ON' if scan_filters[category] else 'OFF'}",
                   bg="lightgreen" if scan_filters[category] else "lightcoral")
        update_stats()
    btn = tk.Button(root, text=f"{text}: ON", command=toggle, bg="lightgreen", width=15)
    btn.pack(pady=2)
    return btn

def toggle_clothing_focus():
    global clothing_only_mode
    clothing_only_mode = not clothing_only_mode
    clothing_focus_btn.config(
        text=f"Clothing Focus: {'ON' if clothing_only_mode else 'OFF'}",
        bg="gold" if clothing_only_mode else "lightgray"
    )

def toggle_time_period(period, period_name):
    time_period_filters[period] = not time_period_filters[period]
    if not any(time_period_filters.values()):
        time_period_filters[period] = True
        return
    btn = early_years_btn if period == "early" else late_years_btn if period == "late" else og_years_btn
    btn.config(text=f"{period_name}: {'ON' if time_period_filters[period] else 'OFF'}",
               bg="lightblue" if time_period_filters[period] else "lightcoral")
    update_stats()

clothing_focus_btn = tk.Button(root, text="Clothing Focus: OFF", command=toggle_clothing_focus,
                               bg="lightgray", width=15, font=("Arial", 10, "bold"))
clothing_focus_btn.pack(pady=5)

tk.Label(root, text="────── Time Periods ──────", font=("Arial", 9), fg="gray").pack(pady=5)
og_years_btn = tk.Button(root, text="2007-2010: ON",
                            command=lambda: toggle_time_period("early", "2007-2010"),
                            bg="lightgreen", width=15)
og_years_btn.pack(pady=2)
early_years_btn = tk.Button(root, text="2007-2010: ON",
                            command=lambda: toggle_time_period("early", "2007-2010"),
                            bg="lightgreen", width=15)
early_years_btn.pack(pady=2)
late_years_btn = tk.Button(root, text="2011-2014: ON",
                           command=lambda: toggle_time_period("late", "2011-2014"),
                           bg="lightgreen", width=15)
late_years_btn.pack(pady=2)

tk.Label(root, text="────── Item Types ──────", font=("Arial", 9), fg="gray").pack(pady=5)
create_toggle("clothing", "Clothing")
create_toggle("places", "Places")
create_toggle("accessories", "Accessories")
create_toggle("other", "Other")

# Start all threads
threading.Thread(target=start_all_threads, daemon=True).start()

# Stats update loop
def stats_loop():
    while True:
        update_stats()
        time.sleep(0.5)

threading.Thread(target=stats_loop, daemon=True).start()

root.mainloop()
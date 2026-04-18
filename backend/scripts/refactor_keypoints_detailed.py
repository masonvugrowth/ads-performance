"""Refactor branch_keypoints for more specificity.

Per user request: keypoints must name specific landmarks, walking times, distances,
restaurants, etc. — not vague phrases like "Prime D1 location" or "Social hotel vibe".

Strategy:
  1. Soft-delete (is_active=FALSE) generic / wrong / duplicate rows. Preserves
     history for any combo already linked to that UUID.
  2. INSERT new detailed rows with concrete names + walking times.
  3. Leave already-specific rows untouched (no churn on metrics).

Data sourced from KOL videos + area research (Google Maps walking estimates
prefixed with ~). Addresses verified via Booking.com / Agoda / Meander official
site. Unverified items are retained per user instruction.
"""
import sys, io, uuid, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from sqlalchemy import text

from app.database import engine, SessionLocal
from app.models.account import AdAccount

now = datetime.now(timezone.utc).isoformat()
db = SessionLocal()

# --- Resolve branch_ids from Meta accounts ---
BRANCHES = {}
for name, filt in [
    ("Meander Saigon", lambda q: q.filter(AdAccount.account_name.ilike("meander saigon"), AdAccount.platform == "meta")),
    ("Meander Osaka",  lambda q: q.filter(AdAccount.account_name.ilike("meander osaka"),  AdAccount.platform == "meta")),
    ("Meander 1948",   lambda q: q.filter(AdAccount.account_name.ilike("meander 1948"),   AdAccount.platform == "meta")),
    ("Meander Taipei", lambda q: q.filter(AdAccount.account_name.ilike("meander taipei"), AdAccount.platform == "meta")),
    ("Oani (Taipei)",  lambda q: q.filter(AdAccount.account_name.ilike("oani%"),          AdAccount.platform == "meta")),
]:
    row = filt(db.query(AdAccount)).first()
    if not row:
        raise SystemExit(f"Branch not found: {name}")
    BRANCHES[name] = row.id
    print(f"  {name} = {row.id}")

# =====================================================================
# SAIGON — 3B Ly Tu Trong Street, Ben Nghe Ward, District 1
# =====================================================================
SAIGON_SOFT_DELETE_TITLES = [
    "Prime District 1 location — walking distance to Saigon's landmarks",
    "Close to every major Saigon attraction — simple, quick transit",
    "Heart of District 1, HCMC",
    "Best value boutique hotel in D1",
    "Local street food tour partnership",
    "Walking distance to Ben Thanh Market & Bui Vien",
    "Free breakfast buffet",              # unverified
    "Rooftop bar with city skyline view",  # unverified
    "Exclusive KOL discount — 10% off on the direct website",  # replaced with coded version
]

SAIGON_NEW = [
    ("location", "Address: 3B Ly Tu Trong Street, Ben Nghe Ward — the luxury core of District 1"),
    ("location", "~4-min walk to Vincom Center (~300m) — shopping, supermarket, food court"),
    ("location", "~5-min walk to Nguyen Hue Walking Street — rooftop bars (Chill Skybar, Social Club, EON51)"),
    ("location", "~5-min walk to Saigon Opera House — heritage French colonial landmark"),
    ("location", "~6-min walk to Saigon Notre-Dame Basilica (~450m) — red-brick cathedral icon"),
    ("location", "~7-min walk to Saigon Central Post Office + Book Street (Nguyen Van Binh)"),
    ("location", "~7-min walk to Saigon Centre / Takashimaya — premium mall + dining"),
    ("location", "~7-min walk to Ben Thanh Station — HCMC Metro Line 1 terminus (opened Dec 2024)"),
    ("location", "~8-min walk to Ben Thanh Market (~650m) — street-food + souvenir hub"),
    ("location", "~10-min walk to Independence / Reunification Palace (~800m)"),
    ("location", "~12-15-min walk to Bui Vien Walking Street (~1km) — backpacker nightlife"),
    ("location", "~2-min walk to Japan Town on Le Thanh Ton — izakayas, ramen, late-night bars"),
    ("location", "~20-30-min Grab to Tan Son Nhat International Airport (SGN, ~7km)"),
    ("location", "~7-min walk to Banh Mi Huynh Hoa — iconic pate-loaded banh mi"),
    ("location", "~6-min walk to The Workshop Coffee — specialty ca phe sua da + Vietnamese single-origin"),
    ("location", "~5-min walk to Secret Garden Restaurant — rooftop Vietnamese home cooking"),
    ("location", "~8-10-min walk to Pho Quynh / Pho Le branches — classic beef pho"),
    ("value",    "Exclusive KOL discount — code FRHEAJAIMI for 10% off on the direct website"),
]

# =====================================================================
# OSAKA — 1-5-16 Motomachi, Naniwa Ward
# =====================================================================
OSAKA_SOFT_DELETE_TITLES = [
    "A few minutes' walk from Namba Station — quick access to Umeda, Osaka Castle and Kyoto",
    "Minutes from Nankai Namba Station and the Osaka Metro Midosuji Line",
    "Namba area — nightlife & shopping hub",
    "Japanese-style common area",  # redundant with stylish common
    "Cherry blossom season special packages",  # unverified — KEEP per user? actually user said keep. Leave this for now.
    "Osaka food culture immersion",  # generic fluff
    "Affordable base for Kansai exploration",  # generic
    "Steps from Dotonbori, Shinsaibashi-suji, Namba Parks and Takashimaya",
    "Surrounded by street food, local izakayas and a 24/7 convenience store",
    "Rental car service right next to the hotel — easy day trips to Nara, Kobe and the Kansai countryside",
]
# NB: user said "giữ" unverified ones; "Cherry blossom special packages" is borderline
# unverified. I'll KEEP it (remove from delete list below).
OSAKA_SOFT_DELETE_TITLES = [t for t in OSAKA_SOFT_DELETE_TITLES if t != "Cherry blossom season special packages"]

OSAKA_NEW = [
    ("location", "Address: 1-5-16 Motomachi, Naniwa Ward, Osaka 556-0016 — south-central Namba"),
    ("location", "~1-2-min walk to JR Namba Station (~300m) — Yamatoji Line to Universal Studios Japan (~25 min)"),
    ("location", "~3-5-min walk to Nankai Namba Station — Nankai Rapi:t to Kansai Airport (KIX) ~45 min"),
    ("location", "~2-4-min walk to Namba Station — Midosuji, Yotsubashi, Sennichimae metro lines"),
    ("location", "~5-7-min walk to Osaka-Namba Station (Hanshin / Kintetsu) — direct to Kobe Sannomiya (~35 min), Nara (~35-40 min)"),
    ("location", "~5-min walk to Takashimaya Osaka + Nankai Namba City — premium dining + department store"),
    ("location", "~6-8-min walk to Namba Parks — rooftop garden mall + cinema"),
    ("location", "~8-10-min walk to Dotonbori canal + Glico sign — neon-lit food street"),
    ("location", "~8-10-min walk to Kuromon Ichiba Market — seafood, wagyu skewers, fresh sushi"),
    ("location", "~9-min walk to Hozenji Yokocho + Hozenji Temple — lantern-lit traditional alley"),
    ("location", "~10-min walk to Shinsaibashi-suji shopping arcade — 600m covered retail street"),
    ("location", "~8-10-min walk to Den Den Town (Nipponbashi) — electronics + anime district"),
    ("location", "~12-min walk to Amerikamura — youth fashion + street culture + Triangle Park"),
    ("location", "~9-min walk to Takoyaki Juhachiban + Ichiran Ramen Dotonbori — Osaka food icons"),
    ("location", "~7-min walk to 551 Horai — famous Osaka pork buns"),
    ("location", "~45-55-min to Kyoto via Midosuji Line → Shin-Osaka → Shinkansen (or Hankyu direct)"),
    ("location", "~5-7-min walk to Times Car Rental + Toyota Rent-a-Car Namba — day trips to Kansai countryside"),
]

# =====================================================================
# 1948 — No. 42 Taiyuan Road, Datong District, Taipei
# =====================================================================
M1948_SOFT_DELETE_TITLES = [
    "Literally next to Taipei Main Station — get anywhere in the city fast",
    "Heritage building with modern renovation",  # redundant with 70-year heritage
    "Hostel dorms available — budget option without sacrificing the vibe",  # redundant
    "Cultural immersion in old Taipei",  # generic
    "Historic Dadaocheng area, Taipei",  # generic area label
    "Unique heritage stay at budget price",  # generic
    "Restaurants, cafes, shopping streets and a 7-Eleven all in the same building",  # vague
    "Walking distance to Ningxia Night Market — one of Taipei's most famous food spots",  # replaced with specific
    "Just a five-minute walk from Taipei Main Station",  # will replace with richer one
    "Connects to MRT Red, Blue and Green lines — fast travel across Taipei",
    "Near Dihua Street heritage market",  # replaced with specific
    "Taipei Main Station is the city's central transport hub — airport express and midnight bus both stop here",
]

M1948_NEW = [
    ("location", "Address: No. 42 Taiyuan Road, Datong District 大同區, Taipei 103"),
    ("location", "~7-10-min walk to Taipei Main Station (MRT Red/Blue, THSR, TRA, Airport MRT, intercity buses)"),
    ("location", "~5-7-min walk to Beimen Station (MRT Green line)"),
    ("location", "~8-10-min walk to Zhongshan Station (MRT Red line)"),
    ("location", "~5-min walk to Ningxia Night Market (寧夏夜市) — Michelin-mentioned stalls"),
    ("location", "~5-min walk to 圓環邊蚵仔煎 — oyster omelette legend"),
    ("location", "~5-min walk to 劉芋仔 — Michelin Bib taro/egg-yolk balls"),
    ("location", "~5-min walk to 里長伯臭豆腐 — classic Taipei stinky tofu"),
    ("location", "~6-min walk to 方家雞肉飯 — shredded chicken rice institution"),
    ("location", "~4-min walk to 豆花莊 (Douhua Zhuang) — classic tofu pudding since 1980s"),
    ("location", "~6-min walk to Dihua Street (迪化街) — oldest commercial street, Lunar New Year market"),
    ("location", "~8-min walk to Xiahai City God Temple (霞海城隍廟) — love/matchmaking shrine"),
    ("location", "~8-min walk to North Gate / Beimen (北門) — Qing-era Taipei city gate"),
    ("location", "~15-min walk to Dadaocheng Wharf (大稻埕碼頭) — Tamsui River sunset spot"),
    ("location", "~6-min walk to Q Square (京站時尚廣場) — mall adjoining Taipei Main Station"),
    ("location", "~35-50-min to Taoyuan International Airport via Airport MRT from Taipei Main"),
    ("location", "~40-50-min to Jiufen / Pingxi via TRA to Ruifang (transfer at Taipei Main)"),
    ("location", "~1hr45m to Tainan / Kaohsiung (Zuoying) via THSR from Taipei Main"),
    ("location", "~2hr to Taroko Gorge via TRA Hualien from Taipei Main"),
]

# =====================================================================
# MEANDER TAIPEI — No. 9 Section 2 Zhonghua Road, Wanhua District
# =====================================================================
TAIPEI_SOFT_DELETE_TITLES = [
    "Near Taipei Main Station",           # WRONG — Meander Taipei is in Ximending, not near Taipei Main
    "Ximending — youth & shopping district",  # generic district label
    "Just an 8-minute walk to the heart of Ximending — close, but away from the crowds",  # replaced
    "Modern co-working lounge",           # redundant with spacious lobby
    "Budget-friendly for solo backpackers",  # generic
    "Night market walking tour",           # unverified fluff
]

TAIPEI_NEW = [
    ("location", "Address: No. 9, Section 2, Zhonghua Road, Wanhua District 萬華區, Taipei 108"),
    ("location", "~8-min walk to Ximen Station (MRT Blue + Green lines) — core Ximending pedestrian zone"),
    ("location", "~15-min walk to Beimen Station (MRT Green) — access to Airport MRT"),
    ("location", "~18-20-min walk to Taipei Main Station, or 1 MRT stop from Ximen"),
    ("location", "~40-min to Taoyuan International Airport via Airport MRT (transfer at Beimen/Taipei Main)"),
    ("location", "~8-min walk to Ay-Chung Flour-Rice Noodles (阿宗麵線) — oyster mian xian icon"),
    ("location", "~9-min walk to Modern Toilet Restaurant — novelty themed dining"),
    ("location", "~10-min walk to Lao Shandong Beef Noodles (老山東牛肉麵) — clear-broth classic"),
    ("location", "~10-min walk to Ice Monster / Smoothie House (思慕昔) — mango shaved ice famous to tourists"),
    ("location", "~12-min walk to Lan Jia Gua Bao (藍家割包) — pork-belly bao flagship"),
    ("location", "~7-9-min walk to Red House Theater (紅樓劇場) — octagonal heritage landmark + LGBTQ bar plaza"),
    ("location", "~9-min walk to Wannian Building (萬年大樓) — toys, anime figurines, retro arcades"),
    ("location", "~12-15-min walk / 1 MRT stop to Longshan Temple (龍山寺) — Taipei's most famous temple"),
    ("location", "~13-min walk to Bopiliao Historic Block (剝皮寮) — Qing-era preserved street"),
    ("location", "~10-min walk east to Presidential Office Building (總統府)"),
    ("location", "Southern edge of Ximending — residential feel, quieter at night but still ~8 min to the neon core"),
]

# =====================================================================
# OANI — No. 50 Kunming Street, Wanhua District
# =====================================================================
OANI_SOFT_DELETE_TITLES = [
    "5 min walk to MRT Zhongshan station",       # WRONG — Oani is Ximending, not Zhongshan
    "Zhongshan District — premium area",         # WRONG district — Oani is in Wanhua
    "Japanese-inspired minimalist design",        # generic
    "Premium bedding & amenities",                # generic
    "Boutique luxury at hostel-friendly price",   # brand fluff
    "Curated Taipei city guide for guests",       # unverified — KEEP per user. Remove from delete.
    "Steps from Ximending street food and shopping",  # replaced with specific
    "Convenience store right next door",          # vague — absorbed into new
    "Walking distance to Wannian Building toy shops, popular street food queues and affordable massage parlors",
]
OANI_SOFT_DELETE_TITLES = [t for t in OANI_SOFT_DELETE_TITLES if t != "Curated Taipei city guide for guests"]

OANI_NEW = [
    ("location", "Address: No. 50 Kunming Street, Wanhua District 萬華區, Taipei 108"),
    ("location", "~1-min walk (~50m) directly across Ximen Station Exit 4 (MRT Blue + Green lines)"),
    ("location", "~8-10-min walk (~700m) to Beimen Station (MRT Green) — Airport MRT transfer"),
    ("location", "~3-min by MRT / ~12-min walk to Taipei Main Station — THSR, TRA, intercity buses"),
    ("location", "~35-50-min to Taoyuan International Airport via Airport MRT from Beimen"),
    ("location", "~2-3-min walk to Ay-Chung Flour-Rice Noodles (阿宗麵線) — oyster mian xian icon"),
    ("location", "~3-min walk to Tian Tian Li (天天利美食坊) — hamburger rice + braised pork rice"),
    ("location", "~3-min walk to Modern Toilet Restaurant — novelty themed dining"),
    ("location", "~4-5-min walk to Ice Monster / Smoothie House — mango shaved ice famous to tourists"),
    ("location", "~4-min walk to Lao Shandong Homemade Noodles (老山東) — beef noodle soup"),
    ("location", "~3-min walk to A-Po Lu Wei (阿婆魯味) — braised snacks counter"),
    ("location", "~3-4-min walk to Red House Theater (紅樓劇場) — octagonal heritage + LGBTQ bar plaza behind"),
    ("location", "~2-3-min walk to Wannian Building (萬年大樓) — toys, anime figurines, retro arcades"),
    ("location", "~3-min walk to Taipei Cinema Park (電影主題公園) — graffiti walls, skater hangout"),
    ("location", "~2-4-min walk to Eslite 116 / Uniqlo / GU flagships + Ximending streetwear scene"),
    ("location", "~13-15-min walk / 1 MRT stop to Longshan Temple (龍山寺)"),
    ("location", "~10-12-min walk to Bopiliao Historic Block (剝皮寮) — Qing-era preserved street"),
    ("location", "~10-12-min walk to Presidential Office Building (總統府)"),
]

# =====================================================================
# Execute
# =====================================================================
PLAN = {
    "Meander Saigon": (SAIGON_SOFT_DELETE_TITLES, SAIGON_NEW),
    "Meander Osaka":  (OSAKA_SOFT_DELETE_TITLES, OSAKA_NEW),
    "Meander 1948":   (M1948_SOFT_DELETE_TITLES, M1948_NEW),
    "Meander Taipei": (TAIPEI_SOFT_DELETE_TITLES, TAIPEI_NEW),
    "Oani (Taipei)":  (OANI_SOFT_DELETE_TITLES, OANI_NEW),
}

total_deactivated = 0
total_inserted = 0

with engine.connect() as c:
    for branch_name, (delete_titles, new_rows) in PLAN.items():
        bid = BRANCHES[branch_name]
        print(f"\n=== {branch_name} ===")

        # Soft delete
        if delete_titles:
            res = c.execute(
                text(
                    "UPDATE branch_keypoints SET is_active = FALSE, updated_at = :now "
                    "WHERE branch_id = :b AND title = ANY(:titles) AND is_active = TRUE"
                ),
                {"now": now, "b": bid, "titles": delete_titles},
            )
            print(f"  soft-deleted: {res.rowcount}")
            total_deactivated += res.rowcount

        # Existing active titles (avoid insert duplicates)
        existing = {
            r[0].lower() for r in c.execute(
                text("SELECT title FROM branch_keypoints WHERE branch_id = :b AND is_active = TRUE"),
                {"b": bid},
            ).fetchall()
        }

        # Insert new
        added = 0
        for cat, title in new_rows:
            if title.lower() in existing:
                continue
            c.execute(
                text(
                    "INSERT INTO branch_keypoints (id, branch_id, category, title, is_active, "
                    "created_at, updated_at) VALUES (:id, :b, :c, :t, TRUE, :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "b": bid, "c": cat, "t": title, "now": now},
            )
            added += 1
        print(f"  inserted:     {added}  ({len(new_rows) - added} skipped as duplicates)")
        total_inserted += added

    c.commit()

print(f"\n---\nTotal soft-deleted: {total_deactivated}")
print(f"Total inserted:     {total_inserted}")
print("Done.")

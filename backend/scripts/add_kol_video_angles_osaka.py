"""Add 2 KOL video angles (Meander Osaka) + keypoints.

Source videos:
  - [Video] KOL_alyamiela    -> Solo-traveler launchpad in the heart of Namba
  - [Video] KOL_luisaoliver  -> Affordable, fully-equipped base near Namba + discount codes

Per memory: ad_angles.branch_id = NULL (angles are global).
Keypoints are branch-scoped (Meander Osaka).
"""
import sys, io, json, uuid, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.models.account import AdAccount


db = SessionLocal()
now = datetime.now(timezone.utc).isoformat()

# --- Find Meander Osaka branch_id (for keypoints only) ---
osaka = db.query(AdAccount).filter(AdAccount.account_name.ilike("%osaka%")).first()
if not osaka:
    raise SystemExit("Meander Osaka branch not found")
osaka_id = osaka.id
print(f"Meander Osaka branch_id = {osaka_id}")

# --- Next ANG-xxx id ---
with engine.connect() as c:
    rows = c.execute(text("SELECT angle_id FROM ad_angles WHERE angle_id LIKE 'ANG-%'")).fetchall()
nums = [int(re.sub(r"\D", "", r[0])) for r in rows if r[0] and re.sub(r"\D", "", r[0]).isdigit()]
next_n = (max(nums) + 1) if nums else 1

# --- Angles (global, branch_id = NULL) ---
angles = [
    {
        "angle_type": "Offer Information Directly in the claim",
        "target_audience": "Solo",
        "angle_explain": (
            "Speak directly to first-time solo travelers in Japan: position Meander Osaka as the launchpad "
            "that makes the trip feel safe, easy and effortless — clean modern rooms, welcoming staff, and a "
            "location minutes from Namba Station that opens up Umeda, Osaka Castle, Nara, Kobe and even Kyoto "
            "as day trips."
        ),
        "hook_examples": [
            "If you're planning your first solo trip to Japan, this is the perfect base in Osaka.",
            "I landed in Osaka alone — the moment I checked into Meander Osaka, everything just clicked.",
            "Safe, welcoming, minutes from Namba Station — the solo-traveler launchpad I wish I'd found sooner.",
        ],
        "notes": "Source: KOL video — alyamiela (Meander Osaka).",
    },
    {
        "angle_type": "Measure the size of the claim",
        "target_audience": "Couple",
        "angle_explain": (
            "Stack concrete proof points to make affordability undeniable: minutes from Nankai Namba Station "
            "and Midosuji Line, a short walk to Dotonbori, Shinsaibashi, Kuromon Market and Family Mart, a "
            "surprisingly spacious superior double with private bathtub, plus 24-hour front desk, luggage "
            "storage, free drinking water/coffee/tea, and up to 10% off with exclusive booking codes."
        ),
        "hook_examples": [
            "Affordable Osaka hotel — minutes from Nankai Namba Station and the Midosuji Line. Save this.",
            "Surprisingly spacious superior double, private bathtub, 24-hour front desk — and up to 10% off with code LUISA.",
            "Dotonbori, Shinsaibashi, Kuromon Market and Family Mart — all a short walk from Meander Osaka.",
        ],
        "notes": "Source: KOL video — luisaoliver (Meander Osaka).",
    },
]

with engine.connect() as c:
    for i, a in enumerate(angles):
        aid = f"ANG-{(next_n + i):03d}"
        c.execute(
            text(
                "INSERT INTO ad_angles (id, angle_id, branch_id, angle_type, angle_explain, "
                "hook_examples, target_audience, angle_text, hook, status, notes, created_by, "
                "created_at, updated_at) VALUES (:id, :aid, NULL, :at, :ae, :he, :ta, :atxt, :hk, "
                "'TEST', :notes, 'kol-video-seed', :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "aid": aid,
                "at": a["angle_type"],
                "ae": a["angle_explain"],
                "he": json.dumps(a["hook_examples"], ensure_ascii=False),
                "ta": a["target_audience"],
                "atxt": a["angle_explain"],
                "hk": a["angle_type"],
                "notes": a["notes"],
                "now": now,
            },
        )
        print(f"  + {aid}  {a['angle_type']}")
    c.commit()

# --- Keypoints (Meander Osaka) ---
# category in {location, amenity, experience, value}
keypoints = [
    # alyamiela
    ("location",   "A few minutes' walk from Namba Station — quick access to Umeda, Osaka Castle and Kyoto"),
    ("experience", "Safe and welcoming atmosphere — ideal for first-time solo travelers"),
    ("amenity",    "Cozy minimalist rooms with modern, clean design"),
    ("experience", "Friendly, helpful staff who make the stay feel effortless"),
    ("amenity",    "Shared lounge space to chill or get some work done"),
    ("location",   "Rental car service right next to the hotel — easy day trips to Nara, Kobe and the Kansai countryside"),
    ("location",   "Surrounded by street food, local izakayas and a 24/7 convenience store"),
    ("location",   "Steps from Dotonbori, Shinsaibashi-suji, Namba Parks and Takashimaya"),
    # luisaoliver
    ("location",   "Minutes from Nankai Namba Station and the Osaka Metro Midosuji Line"),
    ("amenity",    "Superior Double rooms — spacious for Japan, with private bathroom and bathtub"),
    ("amenity",    "Full in-room essentials — TV, kettle, hair dryer, toiletries, ample luggage space"),
    ("amenity",    "Free drinking water, coffee and tea available on-site"),
    ("experience", "24-hour front desk with luggage storage for early arrivals and late check-outs"),
    ("experience", "Stylish common area to chill, eat or meet other travelers — the Meander community vibe"),
    ("value",      "Exclusive KOL discount — code LUISA for up to 10% off on the direct website"),
    ("value",      "Exclusive KOL discount — code AGODALUISA for up to 10% off via the Agoda app"),
]

with engine.connect() as c:
    existing = {
        r[0].lower() for r in c.execute(
            text("SELECT title FROM branch_keypoints WHERE branch_id = :b"),
            {"b": osaka_id},
        ).fetchall()
    }
    added = 0
    for cat, title in keypoints:
        if title.lower() in existing:
            print(f"  = skip (exists): {title}")
            continue
        c.execute(
            text(
                "INSERT INTO branch_keypoints (id, branch_id, category, title, is_active, "
                "created_at, updated_at) VALUES (:id, :b, :c, :t, TRUE, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "b": osaka_id,
                "c": cat,
                "t": title,
                "now": now,
            },
        )
        print(f"  + [{cat}] {title}")
        added += 1
    c.commit()

print(f"\nDone. {len(angles)} angles + {added} keypoints added.")

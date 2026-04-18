"""Add 3 KOL video angles (Meander 1948 — Taipei) + keypoints.

Source videos:
  - _[Video] KOL_stephs_world_travels - talk  -> Gen-Z callout: best budget stay by Taipei Main Station
  - [Video] KOL__luisaoliver                  -> Heritage 70-yr building blending vintage charm + modern comfort
  - KOL_dnvrchoi_locationtips                 -> Taipei Main Station beats Ximending (location comparison)

Per memory: ad_angles.branch_id = NULL (angles are global).
Keypoints are branch-scoped (Meander 1948).
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

# --- Find Meander 1948 branch_id (for keypoints only) ---
m1948 = db.query(AdAccount).filter(AdAccount.account_name.ilike("%1948%")).first()
if not m1948:
    raise SystemExit("Meander 1948 branch not found")
branch_id = m1948.id
print(f"Meander 1948 branch_id = {branch_id}")

# --- Next ANG-xxx id ---
with engine.connect() as c:
    rows = c.execute(text("SELECT angle_id FROM ad_angles WHERE angle_id LIKE 'ANG-%'")).fetchall()
nums = [int(re.sub(r"\D", "", r[0])) for r in rows if r[0] and re.sub(r"\D", "", r[0]).isdigit()]
next_n = (max(nums) + 1) if nums else 1

# --- Angles (global, branch_id = NULL) ---
angles = [
    {
        "angle_type": "State the claim as a question",
        "target_audience": "Solo",
        "angle_explain": (
            "Open with a punchy, relatable question that surfaces the viewer's FOMO — most travelers to "
            "Taipei have never heard of Meander 1948. Frame it as the insider budget pick right next to "
            "Taipei Main Station: private rooms with balcony, dorms, a cafe-like co-working space, and "
            "free meal coupons. Tone is Gen-Z, confident, a little cheeky."
        ),
        "hook_examples": [
            "Why did no one tell me about this place sooner?",
            "You're going to Taipei and not booking Meander 1948? I'm judging.",
            "The best budget stay in Taipei is hiding right next to Taipei Main Station — here's why.",
        ],
        "notes": "Source: KOL video — stephs_world_travels (talk) — Meander 1948.",
    },
    {
        "angle_type": "Stress the exclusiveness of the claim",
        "target_audience": "Couple",
        "angle_explain": (
            "Lead with what nothing else in Taipei offers: a beautifully preserved 70-year-old building on "
            "Datong Street that blends vintage charm with modern comfort — minutes from Taipei Main Station, "
            "one train from Taoyuan International Airport, a 7-Eleven in the same building and Ningxia Night "
            "Market a short walk away. Reinforce exclusivity with three KOL-only booking codes."
        ),
        "hook_examples": [
            "A 70-year-old preserved building in the heart of Taipei — stylish, convenient, traveler-approved.",
            "Vintage charm meets modern comfort, minutes from Taipei Main Station — meet Meander 1948.",
            "Three exclusive codes: LUISA (site), LUISAKLOOK (Klook) and AGODALUISA (Agoda) — up to 10% off.",
        ],
        "notes": "Source: KOL video — luisaoliver — Meander 1948.",
    },
    {
        "angle_type": "Compare the claim to its rival",
        "target_audience": "Friend",
        "angle_explain": (
            "Reframe the default Taipei tourist choice: most people stay around Ximending, but Taipei Main "
            "Station is a better base — airport express and midnight bus stop here, group tours meet here, "
            "three MRT lines plus the HSR connect here. Position Meander 1948 as the stay that turns all of "
            "that into a five-minute walk."
        ),
        "hook_examples": [
            "Most tourists stay in Ximending — here's why you should book near Taipei Main Station instead.",
            "Airport express, midnight bus, three MRT lines, the HSR — all five minutes from Meander 1948.",
            "Skip Ximending. This is the smarter Taipei base for anyone planning group tours or day trips.",
        ],
        "notes": "Source: KOL video — dnvrchoi (location tips) — Meander 1948.",
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

# --- Keypoints (Meander 1948) ---
# category in {location, amenity, experience, value}
keypoints = [
    # stephs_world_travels
    ("location",   "Literally next to Taipei Main Station — get anywhere in the city fast"),
    ("amenity",    "Private rooms with balcony — clean, modern, full of character"),
    ("amenity",    "Hostel dorms available — budget option without sacrificing the vibe"),
    ("experience", "Co-working space that feels like a cute cafe"),
    ("value",      "Free meal coupons included with your stay"),
    # luisaoliver
    ("experience", "Beautifully preserved 70-year-old heritage building on Datong Street"),
    ("experience", "Vintage charm meets modern comfort — cozy, unique, very Taipei"),
    ("location",   "Restaurants, cafes, shopping streets and a 7-Eleven all in the same building"),
    ("location",   "Walking distance to Ningxia Night Market — one of Taipei's most famous food spots"),
    ("location",   "One train away from Taoyuan International Airport"),
    ("amenity",    "Balcony Double Ensuite — minimalist, clean, spacious for two"),
    ("amenity",    "In-room essentials: AC, TV, fridge, fast Wi-Fi, working table, hairdryer, balcony"),
    ("amenity",    "Private bathroom with fresh towels and full toiletries; Japanese washlets in the 4F common CR"),
    ("experience", "Spacious 4F common area with free drinking water — chill, work or meet other travelers"),
    ("value",      "Free breakfast vouchers at partner cafes nearby"),
    ("amenity",    "Clean, comfortable dorm-type rooms for solo travelers"),
    ("value",      "Exclusive KOL discount — code LUISA for up to 10% off on the direct website"),
    ("value",      "Exclusive KOL discount — code LUISAKLOOK for up to 5% off via the Klook app"),
    ("value",      "Exclusive KOL discount — code AGODALUISA for up to 10% off via the Agoda app"),
    # dnvrchoi
    ("location",   "Taipei Main Station is the city's central transport hub — airport express and midnight bus both stop here"),
    ("location",   "Most group tours meet at Taipei Main Station — no need to wake up extra early"),
    ("location",   "Connects to MRT Red, Blue and Green lines — fast travel across Taipei"),
    ("location",   "Right next to the HSR station — easy transfers to other provinces"),
    ("location",   "Just a five-minute walk from Taipei Main Station"),
    ("amenity",    "7-Eleven in the basement of the building for quick snacks and essentials"),
    ("value",      "Exclusive KOL discount — code DENVER for extra savings on the direct website"),
]

with engine.connect() as c:
    existing = {
        r[0].lower() for r in c.execute(
            text("SELECT title FROM branch_keypoints WHERE branch_id = :b"),
            {"b": branch_id},
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
                "b": branch_id,
                "c": cat,
                "t": title,
                "now": now,
            },
        )
        print(f"  + [{cat}] {title}")
        added += 1
    c.commit()

print(f"\nDone. {len(angles)} angles + {added} keypoints added.")

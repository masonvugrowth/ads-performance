"""Add 2 KOL video angles (Oani — Taipei / Ximending) + keypoints.

Source videos:
  - [Video] KOL_Denver Choi   -> 10/10 verdict, trendiest new hotel across Ximending Exit 4
  - KOL____eer___             -> Premium amenities stacked: custom fragrance, late-night beer, laundry+massage

Per memory: ad_angles.branch_id = NULL (angles are global).
Keypoints are branch-scoped (Oani).
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

# --- Find Oani branch_id (for keypoints only) ---
oani = db.query(AdAccount).filter(AdAccount.account_name.ilike("%oani%")).first()
if not oani:
    raise SystemExit("Oani branch not found")
branch_id = oani.id
print(f"Oani branch_id = {branch_id}")

# --- Next ANG-xxx id ---
with engine.connect() as c:
    rows = c.execute(text("SELECT angle_id FROM ad_angles WHERE angle_id LIKE 'ANG-%'")).fetchall()
nums = [int(re.sub(r"\D", "", r[0])) for r in rows if r[0] and re.sub(r"\D", "", r[0]).isdigit()]
next_n = (max(nums) + 1) if nums else 1

# --- Angles (global, branch_id = NULL) ---
angles = [
    {
        "angle_type": "Use an authority",
        "target_audience": "Couple",
        "angle_explain": (
            "Lean on the KOL's definitive verdict — a trusted traveler voice rating Oani 10/10 and promising "
            "to stay again. Position Oani as one of the trendiest new hotels in Ximending, right across Exit 4 "
            "of Ximending Station, with a superior double larger than expected, bidet toilet, a fragrance-tag "
            "oasis common area, free coffee, massage chairs and Bread Espresso's standout toast downstairs."
        ),
        "hook_examples": [
            "I found a perfect base in Taipei's Ximending — I'll definitely stay here again.",
            "The location is truly 10/10 — right across Exit 4 of Ximending Station.",
            "One of the trendiest new hotels in Ximending — use code DENVER on the official site.",
        ],
        "notes": "Source: KOL video — Denver Choi — Oani.",
    },
    {
        "angle_type": "Measure the size of the claim",
        "target_audience": "Solo",
        "angle_explain": (
            "Stack Oani's premium perks to make the stay feel unmissable: one-minute walk from Ximending MRT, "
            "customizable private fragrance from the B1 scent room, welcome snacks in the afternoon, late-night "
            "sweet soups and free-flow beer, wet-and-dry bathroom, in-room diffuser stones, laundry with "
            "massage while you wait, and a guest discount at the famous Japanese bakery downstairs."
        ),
        "hook_examples": [
            "Good morning, Ximending — you're one minute from Oani Oasis Hotel.",
            "Custom fragrance, late-night free-flow beer, laundry + massage while you wait — this is Oani.",
            "Diffuser stones in the room, wet-and-dry bathroom, bakery discount downstairs — save this stay.",
        ],
        "notes": "Source: KOL video — eer — Oani.",
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

# --- Keypoints (Oani) ---
# category in {location, amenity, experience, value}
keypoints = [
    # Denver Choi
    ("location",   "Right across from Exit 4 of Ximending MRT Station"),
    ("location",   "Steps from Ximending street food and shopping"),
    ("location",   "Convenience store right next door"),
    ("experience", "One of the trendiest new hotels in Ximending — cozy, comfortable vibe"),
    ("amenity",    "Superior Double rooms — larger than expected, city-view window"),
    ("amenity",    "Bidet toilet, slippers and a small desk in every room"),
    ("experience", "Stunning Ximending night view straight from the room"),
    ("experience", "Fragrance-tag oasis common area — pick up a scent as you pass through"),
    ("amenity",    "Free coffee available in the common area"),
    ("amenity",    "Massage chairs on site"),
    ("experience", "Bread Espresso downstairs — signature toast and a pumpkin latte with real pumpkin"),
    ("value",      "Exclusive KOL discount — code DENVER on the official website"),
    # eer
    ("location",   "Just a one-minute walk from Ximending MRT Station"),
    ("amenity",    "Full-length mirrors and makeup mirrors thoughtfully provided"),
    ("amenity",    "High-quality decor — extremely comfortable to stay in"),
    ("amenity",    "Wet-and-dry bathroom with excellent ventilation"),
    ("amenity",    "Amazing-smelling toiletries plus diffuser stones in the room"),
    ("experience", "B1 fragrance area — pick a scent to customize your private space"),
    ("experience", "Welcome snacks served in the afternoon on B1"),
    ("experience", "Late-night snack time with sweet soups and free-flow beer"),
    ("amenity",    "Luggage storage plus self-service washing machines, laundry pods and an ironing machine"),
    ("experience", "Enjoy a massage while waiting for your laundry"),
    ("value",      "Guest discount at the famous Japanese bakery downstairs"),
    ("location",   "Walking distance to Wannian Building toy shops, popular street food queues and affordable massage parlors"),
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

"""Add 2 KOL video angles (Meander Saigon) + keypoints.

Source videos:
  - [Video] KOL_frheajaimil  -> Stylish minimalist stay, social hotel vibe, exclusive discount
  - [Video] KOL_benjiminmaguire -> Luxury without the price tag, sustainable + calm in D1

Per memory: ad_angles.branch_id = NULL (angles are global).
Keypoints are branch-scoped (Meander Saigon).
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

# --- Find Meander Saigon branch_id (for keypoints only) ---
saigon = db.query(AdAccount).filter(AdAccount.account_name.ilike("%saigon%")).first()
if not saigon:
    raise SystemExit("Meander Saigon branch not found")
saigon_id = saigon.id
print(f"Meander Saigon branch_id = {saigon_id}")

# --- Next ANG-xxx id ---
with engine.connect() as c:
    rows = c.execute(text("SELECT angle_id FROM ad_angles WHERE angle_id LIKE 'ANG-%'")).fetchall()
nums = [int(re.sub(r"\D", "", r[0])) for r in rows if r[0] and re.sub(r"\D", "", r[0]).isdigit()]
next_n = (max(nums) + 1) if nums else 1

# --- Angles (global, branch_id = NULL) ---
angles = [
    {
        "angle_type": "Call out the person directly",
        "target_audience": "Solo",
        "angle_explain": (
            "Open with a direct address to the traveler heading to Ho Chi Minh so the ad feels like a "
            "personal tip from a friend, then deliver a stylish, clean, central stay they can book instantly "
            "with an exclusive KOL discount code."
        ),
        "hook_examples": [
            "If you're heading to Ho Chi Minh and want a clean, stylish place right in District 1 — keep watching.",
            "Going to Saigon? I found the perfect minimalist stay in the heart of District 1.",
            "Booking a trip to Ho Chi Minh? Use code FRHEAJAIMI for 10% off this stylish D1 stay.",
        ],
        "notes": "Source: KOL video — frheajaimil (Meander Saigon).",
    },
    {
        "angle_type": "Remove limitations from the claim",
        "target_audience": "Couple",
        "angle_explain": (
            "Break the assumption that luxury in District 1 has to be expensive. Frame Meander Saigon as "
            "intentional design, soft sheets, sustainable materials and a calm café downstairs — all without "
            "the five-star price tag — so couples, friend groups and solo travelers all see it as accessible."
        ),
        "hook_examples": [
            "Luxury without the price tag — that's Meander Saigon.",
            "A bed that welcomes you, cold brew downstairs, zero plastic — all in the heart of District 1.",
            "Thought luxury in Saigon was out of budget? Watch this before you book anything else.",
        ],
        "notes": "Source: KOL video — benjiminmaguire (Meander Saigon).",
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

# --- Keypoints (Meander Saigon) ---
# category in {location, amenity, experience, value}
keypoints = [
    # frheajaimil
    ("location", "Prime District 1 location — walking distance to Saigon's landmarks"),
    ("amenity",  "Bright, minimal Studio City View rooms"),
    ("amenity",  "High-tech Japanese-style toilets in every bathroom"),
    ("experience", "Daily housekeeping keeps every room spotless"),
    ("value",    "Exclusive KOL discount — 10% off on the direct website"),
    ("experience", "Social hotel vibe: indoor slide, shared kitchen and lounge to meet other travelers"),
    # benjiminmaguire
    ("amenity",  "Superior Double private rooms with soft sheets and clean lines"),
    ("experience", "Intentional, calm design — space to breathe in a fast-moving city"),
    ("value",    "Sustainable stay — no single-use plastic in the rooms"),
    ("experience", "Ground-floor café serving cold brew and a quiet break from the heat"),
    ("location", "Close to every major Saigon attraction — simple, quick transit"),
    ("value",    "Luxury feel without the five-star price tag"),
]

with engine.connect() as c:
    existing = {
        r[0].lower() for r in c.execute(
            text("SELECT title FROM branch_keypoints WHERE branch_id = :b"),
            {"b": saigon_id},
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
                "b": saigon_id,
                "c": cat,
                "t": title,
                "now": now,
            },
        )
        print(f"  + [{cat}] {title}")
        added += 1
    c.commit()

print(f"\nDone. {len(angles)} angles + {added} keypoints added.")

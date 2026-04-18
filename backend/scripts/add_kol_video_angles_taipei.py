"""Add 2 KOL video angles (Meander Taipei — Ximending) + keypoints.

Source videos:
  - [Video] KOL_ivyluvv.travel  -> "Under $20 a night in Ximending" — belief-challenge hook
  - [Video] KOL_makisantos_     -> Away from crowds but 8-min walk — reframe typical Ximending stay

Per memory: ad_angles.branch_id = NULL (angles are global).
Keypoints are branch-scoped (Meander Taipei).
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

# --- Find Meander Taipei branch_id (for keypoints only) ---
# Must be exactly "Meander Taipei" (Meta) — not "Oani (Taipei)", "1948", or google dupes
taipei = (
    db.query(AdAccount)
    .filter(AdAccount.account_name.ilike("meander taipei"))
    .filter(AdAccount.platform == "meta")
    .first()
)
if not taipei:
    raise SystemExit("Meander Taipei branch not found")
branch_id = taipei.id
print(f"Meander Taipei branch_id = {branch_id}  ({taipei.account_name})")

# --- Next ANG-xxx id ---
with engine.connect() as c:
    rows = c.execute(text("SELECT angle_id FROM ad_angles WHERE angle_id LIKE 'ANG-%'")).fetchall()
nums = [int(re.sub(r"\D", "", r[0])) for r in rows if r[0] and re.sub(r"\D", "", r[0]).isdigit()]
next_n = (max(nums) + 1) if nums else 1

# --- Angles (global, branch_id = NULL) ---
angles = [
    {
        "angle_type": "Challenge your prospect's beliefs",
        "target_audience": "Solo",
        "angle_explain": (
            "Break the assumption that staying in Ximending has to be expensive: open with the disarming "
            "fact that dorms start at $17 and private rooms run under $20, then back it up with a safe "
            "female-only dorm option, a pantry with free tea and coffee, free luggage storage, laundry, "
            "a rooftop night view and a meal voucher redeemable at local vendors."
        ),
        "hook_examples": [
            "Did you know you can stay in Ximending for under $20 a night?",
            "Ximending for $17 a night — safe, comfy and 8 minutes from the action. Yes, really.",
            "Everyone says Taipei is pricey — then they haven't heard of Meander Taipei.",
        ],
        "notes": "Source: KOL video — ivyluvv.travel — Meander Taipei.",
    },
    {
        "angle_type": "Call out a solution or product they're currently using",
        "target_audience": "Friend",
        "angle_explain": (
            "Call out the default Ximending stay travelers usually pick — loud, crowded, smack in the middle "
            "of the chaos — and reposition Meander Taipei as the smarter alternative: far enough from the "
            "noise for real rest, but still an 8-minute walk back when you want the night market and "
            "shopping. Comfy bed, clean bathroom with heated shower, big free common areas and free "
            "luggage storage included."
        ),
        "hook_examples": [
            "Stop booking hotels right in the middle of Ximending — here's the smarter move.",
            "Away from the crowds, 8 minutes from the action — this is how you do Ximending.",
            "Meander Taipei Hostel — dorms from 1,000 pesos, use code MAKI for 10% off.",
        ],
        "notes": "Source: KOL video — makisantos_ — Meander Taipei.",
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

# --- Keypoints (Meander Taipei) ---
# category in {location, amenity, experience, value}
keypoints = [
    # ivyluvv.travel
    ("value",      "Dorm beds from just $17 a night — one of the most affordable stays in Ximending"),
    ("value",      "Private double rooms from under $20 a night"),
    ("location",   "Just an 8-minute walk to the heart of Ximending — close, but away from the crowds"),
    ("amenity",    "Female-only dormitory rooms — safe and reassuring for solo female travelers"),
    ("amenity",    "Private double rooms — compact, with big windows, clean bathroom and under-bed luggage storage"),
    ("experience", "Spacious lobby for chilling or getting work done"),
    ("amenity",    "Pantry with free tea and coffee"),
    ("amenity",    "Free luggage storage for before check-in or after check-out"),
    ("amenity",    "On-site laundry room"),
    ("value",      "Complimentary meal voucher redeemable at selected local vendors"),
    ("experience", "Rooftop with a Taipei night view — perfect for unwinding"),
    ("value",      "Free Taipei travel guide available to guests"),
    # makisantos_
    ("value",      "Dorm beds from 1,000 pesos a night — budget-friendly for Filipino travelers"),
    ("amenity",    "Private rooms for 1 to 4 people — flexible for solo travelers, couples and small groups"),
    ("experience", "Away from the noise and crowds — restful even at peak Ximending hours"),
    ("amenity",    "Standard double room — window, comfy bed, TV, luggage storage, clean bathroom with heated shower"),
    ("experience", "Big free common areas in the lobby — hang out or meet other travelers"),
    ("value",      "Exclusive KOL discount — code MAKI for 10% off"),
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

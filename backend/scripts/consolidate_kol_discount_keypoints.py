"""Consolidate 'Exclusive KOL discount — code X ...' keypoints into one per branch.

User wanted a single 'Exclusive KOL discount' keypoint per branch instead of a
separate row for every KOL promo code (LUISA, LUISAKLOOK, AGODALUISA, DENVER, ...).

Behaviour:
  • Find all active branch_keypoints whose title starts with 'Exclusive KOL discount'.
  • Group by branch_id.
  • Pick a master per branch (exact-title match wins, else earliest created).
  • Rename master title to 'Exclusive KOL discount'.
  • Re-link every ad_combos.keypoint_ids entry that referenced any duplicate ID
    to the master ID (duplicates removed, order preserved).
  • Soft-delete duplicates (is_active = FALSE).

Run `python consolidate_kol_discount_keypoints.py` for a dry-run.
Add `--apply` to commit.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import defaultdict

from sqlalchemy.orm.attributes import flag_modified

from app.database import SessionLocal
from app.models.account import AdAccount
from app.models.ad_angle import AdAngle  # noqa: F401 — ensure FK target tables are registered
from app.models.ad_combo import AdCombo
from app.models.ad_copy import AdCopy  # noqa: F401
from app.models.ad_material import AdMaterial  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.keypoint import BranchKeypoint

APPLY = "--apply" in sys.argv
TARGET_PREFIX = "exclusive kol discount"
MASTER_TITLE = "Exclusive KOL discount"

db = SessionLocal()
try:
    matching = [
        k for k in db.query(BranchKeypoint).filter(BranchKeypoint.is_active.is_(True)).all()
        if k.title.lower().startswith(TARGET_PREFIX)
    ]
    if not matching:
        print("No 'Exclusive KOL discount' keypoints found.")
        raise SystemExit(0)

    by_branch: dict[str, list[BranchKeypoint]] = defaultdict(list)
    for k in matching:
        by_branch[k.branch_id].append(k)

    branch_names = {
        a.id: a.account_name
        for a in db.query(AdAccount).filter(AdAccount.id.in_(list(by_branch.keys()))).all()
    }

    all_combos = db.query(AdCombo).filter(AdCombo.keypoint_ids.isnot(None)).all()

    total_dupes = 0
    total_remaps = 0

    for bid, kps in by_branch.items():
        exact = next(
            (k for k in kps if k.title.strip().lower() == MASTER_TITLE.lower()), None
        )
        master = exact or sorted(kps, key=lambda k: (k.created_at, k.id))[0]
        dup_ids = {k.id for k in kps if k.id != master.id}

        print(f"\n=== {branch_names.get(bid, bid)} ===")
        print(f"  master : {master.id[:8]}  {master.title!r}")
        for k in kps:
            if k.id == master.id:
                continue
            print(f"  dup    : {k.id[:8]}  {k.title!r}")

        if master.title != MASTER_TITLE:
            print(f"  rename master title -> {MASTER_TITLE!r}")
            master.title = MASTER_TITLE

        remaps_here = 0
        for combo in all_combos:
            ids = combo.keypoint_ids if isinstance(combo.keypoint_ids, list) else []
            if not any(i in dup_ids for i in ids):
                continue
            seen: set[str] = set()
            new_ids: list[str] = []
            for i in ids:
                ni = master.id if i in dup_ids else i
                if ni in seen:
                    continue
                seen.add(ni)
                new_ids.append(ni)
            if new_ids != ids:
                combo.keypoint_ids = new_ids
                flag_modified(combo, "keypoint_ids")
                remaps_here += 1
        print(f"  combos re-linked: {remaps_here}")
        total_remaps += remaps_here

        for k in kps:
            if k.id in dup_ids:
                k.is_active = False
                total_dupes += 1

    print("\n---")
    print(f"Branches touched:   {len(by_branch)}")
    print(f"Duplicates removed: {total_dupes}")
    print(f"Combos re-linked:   {total_remaps}")

    if APPLY:
        db.commit()
        print("COMMITTED.")
    else:
        db.rollback()
        print("DRY-RUN (no changes committed). Re-run with --apply to commit.")
finally:
    db.close()

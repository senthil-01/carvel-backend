"""
Migration script for menu_item_rules collection.

Task 1 — Remove servesPerTray from all scenario objects
Task 2 — Rename scenarios keys with category-based labels
Task 3 — Rename countScenarios keys with category-based labels (bread exception)

Run once: python3 migrate_menu_items.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME   = "cravecall_engine"
COLLECTION = "menu_item_rules"

# ── Label maps ────────────────────────────────────────────────────────────────

SCENARIO_LABELS = {
    "Rice": {
        "one":   "1 rice",
        "two":   "2 rice",
        "three": "2 rice and 1 bread",
    },
    "Appetizer": {
        "one":   "1 appetizer",
        "two":   "2 appetizer",
        "three": "3 appetizer",
    },
    "Entree": {
        "one":   "1 entree",
        "two":   "2 entree",
        "three": "3 entree",
    },
    "Dessert": {
        "one":   "1 dessert",
        "two":   "2 dessert",
        "three": "3 dessert",
    },
}

COUNT_SCENARIO_LABELS = {
    "Bread": {
        "one":   "1 bread",
        "two":   "1 bread and 1 rice",
        "three": "1 bread and 2 rice",
    },
    "Appetizer": {
        "one":   "1 appetizer",
        "two":   "2 appetizer",
        "three": "3 appetizer",
    },
    "Dessert": {
        "one":   "1 dessert",
        "two":   "2 dessert",
        "three": "3 dessert",
    },
}


def rename_scenarios(scenarios: dict, category: str) -> dict:
    """
    Rename scenario keys using category label map.
    Also removes servesPerTray from each scenario.
    """
    label_map = SCENARIO_LABELS.get(category, {})
    new_scenarios = {}

    for old_key, scenario_data in scenarios.items():
        # Task 1 — remove servesPerTray
        cleaned = {k: v for k, v in scenario_data.items() if k != "servesPerTray"}

        # Task 2 — rename key
        new_key = label_map.get(old_key, old_key)
        new_scenarios[new_key] = cleaned

    return new_scenarios


def rename_count_scenarios(count_scenarios: dict, category: str) -> dict:
    """
    Rename countScenarios keys using category label map.
    """
    label_map = COUNT_SCENARIO_LABELS.get(category, {})
    new_count_scenarios = {}

    for old_key, scenario_data in count_scenarios.items():
        new_key = label_map.get(old_key, old_key)
        new_count_scenarios[new_key] = scenario_data

    return new_count_scenarios


async def run_migration():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    total     = 0
    updated   = 0
    skipped   = 0

    cursor = collection.find({})

    async for doc in cursor:
        total += 1
        category = doc.get("category", "")
        update_fields = {}

        # ── Task 1 + 2 — scenarios ────────────────────────────────────────────
        scenarios = doc.get("scenarios")
        if scenarios and isinstance(scenarios, dict):
            if category == "Bread":
                # Bread has no scenarios — skip
                pass
            else:
                new_scenarios = rename_scenarios(scenarios, category)
                update_fields["scenarios"] = new_scenarios

        # ── Task 1 only — remove servesPerTray if scenarios exists for Bread ──
        # (shouldn't exist but safety check)
        elif scenarios and category == "Bread":
            new_scenarios = {
                k: {ik: iv for ik, iv in v.items() if ik != "servesPerTray"}
                for k, v in scenarios.items()
            }
            update_fields["scenarios"] = new_scenarios

        # ── Task 3 — countScenarios ───────────────────────────────────────────
        count_scenarios = doc.get("countScenarios")
        if count_scenarios and isinstance(count_scenarios, dict):
            new_count_scenarios = rename_count_scenarios(count_scenarios, category)
            update_fields["countScenarios"] = new_count_scenarios

        # ── Apply update ──────────────────────────────────────────────────────
        if update_fields:
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": update_fields}
            )
            updated += 1
            print(f"✅ Updated: {doc.get('itemCode')} ({category})")
        else:
            skipped += 1
            print(f"⏭  Skipped: {doc.get('itemCode')} ({category}) — nothing to update")

    print(f"\n{'─' * 40}")
    print(f"Total docs : {total}")
    print(f"Updated    : {updated}")
    print(f"Skipped    : {skipped}")

    client.close()


if __name__ == "__main__":
    asyncio.run(run_migration())

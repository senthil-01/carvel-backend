from datetime import datetime, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.constants import RESTAURANT_ID
from app.schemas.learning_cycle_config import LearningCycleConfigUpdate

COLLECTION = "learning_cycle_config"


def _serialize(doc) -> dict:
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_cycle_dates(cycle_months: list, year: int) -> list:
    """Pre-compute trigger dates for given months."""
    dates = []
    for month in cycle_months:
        try:
            dates.append(datetime(year, month, 1, tzinfo=timezone.utc))
            dates.append(datetime(year + 1, month, 1, tzinfo=timezone.utc))
        except ValueError:
            pass
    return sorted(dates)


def _build_current_cycle(cycle_months: list) -> dict:
    """
    Build currentCycle from cycleMonths.
    cycleMonths defines both fire date and cycle boundary.
    e.g. [1, 7] → H1: Jan 1 to Jun 30, H2: Jul 1 to Dec 31
    """
    now   = datetime.now(timezone.utc)
    year  = now.year

    sorted_months = sorted(cycle_months)
    m1 = sorted_months[0]
    m2 = sorted_months[1] if len(sorted_months) > 1 else sorted_months[0]

    # determine which half we are currently in
    if now.month < m2:
        # in first half
        cycle_start = datetime(year, m1, 1, tzinfo=timezone.utc)
        cycle_end   = datetime(year, m2, 1, tzinfo=timezone.utc).replace(
            day=1, hour=23, minute=59, second=59
        )
        # end = day before m2 starts
        import calendar
        prev_month     = m2 - 1 if m2 > 1 else 12
        prev_year      = year if m2 > 1 else year - 1
        last_day       = calendar.monthrange(prev_year, prev_month)[1]
        cycle_end      = datetime(prev_year, prev_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        cycle_id       = f"cycle_{year}_H1"
    else:
        # in second half
        cycle_start = datetime(year, m2, 1, tzinfo=timezone.utc)
        cycle_end   = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        cycle_id    = f"cycle_{year}_H2"

    return {
        "cycleId":                  cycle_id,
        "cycleStartDate":           cycle_start,
        "cycleEndDate":             cycle_end,
        "status":                   "active",
        "ordersCollectedSoFar":     0,
        "minimumMet":               False,
        "dateMet":                  False,
        "bothConditionsMet":        False,
        "recommendationsGenerated": False,
    }


# ── Service functions ─────────────────────────────────────────────────────────

async def initialize_config(
    minimum_order_count: int = 30,
    cycle_months: list = None,
) -> dict:
    """
    Create initial learning_cycle_config during restaurant onboarding.
    One document per caterer — called once at setup.
    cycleMonths defines both fire date and cycle boundary.
    cycleStartDate/cycleEndDate auto-computed from cycleMonths.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    # check if already exists
    existing = await db[COLLECTION].find_one({"restaurantId": RESTAURANT_ID})
    if existing:
        return _serialize(existing)

    cycle_months  = cycle_months or [1, 7]
    config_id     = f"cyc_{RESTAURANT_ID}"
    current_cycle = _build_current_cycle(cycle_months)
    cycle_dates   = _compute_cycle_dates(cycle_months, now.year)

    doc = {
        "configId":     config_id,
        "restaurantId": RESTAURANT_ID,
        "cycleSchedule": {
            "cycleMonths": cycle_months,
            "cycleDates":  cycle_dates,
        },
        "minimumOrderCount": minimum_order_count,
        "currentCycle":      current_cycle,
        "cycleHistory":      [],
        "isActive":          True,
        "createdAt":         now,
        "updatedAt":         now,
    }

    await db[COLLECTION].insert_one(doc)
    doc["_id"] = str(doc.get("_id", ""))
    return _serialize(doc)


async def get_config() -> Optional[dict]:
    """Get current learning cycle config."""
    db  = get_db()
    doc = await db[COLLECTION].find_one({"restaurantId": RESTAURANT_ID})
    return _serialize(doc) if doc else None


async def update_config(data: LearningCycleConfigUpdate) -> Optional[dict]:
    """
    Owner updates minimumOrderCount or cycleMonths.
    cycleStartDate/cycleEndDate auto-recomputed from cycleMonths.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    update_fields: dict = {"updatedAt": now}

    if data.minimumOrderCount is not None:
        update_fields["minimumOrderCount"] = data.minimumOrderCount

    if data.cycleMonths is not None:
        cycle_dates   = _compute_cycle_dates(data.cycleMonths, now.year)
        new_cycle     = _build_current_cycle(data.cycleMonths)
        update_fields["cycleSchedule.cycleMonths"]    = data.cycleMonths
        update_fields["cycleSchedule.cycleDates"]     = cycle_dates
        update_fields["currentCycle.cycleStartDate"]  = new_cycle["cycleStartDate"]
        update_fields["currentCycle.cycleEndDate"]    = new_cycle["cycleEndDate"]
        update_fields["currentCycle.cycleId"]         = new_cycle["cycleId"]

    result = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID},
        {"$set": update_fields},
        return_document=True
    )
    return _serialize(result) if result else None


async def check_and_update_conditions() -> dict:
    """
    Background job — runs daily at 6am.
    Checks both trigger conditions and updates bothConditionsMet flag.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    config = await db[COLLECTION].find_one({"restaurantId": RESTAURANT_ID})
    if not config:
        return {}

    min_orders    = config.get("minimumOrderCount", 30)
    current_cycle = config.get("currentCycle", {})
    cycle_months  = config.get("cycleSchedule", {}).get("cycleMonths", [1, 7])

    orders_so_far = current_cycle.get("ordersCollectedSoFar", 0)

    # check date condition — today is 1st of a cycle month
    date_met    = now.month in cycle_months and now.day == 1
    minimum_met = orders_so_far >= min_orders
    both_met    = date_met and minimum_met

    update_fields = {
        "currentCycle.dateMet":           date_met,
        "currentCycle.minimumMet":        minimum_met,
        "currentCycle.bothConditionsMet": both_met,
        "updatedAt":                      now,
    }

    result = await db[COLLECTION].find_one_and_update(
        {"restaurantId": RESTAURANT_ID},
        {"$set": update_fields},
        return_document=True
    )
    return _serialize(result)


async def mark_recommendations_generated(
    cycle_id: str,
    recommendations_count: int,
) -> None:
    """
    Called after learning engine fires.
    Sets recommendationsGenerated: true.
    Moves currentCycle to cycleHistory.
    Creates new currentCycle for next period.
    """
    db  = get_db()
    now = datetime.now(timezone.utc)

    config = await db[COLLECTION].find_one({"restaurantId": RESTAURANT_ID})
    if not config:
        return

    current_cycle = config.get("currentCycle", {})
    cycle_history = config.get("cycleHistory", [])
    cycle_months  = config.get("cycleSchedule", {}).get("cycleMonths", [1, 7])

    # move current to history
    cycle_history.append({
        "cycleId":              cycle_id,
        "ordersAnalysed":       current_cycle.get("ordersCollectedSoFar", 0),
        "recommendationsCount": recommendations_count,
        "triggeredAt":          now,
    })

    # build new cycle for next period
    new_cycle = _build_current_cycle(cycle_months)

    await db[COLLECTION].update_one(
        {"restaurantId": RESTAURANT_ID},
        {"$set": {
            "currentCycle": new_cycle,
            "cycleHistory": cycle_history,
            "updatedAt":    now,
        }}
    )


async def create_indexes():
    db = get_db()

    await db[COLLECTION].create_index(
        [("restaurantId", 1)],
        unique=True,
        name="idx_restaurantId_unique"
    )
    await db[COLLECTION].create_index(
        [("currentCycle.bothConditionsMet", 1)],
        name="idx_bothConditionsMet"
    )
    print(f"Indexes created for {COLLECTION}")
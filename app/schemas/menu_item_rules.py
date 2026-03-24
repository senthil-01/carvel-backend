from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.constants import (
    Category, VegNonVeg, RoundingRule, BreadSize
)


class TraySpread(BaseModel):
    S: float
    M: float
    L: float


class Scenario(BaseModel):
    servesPerTray: float
    spread: TraySpread


class Scenarios(BaseModel):
    one: Optional[Scenario] = None
    two: Optional[Scenario] = None
    three: Optional[Scenario] = None
    four: Optional[Scenario] = None


class CountScenario(BaseModel):
    piecesPerPerson: float


class CountScenarios(BaseModel):
    one: Optional[CountScenario] = None
    two: Optional[CountScenario] = None
    three: Optional[CountScenario] = None


class ComboSpreadLevel(BaseModel):
    S: float
    M: float
    L: float


class ComboBase(BaseModel):
    level1: ComboSpreadLevel
    level2: ComboSpreadLevel
    level3: ComboSpreadLevel


class ComboMatrixEntry(BaseModel):
    vegCount: int
    nonVegCount: int
    vegQtyLevel: int
    nonVegQtyLevel: int
    specialRule: Optional[str] = None


class ComboSpreadRules(BaseModel):
    vegBase: ComboBase
    nonVegBase: ComboBase
    comboMatrix: list[ComboMatrixEntry]

class TrayPrice(BaseModel):
    S: Optional[float] = None
    M: Optional[float] = None
    L: Optional[float] = None




# ── CREATE schema (used when importing from Excel) ──
class MenuItemRuleCreate(BaseModel):
    ruleVersionId: str
    # itemCode → auto-generated from menuName
    # restaurantId → sourced from RESTAURANT_ID constant
    # importJobId → excel only
    menuName: str
    category: Category
    style: str
    group: Optional[str] = None
    vegNonVeg: VegNonVeg
    sellByCount: bool
    size: Optional[str] = None
    adjustmentPct: float = 0
    adjustmentMultiplier: float = 1.0      # auto-set
    roundingRule: RoundingRule = RoundingRule.FULL_TRAY
    scenarios: Optional[Scenarios] = None
    countScenarios: Optional[CountScenarios] = None
    comboSpreadRules: Optional[ComboSpreadRules] = None
    isActive: bool = True
    source: str = "entry"                  # default for manual


# ── RESPONSE schema ──
class MenuItemRuleResponse(MenuItemRuleCreate):
    id: Optional[str] = Field(None, alias="_id")
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


# ── UPDATE schema (only through override workflow) ──
class MenuItemRuleUpdate(BaseModel):
    servesPerTray: Optional[float] = None
    adjustmentPct: Optional[float] = None
    adjustmentMultiplier: Optional[float] = None
    roundingRule: Optional[RoundingRule] = None
    scenarios: Optional[Scenarios] = None
    countScenarios: Optional[CountScenarios] = None
    isActive: Optional[bool] = None
    ruleVersionId: Optional[str] = None

#update price foe menu items
class MenuItemPriceUpdate(BaseModel):
    price: Optional[float] = None
    trayPrice: Optional[TrayPrice] = None
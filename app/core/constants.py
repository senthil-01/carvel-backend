from enum import Enum

# app/core/constants.py  (already exists in your project)
RESTAURANT_ID = "rest_001"

class Category(str, Enum):
    APPETIZER = "Appetizer"
    ENTREE = "Entree"
    RICE = "Rice"
    BREAD = "Bread"
    DESSERT = "Dessert"


class VegNonVeg(str, Enum):
    VEG = "Veg"
    NON_VEG = "Non Veg"


class Property(str, Enum):
    DRY = "Dry"
    SEMI = "Semi"
    GRAVY = "Gravy"
    EXTRA = "Extra"


class RiceType(str, Enum):
    REGULAR = "Regular"
    SPECIAL = "Special"
    BRIYANI = "Briyani"
    COLOR = "Color"


class BreadSize(str, Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    REGULAR = "Regular"


class RoundingRule(str, Enum):
    FULL_TRAY = "full_tray"
    HALF_TRAY = "half_tray"
    NEXT_INTEGER = "next_integer"
    MIN_ONE = "min_one"


class MultiplierType(str, Enum):
    EVENT = "event"
    SERVICE = "service"
    AUDIENCE = "audience"
    BUFFER = "buffer"
    SEASONAL = "seasonal"


class VersionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionSource(str, Enum):
    EXCEL_IMPORT = "excel_import"
    OVERRIDE_APPROVAL = "override_approval"
    LEARNING_APPROVAL = "learning_approval"


class RequestChannel(str, Enum):
    WEB_APP = "web_app"
    ADMIN_CONSOLE = "admin_console"
    SALES_CONSOLE = "sales_console"
    VOICE_AGENT = "voice_agent"
    CHAT_FORM = "chat_form"


class RequestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OverrideType(str, Enum):
    CALCULATION = "calculation"
    RULE = "rule"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


class OverrideStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    EXPIRED = "expired"


class OverrideReason(str, Enum):
    CHEF_EXPERIENCE = "chef_experience"
    CUSTOMER_PATTERN = "customer_specific_pattern"
    SEASONAL_DEMAND = "seasonal_demand"
    VIP_EVENT_RISK = "vip_event_risk"
    NEW_ITEM_NO_HISTORY = "new_item_no_history"
    ONE_TIME_EXCEPTION = "one_time_exception"


class ApproverRole(str, Enum):
    RESTAURANT_ADMIN = "restaurant_admin"
    REGIONAL_MANAGER = "regional_manager"
    BUSINESS_OWNER = "business_owner"
    CENTRAL_OPERATIONS_LEAD = "central_operations_lead"


class RequestorRole(str, Enum):
    SALES_REP = "sales_rep"
    CATERING_MANAGER = "catering_manager"
    OPERATIONS_MANAGER = "operations_manager"


class Decision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ImportStatus(str, Enum):
    UPLOADING = "uploading"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# Tray capacities (useable)
TRAY_CAPACITY = {
    "Small": 100,
    "Medium": 200,
    "Large": 300
}

# Combo spread base table
COMBO_SPREAD_BASE = {
    "1": {"S": 15, "M": 25, "L": 40},
    "2": {"S": 20, "M": 35, "L": 55},
    "3": {"S": 25, "M": 45, "L": 65},
}

# Combo matrix
COMBO_MATRIX = [
    {"vegCount": 1, "nonVegCount": 1, "vegQtyLevel": 1, "nonVegQtyLevel": 1},
    {"vegCount": 2, "nonVegCount": 1, "vegQtyLevel": 2, "nonVegQtyLevel": 1},
    {"vegCount": 3, "nonVegCount": 1, "vegQtyLevel": 3, "nonVegQtyLevel": 1},
    {"vegCount": 2, "nonVegCount": 2, "vegQtyLevel": 2, "nonVegQtyLevel": 2},
    {"vegCount": 3, "nonVegCount": 2, "vegQtyLevel": 3, "nonVegQtyLevel": 3},
]

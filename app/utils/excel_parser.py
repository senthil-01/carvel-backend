import pandas as pd
import math
from typing import Optional


# ── Tray useable capacities per sheet ──────────────────────────────────────
TRAY_USEABLE = {
    "Sell by Tray Appetizers":  {"Small": 100, "Medium": 203, "Large": 316},
    "Sell by Tray Entree":      {"Small": 110, "Medium": 215, "Large": 320},
    "Sell by Tray Rice":        {"Small": 100, "Medium": 200, "Large": 300},
    "Sell by Count Appetizer":  {"Small": 100, "Medium": 200, "Large": 300},
    "Sell by Count Bread":      {"Small": 100, "Medium": 200, "Large": 300},
    "Misc":                     {"Small": 100, "Medium": 200, "Large": 300},
}

# ── Column positions per sheet ─────────────────────────────────────────────
# Row 5 = servesPerTray row (index 5)
# Row 6 = header row (index 6)
# Row 7+ = data rows

SHEET_CONFIG = {
    "Sell by Tray Appetizers": {
        "data_start_row": 7,
        "col_adj_pct": 0,
        "col_adj_mult": 1,
        "col_veg": 2,
        "col_category": 3,
        "col_style": 4,
        "col_property": 5,
        "col_sell_by_count": 6,
        "col_menu_name": 7,
        "scenarios": {
            "one":   {"gpu_col": 8,  "S": 8,  "M": 9,  "L": 10},
            "two":   {"gpu_col": 11, "S": 11, "M": 12, "L": 13},
            "three": {"gpu_col": 14, "S": 14, "M": 15, "L": 16},
            "four":  {"gpu_col": 17, "S": 17, "M": 18, "L": 19},
        },
        "sell_by_count": False,
        "category": "Appetizer",
    },
    "Sell by Count Appetizer": {
        "data_start_row": 7,
        "col_adj_pct": 0,
        "col_adj_mult": 1,
        "col_veg": 2,
        "col_category": 3,
        "col_style": 4,
        "col_size": 5,
        "col_sell_by_count": 6,
        "col_menu_name": 7,
        "count_scenarios": {
            "one":   {"gpu_col": 8,  "val_col": 8},
            "two":   {"gpu_col": 9,  "val_col": 9},
            "three": {"gpu_col": 10, "val_col": 10},
        },
        "sell_by_count": True,
        "category": "Appetizer",
    },
    "Sell by Tray Entree": {
        "data_start_row": 7,
        "col_adj_pct": 0,
        "col_adj_mult": 1,
        "col_veg": 2,
        "col_category": 3,
        "col_group": 4,
        "col_style": 5,
        "col_property": 6,
        "col_sell_by_count": 7,
        "col_menu_name": 8,
        "scenarios": {
            "one":   {"gpu_col": 9,  "S": 9,  "M": 10, "L": 11},
            "two":   {"gpu_col": 12, "S": 12, "M": 13, "L": 14},
            "three": {"gpu_col": 15, "S": 15, "M": 16, "L": 17},
        },
        "sell_by_count": False,
        "category": "Entree",
    },
    "Sell by Tray Rice": {
        "data_start_row": 7,
        "col_adj_pct": 0,
        "col_adj_mult": 1,
        "col_veg": 2,
        "col_category": 3,
        "col_style": 4,
        "col_rice_type": 5,
        "col_sell_by_count": 6,
        "col_menu_name": 7,
        "scenarios": {
            "one":   {"gpu_col": 8,  "S": 8,  "M": 9,  "L": 10},
            "two":   {"gpu_col": 11, "S": 11, "M": 12, "L": 13},
            "three": {"gpu_col": 14, "S": 14, "M": 15, "L": 16},
        },
        "sell_by_count": False,
        "category": "Rice",
    },
    "Sell by Count Bread": {
        "data_start_row": 7,
        "col_adj_pct": 0,
        "col_adj_mult": 1,
        "col_veg": 2,
        "col_category": 3,
        "col_style": 4,
        "col_size": 5,
        "col_sell_by_count": 6,
        "col_menu_name": 7,
        "count_scenarios": {
            "one":   {"val_col": 8},
            "two":   {"val_col": 9},
            "three": {"val_col": 10},
        },
        "sell_by_count": True,
        "category": "Bread",
    },
}

GPU_ROW = 5  # Row index for servesPerTray values


def _safe_float(val) -> Optional[float]:
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return str(val).strip()


def _is_valid_row(row, col_menu_name: int) -> bool:
    name = _safe_str(row.iloc[col_menu_name])
    return name is not None and name != "" and name != "0"


def parse_tray_sheet(df: pd.DataFrame, sheet_name: str, config: dict) -> list:
    """Parse a sell-by-tray sheet and return list of item dicts"""
    items = []
    errors = []

    # Read servesPerTray from row 5
    gpu_row = df.iloc[GPU_ROW]
    serves_per_tray_values = {}
    for scenario_name, cols in config["scenarios"].items():
        spt_val = _safe_float(gpu_row.iloc[cols["gpu_col"]])
        if spt_val:
            serves_per_tray_values[scenario_name] = spt_val

    for row_idx in range(config["data_start_row"], len(df)):
        row = df.iloc[row_idx]
        menu_name = _safe_str(row.iloc[config["col_menu_name"]])

        if not menu_name or menu_name in ["0", "nan", ""]:
            continue

        adj_pct = _safe_float(row.iloc[config["col_adj_pct"]]) or 0
        adj_mult = _safe_float(row.iloc[config["col_adj_mult"]]) or 1.0
        veg_non_veg_raw = _safe_str(row.iloc[config["col_veg"]])
        veg_non_veg = "Non Veg" if veg_non_veg_raw and "non" in veg_non_veg_raw.lower() else veg_non_veg_raw
        category_raw = _safe_str(row.iloc[config["col_category"]]) or config["category"]
        # Normalize Entrée → Entree
        category = category_raw.replace("É", "E").replace("é", "e").replace("Entrée", "Entree").replace("entrée", "entree")
        sell_by_count_val = _safe_str(row.iloc[config["col_sell_by_count"]])
        sell_by_count = sell_by_count_val.upper() == "YES" if sell_by_count_val else False
        style = _safe_str(row.iloc[config["col_style"]])
        group = _safe_str(row.iloc[config["col_group"]]) if config.get("col_group") is not None else None
        property_val = _safe_str(row.iloc[config["col_property"]]) if config.get("col_property") is not None else None
        rice_type = _safe_str(row.iloc[config["col_rice_type"]]) if config.get("col_rice_type") is not None else None

        # Build scenarios
        scenarios = {}
        for scenario_name, cols in config["scenarios"].items():
            s_val = _safe_float(row.iloc[cols["S"]])
            m_val = _safe_float(row.iloc[cols["M"]])
            l_val = _safe_float(row.iloc[cols["L"]])
            spt = serves_per_tray_values.get(scenario_name)

            if s_val is not None and m_val is not None and l_val is not None:
                scenarios[scenario_name] = {
                    "servesPerTray": spt,
                    "spread": {"S": s_val, "M": m_val, "L": l_val}
                }

        # Generate itemCode
        item_code = menu_name.upper().replace(" ", "_").replace("-", "_")

        item = {
            "itemCode": item_code,
            "menuName": menu_name,
            "category": category,
            "style": style,
            "group": group,
            "vegNonVeg": veg_non_veg,
            "property": property_val,
            "riceType": rice_type,
            "sellByCount": sell_by_count,
            "size": None,
            "adjustmentPct": adj_pct,
            "adjustmentMultiplier": adj_mult,
            "roundingRule": "full_tray",
            "scenarios": scenarios,
            "countScenarios": None,
        }
        items.append({"row": row_idx + 2, "data": item})

    return items, errors


def parse_count_sheet(df: pd.DataFrame, sheet_name: str, config: dict) -> list:
    """Parse a sell-by-count sheet and return list of item dicts"""
    items = []
    errors = []

    for row_idx in range(config["data_start_row"], len(df)):
        row = df.iloc[row_idx]
        menu_name = _safe_str(row.iloc[config["col_menu_name"]])

        if not menu_name or menu_name in ["0", "nan", ""]:
            continue

        adj_pct = _safe_float(row.iloc[config["col_adj_pct"]]) or 0
        adj_mult = _safe_float(row.iloc[config["col_adj_mult"]]) or 1.0
        veg_non_veg_raw = _safe_str(row.iloc[config["col_veg"]])
        veg_non_veg = "Non Veg" if veg_non_veg_raw and "non" in veg_non_veg_raw.lower() else veg_non_veg_raw
        category_raw = _safe_str(row.iloc[config["col_category"]]) or config["category"]
        category = category_raw.replace("É", "E").replace("é", "e").replace("Entrée", "Entree").replace("entrée", "entree")
        sell_by_count_val = _safe_str(row.iloc[config["col_sell_by_count"]])
        sell_by_count = sell_by_count_val.upper() == "YES" if sell_by_count_val else True
        style = _safe_str(row.iloc[config["col_style"]])
        size = _safe_str(row.iloc[config["col_size"]]) if config.get("col_size") is not None else None

        # Build count scenarios
        count_scenarios = {}
        for scenario_name, cols in config["count_scenarios"].items():
            val = _safe_float(row.iloc[cols["val_col"]])
            if val is not None:
                count_scenarios[scenario_name] = {"piecesPerPerson": val}

        item_code = menu_name.upper().replace(" ", "_").replace("-", "_")

        item = {
            "itemCode": item_code,
            "menuName": menu_name,
            "category": category,
            "style": style,
            "group": None,
            "vegNonVeg": veg_non_veg,
            "property": None,
            "riceType": None,
            "sellByCount": sell_by_count,
            "size": size,
            "adjustmentPct": adj_pct,
            "adjustmentMultiplier": adj_mult,
            "roundingRule": "full_tray",
            "scenarios": None,
            "countScenarios": count_scenarios,
        }
        items.append({"row": row_idx + 2, "data": item})

    return items, errors


def parse_misc_sheet(df: pd.DataFrame) -> list:
    """Parse Misc sheet for Dessert items"""
    items = []

    # Misc sheet structure:
    # Row 3: scenario labels
    # Row 4: headers
    # Row 5-6: Idly, Vada (Appetizers — already in Sell by Count Appetizer sheet, skip)
    # Row 16-17: Dessert items (Gulab, Rasamalai — only these get imported)

    for row_idx in range(3, len(df)):
        if row_idx >= len(df):
            continue
        row = df.iloc[row_idx]

        category = _safe_str(row.iloc[1]) if len(row) > 1 else None
        menu_name = _safe_str(row.iloc[2]) if len(row) > 2 else None

        # Only process Dessert category rows — skip Idly, Vada and header rows
        if category != "Dessert":
            continue

        if not menu_name or menu_name in ["0", "nan", ""]:
            continue

        val1 = _safe_float(row.iloc[3])
        val2 = _safe_float(row.iloc[6])
        val3 = _safe_float(row.iloc[9])

        count_scenarios = {}
        if val1:
            count_scenarios["one"] = {"piecesPerPerson": val1}
        if val2:
            count_scenarios["two"] = {"piecesPerPerson": val2}
        if val3:
            count_scenarios["three"] = {"piecesPerPerson": val3}

        item_code = menu_name.upper().replace(" ", "_")

        item = {
            "itemCode": item_code,
            "menuName": menu_name,
            "category": "Dessert",
            "style": "South Indian",
            "group": None,
            "vegNonVeg": "Veg",
            "property": None,
            "riceType": None,
            "sellByCount": True,
            "size": "Large",
            "adjustmentPct": 0,
            "adjustmentMultiplier": 1.0,
            "roundingRule": "full_tray",
            "scenarios": None,
            "countScenarios": count_scenarios,
        }
        items.append({"row": row_idx + 2, "data": item})

    return items, []


def parse_combo_spread(file_path: str) -> dict:
    """
    Parse the veg/non-veg combo spread Excel file.
    Reads per-item spread values for each combo combination.

    Sheet structure:
    Rows 4-6:   Veg base table (qty 1,2,3)
    Rows 8-10:  NonVeg base table (qty 1,2,3)
    Rows 13-15: 1V+1NV combo — per item spread
    Rows 17-20: 2V+1NV combo — per item spread
    Rows 22-26: 3V+1NV combo — per item spread
    Rows 29-35: 3V+2NV combo — special rule, NV escalates to level 3
    Rows 39-43: 2V+2NV combo — per item spread
    """
    df = pd.read_excel(file_path, sheet_name="Sheet1", header=None)

    def _read_spread(row_idx):
        row = df.iloc[row_idx]
        return {
            "S": float(row.iloc[3]),
            "M": float(row.iloc[4]),
            "L": float(row.iloc[5])
        }

    def _read_qty(row_idx):
        row = df.iloc[row_idx]
        return int(float(row.iloc[2]))

    # ── Base table ─────────────────────────────────────────────────────────
    veg_base = {
        "1": _read_spread(4),
        "2": _read_spread(5),
        "3": _read_spread(6),
    }
    non_veg_base = {
        "1": _read_spread(8),
        "2": _read_spread(9),
        "3": _read_spread(10),
    }

    # ── 1V + 1NV (rows 14-15) ─────────────────────────────────────────────
    combo_1v_1nv = {
        "comboKey": "1V_1NV",
        "vegCount": 1,
        "nonVegCount": 1,
        "specialRule": False,
        "items": [
            {"type": "Veg",    "qtyLevel": _read_qty(14), "spread": _read_spread(14)},
            {"type": "NonVeg", "qtyLevel": _read_qty(15), "spread": _read_spread(15)},
        ]
    }

    # ── 2V + 1NV (rows 18-20) ─────────────────────────────────────────────
    combo_2v_1nv = {
        "comboKey": "2V_1NV",
        "vegCount": 2,
        "nonVegCount": 1,
        "specialRule": False,
        "items": [
            {"type": "Veg",    "qtyLevel": _read_qty(18), "spread": _read_spread(18)},
            {"type": "Veg",    "qtyLevel": _read_qty(19), "spread": _read_spread(19)},
            {"type": "NonVeg", "qtyLevel": _read_qty(20), "spread": _read_spread(20)},
        ]
    }

    # ── 3V + 1NV (rows 23-26) ─────────────────────────────────────────────
    combo_3v_1nv = {
        "comboKey": "3V_1NV",
        "vegCount": 3,
        "nonVegCount": 1,
        "specialRule": False,
        "items": [
            {"type": "Veg",    "qtyLevel": _read_qty(23), "spread": _read_spread(23)},
            {"type": "Veg",    "qtyLevel": _read_qty(24), "spread": _read_spread(24)},
            {"type": "Veg",    "qtyLevel": _read_qty(25), "spread": _read_spread(25)},
            {"type": "NonVeg", "qtyLevel": _read_qty(26), "spread": _read_spread(26)},
        ]
    }

    # ── 3V + 2NV (rows 31-35) — special rule ──────────────────────────────
    combo_3v_2nv = {
        "comboKey": "3V_2NV",
        "vegCount": 3,
        "nonVegCount": 2,
        "specialRule": True,
        "note": "5 items total — NonVeg escalates to level 3 instead of 2",
        "items": [
            {"type": "Veg",    "qtyLevel": _read_qty(31), "spread": _read_spread(31)},
            {"type": "Veg",    "qtyLevel": _read_qty(32), "spread": _read_spread(32)},
            {"type": "Veg",    "qtyLevel": _read_qty(33), "spread": _read_spread(33)},
            {"type": "NonVeg", "qtyLevel": _read_qty(34), "spread": _read_spread(34)},
            {"type": "NonVeg", "qtyLevel": _read_qty(35), "spread": _read_spread(35)},
        ]
    }

    # ── 2V + 2NV (rows 40-43) ─────────────────────────────────────────────
    combo_2v_2nv = {
        "comboKey": "2V_2NV",
        "vegCount": 2,
        "nonVegCount": 2,
        "specialRule": False,
        "items": [
            {"type": "Veg",    "qtyLevel": _read_qty(40), "spread": _read_spread(40)},
            {"type": "Veg",    "qtyLevel": _read_qty(41), "spread": _read_spread(41)},
            {"type": "NonVeg", "qtyLevel": _read_qty(42), "spread": _read_spread(42)},
            {"type": "NonVeg", "qtyLevel": _read_qty(43), "spread": _read_spread(43)},
        ]
    }

    return {
        "base": {
            "veg":    veg_base,
            "nonVeg": non_veg_base,
        },
        "combos": [
            combo_1v_1nv,
            combo_2v_1nv,
            combo_3v_1nv,
            combo_2v_2nv,
            combo_3v_2nv,
        ]
    }


def parse_excel_file(file_path: str) -> dict:
    """
    Main entry point. Parse all sheets from Excel file.
    Returns: { sheets_found, all_items, errors }
    """
    xl = pd.ExcelFile(file_path)
    sheets_found = xl.sheet_names
    all_items = []
    all_errors = []

    for sheet_name, config in SHEET_CONFIG.items():
        # Handle sheet name with trailing space
        actual_name = sheet_name
        for s in sheets_found:
            if s.strip() == sheet_name.strip():
                actual_name = s
                break

        if actual_name not in sheets_found and sheet_name not in sheets_found:
            continue

        try:
            df = pd.read_excel(file_path, sheet_name=actual_name, header=None)
        except Exception:
            continue

        if config.get("sell_by_count"):
            items, errors = parse_count_sheet(df, actual_name, config)
        else:
            items, errors = parse_tray_sheet(df, actual_name, config)

        for item in items:
            item["data"]["sheet"] = actual_name
        all_items.extend(items)
        all_errors.extend(errors)

    # Parse Misc sheet
    if "Misc" in sheets_found:
        df_misc = pd.read_excel(file_path, sheet_name="Misc", header=None)
        misc_items, misc_errors = parse_misc_sheet(df_misc)
        for item in misc_items:
            item["data"]["sheet"] = "Misc"
        all_items.extend(misc_items)
        all_errors.extend(misc_errors)

    return {
        "sheetsFound": sheets_found,
        "items": all_items,
        "errors": all_errors,
        "totalFound": len(all_items),
    }

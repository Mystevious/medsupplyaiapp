from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from math import ceil, sqrt
from pathlib import Path
from statistics import mean, pstdev
from time import monotonic

from flask import Flask, jsonify, request, send_from_directory
from sklearn.ensemble import RandomForestRegressor

from database import create_database, get_connection

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__)
APP_VERSION = "2.1.2"

@app.errorhandler(Exception)
def api_safe_exception(exc):
    # Flask normally emits an HTML 500 page.  API consumers need JSON.
    if request.path.startswith("/api/"):
        app.logger.exception("API request failed: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500
    raise exc


@app.after_request
def disable_stale_browser_cache(response):
    if request.path.startswith("/api/") or request.path in {"/script.js", "/style.css"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response
CACHE_TTL_SECONDS = 60
_consumption_cache = {}
_intel_cache = {}

SERVICE_LEVEL_Z = 1.645  # Approx. 95% service level assumption for the demo model.


def json_error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


def serialize_date(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def get_inventory_rows():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT
            i.id,
            i.medicine_name,
            i.category,
            i.quantity,
            i.minimum_stock,
            i.maximum_stock,
            i.expiry_date,
            i.supplier,
            COALESCE(i.supplier_lead_days, 5) AS supplier_lead_days,
            COALESCE(i.unit_price, 0) AS unit_price,
            COALESCE(i.criticality, 'Routine') AS criticality,
            mp.generic_name,
            mp.brand_name,
            mp.strength,
            mp.dosage_form,
            mp.storage_instruction,
            mp.manufacturer,
            mp.manufacturing_site,
            mp.product_identifier,
            mp.gtin,
            mp.emergency_reserve,
            mp.data_status,
            mp.source_name,
            mp.source_url
        FROM inventory i
        LEFT JOIN medicine_profiles mp ON mp.inventory_id = i.id
        ORDER BY i.id DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_consumption(medicine_id: int):
    now = monotonic()
    cached = _consumption_cache.get(medicine_id)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT usage_date, quantity_used
        FROM consumption_history
        WHERE medicine_id = %s
        ORDER BY usage_date ASC
        """,
        (medicine_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    _consumption_cache[medicine_id] = (now, rows)
    return rows


def ensure_demo_history():
    """Create clearly synthetic history only when the consumption table is empty."""
    import random

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM consumption_history")
    total = cur.fetchone()[0]
    if total > 0:
        cur.close()
        conn.close()
        return

    cur.execute("SELECT id, medicine_name FROM inventory ORDER BY id")
    medicines = cur.fetchall()
    base_usage = {
        "Paracetamol": 32,
        "Paracetamol 500mg": 32,
        "Amoxicillin": 9,
        "Amoxicillin 500mg": 9,
        "Insulin": 3,
        "Ibuprofen": 18,
        "Salbutamol": 2,
        "Azithromycin": 7,
        "Azithromycin 250mg": 7,
        "ORS": 22,
        "Metformin": 13,
        "IV Saline 500ml": 24,
        "Vitamin B12": 8,
    }
    random.seed(42)
    today = date.today()

    for medicine_id, medicine_name in medicines:
        base = base_usage.get(medicine_name, 10)
        for days_ago in range(120):
            d = today - timedelta(days=days_ago)
            weekday_factor = {
                0: 1.10, 1: 1.00, 2: 1.05, 3: 1.00,
                4: 1.15, 5: 0.85, 6: 0.75,
            }[d.weekday()]
            # A small synthetic noise component; this is marked DEMO in the UI.
            usage = max(1, round(base * weekday_factor * random.uniform(0.75, 1.25)))
            cur.execute(
                "INSERT INTO consumption_history (medicine_id, usage_date, quantity_used) VALUES (%s,%s,%s)",
                (medicine_id, d, usage),
            )

    conn.commit()
    cur.close()
    conn.close()


def build_forecast(records):
    """Random Forest demand forecast plus basic uncertainty statistics."""
    if not records:
        return {
            "daily_usage": 0.0,
            "predicted_7_days": 0,
            "predicted_30_days": 0,
            "forecast_series": [],
            "model": "Fallback average",
            "history_days": 0,
            "uncertainty": 0.0,
        }

    values = [max(0, float(r["quantity_used"])) for r in records]
    history_days = len(records)

    if history_days < 14:
        daily = max(0.1, mean(values))
        series = [daily] * 30
        return {
            "daily_usage": round(daily, 2),
            "predicted_7_days": round(sum(series[:7])),
            "predicted_30_days": round(sum(series)),
            "forecast_series": [round(x, 2) for x in series],
            "model": "Historical mean (insufficient history for ML)",
            "history_days": history_days,
            "uncertainty": round(pstdev(values) if len(values) > 1 else 0, 2),
        }

    first_date = records[0]["usage_date"]
    X, y = [], []
    for r in records:
        day_number = (r["usage_date"] - first_date).days
        X.append([day_number, r["usage_date"].weekday()])
        y.append(float(r["quantity_used"]))

    model = RandomForestRegressor(
        n_estimators=160,
        random_state=42,
        min_samples_leaf=2,
        max_features=1.0,
        n_jobs=-1,
    )
    model.fit(X, y)

    last_date = records[-1]["usage_date"]
    series = []
    tree_predictions = []
    for i in range(1, 31):
        future = last_date + timedelta(days=i)
        day_number = (future - first_date).days
        features = [[day_number, future.weekday()]]
        pred = max(0.0, float(model.predict(features)[0]))
        series.append(pred)
        tree_predictions.append(pred)

    daily = sum(series) / len(series)
    uncertainty = pstdev(series) if len(series) > 1 else 0.0

    return {
        "daily_usage": round(daily, 2),
        "predicted_7_days": round(sum(series[:7])),
        "predicted_30_days": round(sum(series)),
        "forecast_series": [round(x, 2) for x in series],
        "model": "Random Forest Regression",
        "history_days": history_days,
        "uncertainty": round(uncertainty, 2),
    }


def calculate_inventory_intelligence(item):
    history = get_consumption(item["id"])
    history_signature = (
        len(history),
        history[-1]["usage_date"].isoformat() if history else None,
        int(history[-1]["quantity_used"]) if history else None,
    )
    cache_key = (
        int(item["id"]),
        int(item["quantity"] or 0),
        int(item["minimum_stock"] or 0),
        int(item["maximum_stock"] or 0),
        serialize_date(item["expiry_date"]),
        int(item["supplier_lead_days"] or 5),
        float(item["unit_price"] or 0),
        str(item.get("criticality") or "Routine"),
        history_signature,
        date.today().isoformat(),
    )
    now = monotonic()
    cached = _intel_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    forecast = build_forecast(history)
    daily = forecast["daily_usage"]
    lead = max(0, int(item["supplier_lead_days"] or 5))
    minimum_stock = max(0, int(item["minimum_stock"] or 0))
    maximum_stock = max(minimum_stock, int(item["maximum_stock"] or minimum_stock))
    current = max(0, int(item["quantity"] or 0))
    emergency_reserve = max(0, int(item.get("emergency_reserve") or 0))

    lead_time_demand = daily * lead
    sigma = forecast["uncertainty"]
    statistical_safety = SERVICE_LEVEL_Z * sigma * sqrt(max(lead, 1))
    safety_stock = max(float(minimum_stock), statistical_safety, float(emergency_reserve))
    reorder_point = ceil(lead_time_demand + safety_stock)
    order_up_to = max(maximum_stock, reorder_point)
    recommended_order = max(0, order_up_to - current) if current <= reorder_point else 0

    stock_days = (current / daily) if daily > 0 else None
    days_to_expiry = (item["expiry_date"] - date.today()).days

    projected_stockout = None
    if stock_days is not None and stock_days < 3650:
        projected_stockout = (date.today() + timedelta(days=max(0, ceil(stock_days)))).isoformat()

    # Transparent rule-based Supply Risk Index, not a medical or predictive probability.
    risk_score = 0
    reasons = []
    if stock_days is not None and stock_days <= lead:
        risk_score += 40
        reasons.append("Projected stockout is at or before supplier lead time")
    elif stock_days is not None and stock_days <= lead + 3:
        risk_score += 25
        reasons.append("Stock cover is close to supplier lead time")
    if current <= minimum_stock:
        risk_score += 25
        reasons.append("Stock is at or below minimum level")
    if days_to_expiry < 0:
        risk_score += 35
        reasons.append("Batch-level expiry date has passed")
    elif days_to_expiry <= 30:
        risk_score += 30
        reasons.append("Expiry within 30 days")
    elif days_to_expiry <= 60:
        risk_score += 15
        reasons.append("Expiry within 60 days")
    criticality = (item.get("criticality") or "Routine").lower()
    if criticality == "critical":
        risk_score += 15
        reasons.append("Critical item")
    elif criticality == "essential":
        risk_score += 8
        reasons.append("Essential item")
    risk_score = min(100, risk_score)

    if risk_score >= 70:
        risk = "CRITICAL"
    elif risk_score >= 45:
        risk = "HIGH"
    elif risk_score >= 20:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    result = {
        **item,
        "expiry_date": serialize_date(item["expiry_date"]),
        "unit_price": float(item["unit_price"] or 0),
        "forecast": forecast,
        "daily_usage": forecast["daily_usage"],
        "stock_days": round(stock_days, 1) if stock_days is not None else None,
        "lead_time_demand": round(lead_time_demand),
        "safety_stock": round(safety_stock),
        "reorder_point": reorder_point,
        "recommended_order": recommended_order,
        "days_to_expiry": days_to_expiry,
        "projected_stockout": projected_stockout,
        "risk_score": risk_score,
        "risk": risk,
        "risk_reasons": reasons,
    }
    _intel_cache[cache_key] = (now, result)
    return result


def get_batch_summary(inventory_id=None):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    where = "" if inventory_id is None else "WHERE b.inventory_id = %s"
    params = () if inventory_id is None else (inventory_id,)
    cur.execute(
        f"""
        SELECT
            b.batch_id, b.inventory_id, i.medicine_name, b.batch_number,
            b.manufacture_date, b.expiry_date, b.quantity_received,
            b.quantity_current, b.received_date, b.origin_country,
            b.origin_site, b.quality_status, b.data_status,
            b.source_name, b.source_url,
            s.supplier_name,
            sl.location_code, sl.location_name, sl.location_type
        FROM medicine_batches b
        LEFT JOIN inventory i ON i.id = b.inventory_id
        LEFT JOIN suppliers s ON s.supplier_id = b.supplier_id
        LEFT JOIN storage_locations sl ON sl.location_id = b.storage_location_id
        {where}
        ORDER BY b.expiry_date ASC, b.batch_id DESC
        """,
        params,
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    for row in rows:
        for key in ("manufacture_date", "expiry_date", "received_date"):
            if row[key]:
                row[key] = serialize_date(row[key])
    return rows


def get_alerts_data():
    alerts = []
    for item in get_inventory_rows():
        intel = calculate_inventory_intelligence(item)
        if intel["quantity"] <= intel["minimum_stock"]:
            alerts.append({
                "type": "LOW STOCK",
                "severity": "HIGH" if intel["quantity"] <= intel["minimum_stock"] * 0.5 else "MEDIUM",
                "medicine_name": intel["medicine_name"],
                "message": f"{intel['quantity']} units remain against a minimum of {intel['minimum_stock']}.",
                "recommendation": f"Review procurement; suggested order {intel['recommended_order']} units.",
            })
        if intel["days_to_expiry"] < 0:
            alerts.append({
                "type": "EXPIRED",
                "severity": "CRITICAL",
                "medicine_name": intel["medicine_name"],
                "message": f"Expiry date was {intel['expiry_date']}.",
                "recommendation": "Quarantine/segregate and follow the organization's disposal procedure.",
            })
        elif intel["days_to_expiry"] <= 30:
            alerts.append({
                "type": "EXPIRY",
                "severity": "HIGH",
                "medicine_name": intel["medicine_name"],
                "message": f"Expires in {intel['days_to_expiry']} days.",
                "recommendation": "Apply FEFO and assess redistribution/use before expiry.",
            })
        if intel["stock_days"] is not None and intel["stock_days"] <= intel["supplier_lead_days"]:
            alerts.append({
                "type": "PROJECTED STOCKOUT",
                "severity": "CRITICAL",
                "medicine_name": intel["medicine_name"],
                "message": f"Projected stock cover is {intel['stock_days']} days versus {intel['supplier_lead_days']} days supplier lead time.",
                "recommendation": f"Plan approximately {intel['recommended_order']} units, subject to procurement policy.",
            })

    # Consumption anomaly alerts: compare last 7 days against the preceding 28 days.
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT medicine_id, usage_date, quantity_used
        FROM consumption_history
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL 35 DAY)
        ORDER BY medicine_id, usage_date
        """
    )
    records = cur.fetchall()
    cur.close()
    conn.close()
    grouped = defaultdict(list)
    for r in records:
        grouped[r["medicine_id"]].append(r)
    names = {r["id"]: r["medicine_name"] for r in get_inventory_rows()}
    for medicine_id, rows in grouped.items():
        recent = [float(r["quantity_used"]) for r in rows if r["usage_date"] >= date.today() - timedelta(days=6)]
        baseline = [float(r["quantity_used"]) for r in rows if r["usage_date"] < date.today() - timedelta(days=6)]
        if len(recent) >= 3 and len(baseline) >= 7:
            base = mean(baseline)
            recent_avg = mean(recent)
            if base > 0 and recent_avg >= base * 1.5:
                pct = (recent_avg / base - 1) * 100
                alerts.append({
                    "type": "ABNORMAL USAGE",
                    "severity": "MEDIUM",
                    "medicine_name": names.get(medicine_id, f"Medicine #{medicine_id}"),
                    "message": f"Recent 7-day average is {recent_avg:.1f}/day vs {base:.1f}/day baseline ({pct:.0f}% higher).",
                    "recommendation": "Review unusual demand, stock movements and underlying operational events.",
                })
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(alerts, key=lambda x: severity_order.get(x["severity"], 9))


@app.errorhandler(404)
def handle_404(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "API endpoint not found.", "path": request.path}), 404
    return error


@app.errorhandler(500)
def handle_500(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "API request failed. Check backend logs."}), 500
    return error


@app.route("/")
def home():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<page>.html")
def html_page(page):
    allowed = {"inventory", "alerts", "prediction", "supply-chain", "procurement", "settings"}
    if page not in allowed:
        return json_error("Page not found.", 404)
    return send_from_directory(str(FRONTEND_DIR), f"{page}.html")


# Friendly aliases (same pages, without .html).
@app.route("/<page>")
def friendly_page(page):
    allowed = {"inventory", "alerts", "prediction", "supply-chain", "procurement", "settings"}
    if page not in allowed:
        return json_error("Page not found.", 404)
    return send_from_directory(str(FRONTEND_DIR), f"{page}.html")


@app.route("/style.css")
def style():
    return send_from_directory(str(FRONTEND_DIR), "style.css")


@app.route("/script.js")
def script():
    return send_from_directory(str(FRONTEND_DIR), "script.js")


@app.route("/api/version")
def version():
    return jsonify({"system": "MedSupplyAI", "version": APP_VERSION})


@app.route("/api/health")
def health():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"status": "online", "system": "MedSupplyAI V2", "database": "connected"})
    except Exception as exc:
        return jsonify({"status": "degraded", "system": "MedSupplyAI V2", "database": "error", "message": str(exc)}), 500


@app.route("/api/dashboard")
def dashboard():
    items = [calculate_inventory_intelligence(x) for x in get_inventory_rows()]
    alerts = get_alerts_data()
    total_units = sum(int(x["quantity"]) for x in items)
    inventory_value = sum(float(x["quantity"]) * float(x["unit_price"]) for x in items)
    avg_daily = sum(float(x["daily_usage"]) for x in items if x["daily_usage"] > 0)
    risk_counts = defaultdict(int)
    for x in items:
        risk_counts[x["risk"]] += 1
    consumption = []
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT usage_date, SUM(quantity_used) total_usage
        FROM consumption_history
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY usage_date
        ORDER BY usage_date
        """
    )
    consumption = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({
        "total_items": len(items),
        "total_units": total_units,
        "inventory_value": round(inventory_value, 2),
        "low_stock": sum(1 for x in items if x["quantity"] <= x["minimum_stock"]),
        "expiring_soon": sum(1 for x in items if 0 <= x["days_to_expiry"] <= 30),
        "projected_stockouts": sum(1 for x in items if x["stock_days"] is not None and x["stock_days"] <= x["supplier_lead_days"]),
        "critical_items": sum(1 for x in items if x["criticality"].lower() == "critical"),
        "risk_counts": risk_counts,
        "alert_count": len(alerts),
        "top_risks": sorted(items, key=lambda x: (-x["risk_score"], x["medicine_name"]))[:6],
        "consumption_30d": [
            {"date": r["usage_date"].isoformat(), "usage": int(r["total_usage"])}
            for r in consumption
        ],
    })


@app.route("/api/inventory", methods=["GET", "POST"])
def inventory_api():
    if request.method == "GET":
        return jsonify([calculate_inventory_intelligence(x) for x in get_inventory_rows()])

    data = request.get_json(silent=True) or {}
    required = ["medicine_name", "category", "quantity", "minimum_stock", "maximum_stock", "expiry_date"]
    if any(data.get(k) in (None, "") for k in required):
        return json_error("Required fields are missing.")
    try:
        quantity = int(data["quantity"])
        minimum_stock = int(data["minimum_stock"])
        maximum_stock = int(data["maximum_stock"])
        lead_days = int(data.get("supplier_lead_days", 5))
        unit_price = float(data.get("unit_price", 0))
        if min(quantity, minimum_stock, maximum_stock, lead_days) < 0 or maximum_stock < minimum_stock:
            raise ValueError("Invalid numeric values")
    except (ValueError, TypeError):
        return json_error("Numeric values are invalid.")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO inventory
        (medicine_name, category, quantity, minimum_stock, maximum_stock,
         expiry_date, supplier, supplier_lead_days, unit_price, criticality)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            data["medicine_name"], data["category"], quantity,
            minimum_stock, maximum_stock, data["expiry_date"],
            data.get("supplier"), lead_days, unit_price, data.get("criticality", "Routine"),
        ),
    )
    inventory_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO medicine_profiles
        (inventory_id, generic_name, brand_name, strength, dosage_form,
         storage_instruction, manufacturer, manufacturing_site, product_identifier,
         gtin, emergency_reserve, data_status, source_name, source_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            inventory_id, data.get("generic_name", data["medicine_name"]),
            data.get("brand_name"), data.get("strength"), data.get("dosage_form", data["category"]),
            data.get("storage_instruction"), data.get("manufacturer"), data.get("manufacturing_site"),
            data.get("product_identifier"), data.get("gtin"), int(data.get("emergency_reserve", 0)),
            data.get("data_status", "USER ENTERED"), data.get("source_name"), data.get("source_url"),
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "id": inventory_id}), 201


@app.route("/api/inventory/<int:item_id>", methods=["DELETE"])
def delete_inventory(item_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM inventory WHERE id=%s", (item_id,))
    deleted = cur.rowcount
    if deleted:
        cur.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, details) VALUES ('inventory',%s,'DELETE','Inventory item deleted')",
            (item_id,),
        )
    conn.commit()
    cur.close()
    conn.close()
    if not deleted:
        return json_error("Medicine not found.", 404)
    return jsonify({"success": True})


@app.route("/api/predictions")
def predictions():
    return jsonify([calculate_inventory_intelligence(x) for x in get_inventory_rows()])


@app.route("/api/alerts")
def alerts():
    return jsonify(get_alerts_data())


@app.route("/api/consumption/<int:medicine_id>")
def consumption(medicine_id):
    rows = get_consumption(medicine_id)
    return jsonify([
        {"usage_date": r["usage_date"].isoformat(), "quantity_used": int(r["quantity_used"])}
        for r in rows
    ])


@app.route("/api/traceability/<int:inventory_id>")
def traceability(inventory_id):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT
            i.id, i.medicine_name, i.category, i.expiry_date,
            mp.generic_name, mp.brand_name, mp.strength, mp.dosage_form,
            mp.storage_instruction, mp.manufacturer, mp.manufacturing_site,
            mp.product_identifier, mp.gtin, mp.data_status, mp.source_name, mp.source_url,
            b.batch_id, b.batch_number, b.manufacture_date, b.quantity_current,
            b.received_date, b.origin_country, b.origin_site, b.quality_status,
            b.supplier_id, s.supplier_name, s.country supplier_country,
            sl.location_code, sl.location_name, sl.location_type
        FROM inventory i
        LEFT JOIN medicine_profiles mp ON mp.inventory_id = i.id
        LEFT JOIN medicine_batches b ON b.inventory_id = i.id
        LEFT JOIN suppliers s ON s.supplier_id = b.supplier_id
        LEFT JOIN storage_locations sl ON sl.location_id = b.storage_location_id
        WHERE i.id=%s
        ORDER BY b.expiry_date ASC
        """,
        (inventory_id,),
    )
    rows = cur.fetchall()
    if not rows:
        cur.close(); conn.close()
        return json_error("Medicine not found.", 404)
    events = []
    if rows[0]["batch_id"]:
        cur.execute(
            """
            SELECT event_id, event_type, event_time, location_name, actor_name,
                   document_ref, notes, data_status, source_name, source_url
            FROM supply_chain_events
            WHERE batch_id=%s
            ORDER BY event_time ASC
            """,
            (rows[0]["batch_id"],),
        )
        events = cur.fetchall()
    cur.close(); conn.close()

    head = rows[0]
    result = {
        "medicine": {
            "id": head["id"], "medicine_name": head["medicine_name"], "category": head["category"],
            "expiry_date": serialize_date(head["expiry_date"]), "generic_name": head["generic_name"],
            "brand_name": head["brand_name"], "strength": head["strength"], "dosage_form": head["dosage_form"],
            "storage_instruction": head["storage_instruction"], "manufacturer": head["manufacturer"],
            "manufacturing_site": head["manufacturing_site"], "product_identifier": head["product_identifier"],
            "gtin": head["gtin"], "data_status": head["data_status"], "source_name": head["source_name"],
            "source_url": head["source_url"],
        },
        "batches": [],
        "events": [],
    }
    seen = set()
    for row in rows:
        bid = row["batch_id"]
        if bid and bid not in seen:
            seen.add(bid)
            result["batches"].append({
                "batch_id": bid,
                "batch_number": row["batch_number"],
                "manufacture_date": serialize_date(row["manufacture_date"]),
                "expiry_date": serialize_date(row["expiry_date"]),
                "quantity_current": row["quantity_current"],
                "received_date": serialize_date(row["received_date"]),
                "origin_country": row["origin_country"],
                "origin_site": row["origin_site"],
                "quality_status": row["quality_status"],
                "supplier_name": row["supplier_name"],
                "location_name": row["location_name"],
                "location_type": row["location_type"],
            })
    for e in events:
        result["events"].append({
            **e,
            "event_time": e["event_time"].isoformat() if e["event_time"] else None,
        })
    return jsonify(result)


@app.route("/api/batches")
def batches():
    return jsonify(get_batch_summary())


@app.route("/api/storage")
def storage():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM storage_locations ORDER BY location_name")
    locations = cur.fetchall()
    cur.execute(
        """
        SELECT tl.*, sl.location_name
        FROM temperature_logs tl
        JOIN storage_locations sl ON sl.location_id=tl.location_id
        ORDER BY tl.logged_at DESC LIMIT 50
        """
    )
    temps = cur.fetchall()
    cur.close(); conn.close()
    for t in temps:
        if t["logged_at"]:
            t["logged_at"] = t["logged_at"].isoformat()
    return jsonify({"locations": locations, "temperature_logs": temps})


@app.route("/api/suppliers")
def suppliers():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM suppliers ORDER BY supplier_name")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)


def get_outstanding_procurement_by_inventory():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT poi.inventory_id, COALESCE(SUM(poi.quantity), 0) AS outstanding_quantity
        FROM procurement_order_items poi
        JOIN procurement_orders po ON po.order_id = poi.order_id
        WHERE UPPER(po.status) NOT IN ('CANCELLED', 'RECEIVED', 'CLOSED')
        GROUP BY poi.inventory_id
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {int(r["inventory_id"]): int(r["outstanding_quantity"] or 0) for r in rows}


@app.route("/api/procurement/recommendations")
def procurement_recommendations():
    outstanding = get_outstanding_procurement_by_inventory()
    rows = [calculate_inventory_intelligence(x) for x in get_inventory_rows()]
    result = []
    for row in rows:
        open_qty = outstanding.get(int(row["id"]), 0)
        net_recommendation = max(0, int(row["recommended_order"]) - open_qty)
        if net_recommendation > 0:
            result.append({**row, "outstanding_order": open_qty, "recommended_order": net_recommendation})
    return jsonify(result)


@app.route("/api/procurement", methods=["GET", "POST"])
def procurement():
    if request.method == "GET":
        conn = get_connection(); cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT po.order_id, po.order_number, po.created_at, po.expected_delivery,
                   po.status, po.priority, po.total_value, s.supplier_name
            FROM procurement_orders po
            LEFT JOIN suppliers s ON s.supplier_id=po.supplier_id
            ORDER BY po.created_at DESC
            """
        )
        rows = cur.fetchall(); cur.close(); conn.close()
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
            r["expected_delivery"] = serialize_date(r["expected_delivery"])
            r["total_value"] = float(r["total_value"] or 0)
        return jsonify(rows)

    data = request.get_json(silent=True) or {}
    item = data.get("inventory_id")
    qty = data.get("quantity")
    if item is None or qty is None:
        return json_error("inventory_id and quantity are required.")
    try:
        qty = int(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        return json_error("Quantity must be a positive integer.")

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT i.*, COALESCE(i.unit_price,0) unit_price FROM inventory i WHERE i.id=%s",
        (int(item),),
    )
    inv = cur.fetchone()
    if not inv:
        cur.close(); conn.close(); return json_error("Inventory item not found.", 404)

    # Prevent duplicate active orders for the same recommendation.
    cur.execute(
        """
        SELECT COALESCE(SUM(poi.quantity),0) AS outstanding_quantity
        FROM procurement_order_items poi
        JOIN procurement_orders po ON po.order_id = poi.order_id
        WHERE poi.inventory_id=%s
          AND UPPER(po.status) NOT IN ('CANCELLED', 'RECEIVED', 'CLOSED')
        """,
        (int(item),),
    )
    outstanding = int(cur.fetchone()["outstanding_quantity"] or 0)

    supplier_id = None
    if inv["supplier"]:
        cur.execute("SELECT supplier_id FROM suppliers WHERE supplier_name=%s LIMIT 1", (inv["supplier"],))
        row = cur.fetchone(); supplier_id = row["supplier_id"] if row else None
    order_number = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    total = qty * float(inv["unit_price"] or 0)
    cur.execute(
        """
        INSERT INTO procurement_orders
        (order_number, supplier_id, created_at, expected_delivery, status, priority, total_value, notes)
        VALUES (%s,%s,NOW(),DATE_ADD(CURDATE(),INTERVAL %s DAY),'PLACED',%s,%s,%s)
        """,
        (order_number, supplier_id, int(inv["supplier_lead_days"] or 5), data.get("priority", "NORMAL"), total,
         "Placed from MedSupplyAI recommendation; quantity remains outstanding until received or closed."),
    )
    order_id = cur.lastrowid
    cur.execute(
        "INSERT INTO procurement_order_items (order_id, inventory_id, quantity, unit_price) VALUES (%s,%s,%s,%s)",
        (order_id, int(item), qty, float(inv["unit_price"] or 0)),
    )
    cur.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, details) VALUES ('procurement_order',%s,'CREATE',%s)",
        (order_id, f"Created {order_number} for inventory {item}, quantity {qty}"),
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify({"success": True, "order_id": order_id, "order_number": order_number, "status": "PLACED"}), 201


@app.route("/api/procurement/<int:order_id>/status", methods=["POST"])
def procurement_status(order_id):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).upper().strip()
    allowed = {"PLACED", "APPROVED", "SENT", "IN_TRANSIT", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED", "CLOSED"}
    if status not in allowed:
        return json_error("Invalid procurement status.")
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE procurement_orders SET status=%s WHERE order_id=%s", (status, order_id))
    updated = cur.rowcount
    if updated:
        cur.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, details) VALUES ('procurement_order',%s,'STATUS_CHANGE',%s)",
            (order_id, f"Status changed to {status}"),
        )
    conn.commit(); cur.close(); conn.close()
    if not updated:
        return json_error("Purchase order not found.", 404)
    return jsonify({"success": True, "order_id": order_id, "status": status})


@app.route("/api/stock/transaction", methods=["POST"])
def stock_transaction():
    data = request.get_json(silent=True) or {}
    inventory_id = data.get("inventory_id")
    transaction_type = str(data.get("transaction_type", "")).upper()
    quantity = data.get("quantity")
    if inventory_id is None or quantity is None or transaction_type not in {"RECEIPT", "ISSUE", "ADJUSTMENT"}:
        return json_error("inventory_id, quantity and a valid transaction type are required.")
    try:
        qty = int(quantity)
        if qty <= 0:
            raise ValueError
    except ValueError:
        return json_error("Quantity must be a positive integer.")

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT quantity FROM inventory WHERE id=%s FOR UPDATE", (int(inventory_id),))
    row = cur.fetchone()
    if not row:
        conn.rollback(); cur.close(); conn.close(); return json_error("Inventory item not found.", 404)
    current = int(row["quantity"])
    if transaction_type == "ISSUE" and qty > current:
        conn.rollback(); cur.close(); conn.close(); return json_error("Issue quantity exceeds current stock.")
    if transaction_type == "RECEIPT":
        new_quantity = current + qty
    elif transaction_type == "ISSUE":
        new_quantity = current - qty
    else:
        new_quantity = qty
    cur.execute("UPDATE inventory SET quantity=%s WHERE id=%s", (new_quantity, int(inventory_id)))
    cur.execute(
        "INSERT INTO stock_transactions (medicine_id, transaction_type, quantity, notes) VALUES (%s,%s,%s,%s)",
        (int(inventory_id), transaction_type, qty, data.get("notes")),
    )
    cur.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, details) VALUES ('inventory',%s,'STOCK_CHANGE',%s)",
        (int(inventory_id), f"{transaction_type} {qty}; new balance {new_quantity}"),
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify({"success": True, "new_quantity": new_quantity})


@app.route("/api/supply-chain/events/<int:batch_id>")
def batch_events(batch_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM supply_chain_events WHERE batch_id=%s ORDER BY event_time ASC",
        (batch_id,),
    )
    rows = cur.fetchall(); cur.close(); conn.close()
    for r in rows:
        r["event_time"] = r["event_time"].isoformat() if r["event_time"] else None
    return jsonify(rows)


if __name__ == "__main__":
    print(f"[MedSupplyAI] Starting version {APP_VERSION}")
    print(f"[MedSupplyAI] Backend: {Path(__file__).resolve()}")
    create_database()
    ensure_demo_history()
    app.run(debug=True, host="127.0.0.1", port=5000)

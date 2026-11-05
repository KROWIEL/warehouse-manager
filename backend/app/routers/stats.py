from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..config import settings
from ..constants import CURRENCY, PAYMENT_METHODS
from ..db import get_conn
from ..export_xlsx import build_workbook
from ..periods import (
    MIN_DATE,
    PERIOD_IDS,
    bucket_key,
    bucket_label,
    choose_granularity,
    next_bucket,
    resolve_period,
)
from ..security import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])

TOP_LIMIT = 20

# Доля скидки на позицию: скидка задаётся на весь чек, поэтому для разрезов
# по категориям и поставщикам её разносим пропорционально суммам позиций.
# sale_gross считается коррелированным подзапросом — по idx_items_sale это дёшево
# и не требует держать все чеки в памяти.
_SALE_LINES = """
SELECT i.id AS item_id, i.sale_id, i.product_id, i.qty, i.unit_price, i.subtotal,
       s.occurred_at, s.discount, s.payment_method, s.created_by,
       (SELECT SUM(subtotal) FROM sale_items WHERE sale_id = i.sale_id) AS sale_gross,
       p.name AS product_name, p.category_id, p.subcategory_id, p.supplier_id
FROM sale_items i
JOIN sales s ON s.id = i.sale_id
JOIN products p ON p.id = i.product_id
WHERE s.occurred_at BETWEEN ? AND ?
"""

# Возврат относим к дате самого возврата, а не продажи: деньги ушли из кассы
# в этом периоде. Цена берётся из позиции чека, а скидка — из того же чека.
_RETURN_LINES = """
SELECT m.qty, m.occurred_at, i.id AS item_id, i.sale_id, i.unit_price,
       s.discount, s.payment_method, s.created_by,
       (SELECT SUM(subtotal) FROM sale_items WHERE sale_id = i.sale_id) AS sale_gross,
       p.name AS product_name, p.id AS product_id,
       p.category_id, p.subcategory_id, p.supplier_id
FROM stock_movements m
JOIN sale_items i ON i.id = m.sale_item_id
JOIN sales s ON s.id = i.sale_id
JOIN products p ON p.id = i.product_id
WHERE m.kind = 'return' AND m.occurred_at BETWEEN ? AND ?
"""


def _factor(sale_gross: float | None, discount: float | None) -> float:
    gross = float(sale_gross or 0)
    if gross <= 0:
        return 1.0
    return (gross - float(discount or 0)) / gross


class Bucket:
    """Копилка «выручка + количество» с произвольным набором полей-описателей."""

    __slots__ = ("meta", "revenue", "units")

    def __init__(self, meta: dict):
        self.meta = meta
        self.revenue = 0.0
        self.units = 0.0

    def add(self, revenue: float, units: float) -> None:
        self.revenue += revenue
        self.units += units


def _group(store: dict, key, meta: dict) -> Bucket:
    if key not in store:
        store[key] = Bucket(meta)
    return store[key]


def _finish(store: dict, total: float, limit: int | None = None) -> list[dict]:
    items = [
        {
            **b.meta,
            "revenue": round(b.revenue, 2),
            "units": round(b.units, 3),
            "percent": round(b.revenue / total * 100, 1) if total else 0.0,
        }
        for b in store.values()
    ]
    items.sort(key=lambda x: x["revenue"], reverse=True)
    return items[:limit] if limit else items


def build_stats(
    start: str, end: str, label: str, period: str, attribute_id: int | None = None
) -> dict:
    today = date.today()
    dead_cutoff = (today - timedelta(days=settings.dead_stock_days)).isoformat()

    with get_conn() as conn:
        sales = conn.execute(
            """
            SELECT s.id, s.occurred_at, s.total, s.discount, s.payment_method, s.created_by,
                   u.display_name AS author
            FROM sales s LEFT JOIN users u ON u.id = s.created_by
            WHERE s.occurred_at BETWEEN ? AND ?
            """,
            (start, end),
        ).fetchall()
        lines = conn.execute(_SALE_LINES, (start, end)).fetchall()
        returns = conn.execute(_RETURN_LINES, (start, end)).fetchall()

        movements = conn.execute(
            """
            SELECT m.kind, m.qty, p.price
            FROM stock_movements m JOIN products p ON p.id = m.product_id
            WHERE m.kind IN ('writeoff', 'receipt', 'adjust')
              AND m.occurred_at BETWEEN ? AND ?
            """,
            (start, end),
        ).fetchall()

        user_names = {
            r["id"]: r["display_name"]
            for r in conn.execute("SELECT id, display_name FROM users")
        }
        categories = {
            r["id"]: dict(r)
            for r in conn.execute("SELECT id, name, color, icon FROM categories")
        }
        subcategories = {
            r["id"]: dict(r) for r in conn.execute("SELECT id, name, category_id FROM subcategories")
        }
        suppliers = {r["id"]: dict(r) for r in conn.execute("SELECT id, name FROM suppliers")}

        attributes_available = [
            dict(r)
            for r in conn.execute(
                """
                SELECT a.id, a.name, a.kind, c.name AS category_name
                FROM attributes a JOIN categories c ON c.id = a.category_id
                WHERE a.archived = 0
                ORDER BY c.sort_order, a.sort_order
                """
            )
        ]

        attr_values: dict[int, str] = {}
        attribute_meta = None
        if attribute_id:
            attribute_meta = next(
                (a for a in attributes_available if a["id"] == attribute_id), None
            )
            if attribute_meta is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Поле не найдено")
            attr_values = {
                r["product_id"]: r["value"]
                for r in conn.execute(
                    "SELECT product_id, value FROM product_attributes WHERE attribute_id = ?",
                    (attribute_id,),
                )
            }

        stock_rows = conn.execute(
            """
            SELECT p.id, p.name, p.price, p.min_stock, p.archived,
                   c.name AS category_name, c.color AS category_color,
                   s.name AS supplier_name,
                   COALESCE(agg.stock, 0) AS stock, agg.last_sale
            FROM products p
            JOIN categories c ON c.id = p.category_id
            JOIN suppliers s ON s.id = p.supplier_id
            LEFT JOIN (
                SELECT product_id, SUM(qty) AS stock,
                       MAX(CASE WHEN kind = 'sale' THEN occurred_at END) AS last_sale
                FROM stock_movements GROUP BY product_id
            ) agg ON agg.product_id = p.id
            WHERE p.archived = 0
            """
        ).fetchall()

    # ==== Итоги ====
    receipts = len(sales)
    after_discount = sum(float(s["total"]) for s in sales)
    discount_total = sum(float(s["discount"]) for s in sales)

    by_category: dict = {}
    by_subcategory: dict = {}
    by_supplier: dict = {}
    by_product: dict = {}
    by_user: dict = {}
    by_payment: dict = {}
    by_attribute: dict = {}
    per_bucket: dict = {}

    granularity = "day"
    dates = [r["occurred_at"] for r in sales] + [r["occurred_at"] for r in returns]
    if dates:
        granularity = choose_granularity(min(dates), max(dates))

    def touch_bucket(iso: str) -> dict:
        key = bucket_key(iso, granularity)
        if key not in per_bucket:
            per_bucket[key] = {"revenue": 0.0, "units": 0.0, "receipts": 0}
        return per_bucket[key]

    def spread(row, revenue: float, units: float) -> None:
        """Одна и та же сумма разносится по всем разрезам сразу."""
        cat = categories.get(row["category_id"], {"name": "—", "color": "#94a3b8", "icon": "package"})
        _group(
            by_category,
            row["category_id"],
            {
                "id": row["category_id"],
                "name": cat["name"],
                "color": cat.get("color", "#94a3b8"),
                "icon": cat.get("icon", "package"),
            },
        ).add(revenue, units)

        sub_id = row["subcategory_id"]
        sub = subcategories.get(sub_id)
        _group(
            by_subcategory,
            sub_id or 0,
            {
                "id": sub_id,
                "name": sub["name"] if sub else "Без подкатегории",
                "category_name": cat["name"],
                "color": cat.get("color", "#94a3b8"),
            },
        ).add(revenue, units)

        sup = suppliers.get(row["supplier_id"], {"name": "—"})
        _group(
            by_supplier,
            row["supplier_id"],
            {"id": row["supplier_id"], "name": sup["name"]},
        ).add(revenue, units)

        _group(
            by_product,
            row["product_id"],
            {
                "id": row["product_id"],
                "name": row["product_name"],
                "category_name": cat["name"],
                "color": cat.get("color", "#94a3b8"),
            },
        ).add(revenue, units)

        method = row["payment_method"]
        _group(
            by_payment,
            method,
            {"id": method, "name": PAYMENT_METHODS.get(method, method)},
        ).add(revenue, units)

        if attribute_id:
            value = attr_values.get(row["product_id"], "Не указано")
            _group(by_attribute, value, {"id": value, "name": value}).add(revenue, units)

    def seller(user_id) -> dict:
        return {"id": user_id, "name": user_names.get(user_id, "—")}

    for row in lines:
        factor = _factor(row["sale_gross"], row["discount"])
        revenue = float(row["subtotal"]) * factor
        units = float(row["qty"])
        spread(row, revenue, units)
        bucket = touch_bucket(row["occurred_at"])
        bucket["revenue"] += revenue
        bucket["units"] += units

    returns_units = 0.0
    returns_amount = 0.0
    for row in returns:
        factor = _factor(row["sale_gross"], row["discount"])
        units = float(row["qty"])  # у возврата qty положительный
        revenue = units * float(row["unit_price"]) * factor
        returns_units += units
        returns_amount += revenue
        spread(row, -revenue, -units)
        bucket = touch_bucket(row["occurred_at"])
        bucket["revenue"] -= revenue
        bucket["units"] -= units

    # Продавцы: сумма чека идёт тому, кто его провёл, а возврат уменьшает выручку
    # того, кто оформил исходную продажу, а не того, кто принял товар обратно.
    for s in sales:
        _group(by_user, s["created_by"] or 0, seller(s["created_by"])).add(
            float(s["total"]), 0.0
        )
        touch_bucket(s["occurred_at"])["receipts"] += 1
    for row in lines:
        _group(by_user, row["created_by"] or 0, seller(row["created_by"])).add(
            0.0, float(row["qty"])
        )
    for row in returns:
        factor = _factor(row["sale_gross"], row["discount"])
        _group(by_user, row["created_by"] or 0, seller(row["created_by"])).add(
            -float(row["qty"]) * float(row["unit_price"]) * factor, -float(row["qty"])
        )

    revenue_total = after_discount - returns_amount
    units_total = sum(float(r["qty"]) for r in lines) - returns_units

    writeoff_units = writeoff_amount = 0.0
    receipt_units = 0.0
    adjust_delta = 0.0
    for m in movements:
        if m["kind"] == "writeoff":
            writeoff_units += -float(m["qty"])
            writeoff_amount += -float(m["qty"]) * float(m["price"])
        elif m["kind"] == "receipt":
            receipt_units += float(m["qty"])
        else:
            adjust_delta += float(m["qty"])

    # ==== Динамика: заполняем пропуски, чтобы график не «сжимался» ====
    series = []
    if per_bucket:
        keys = sorted(per_bucket)
        key = keys[0]
        while key <= keys[-1]:
            point = per_bucket.get(key, {"revenue": 0.0, "units": 0.0, "receipts": 0})
            series.append(
                {
                    "key": key,
                    "label": bucket_label(key, granularity),
                    "revenue": round(point["revenue"], 2),
                    "units": round(point["units"], 3),
                    "receipts": point["receipts"],
                }
            )
            key = next_bucket(key, granularity)

    # ==== Склад ====
    stock_units = stock_value = 0.0
    low, dead = [], []
    for r in stock_rows:
        qty = float(r["stock"] or 0)
        if qty > 0:
            stock_units += qty
            stock_value += qty * float(r["price"])
        if r["min_stock"] > 0 and qty <= r["min_stock"]:
            low.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "category_name": r["category_name"],
                    "color": r["category_color"],
                    "supplier_name": r["supplier_name"],
                    "stock": round(qty, 3),
                    "min_stock": r["min_stock"],
                }
            )
        if qty > 0 and (r["last_sale"] is None or r["last_sale"] < dead_cutoff):
            dead.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "category_name": r["category_name"],
                    "color": r["category_color"],
                    "supplier_name": r["supplier_name"],
                    "stock": round(qty, 3),
                    "value": round(qty * float(r["price"]), 2),
                    "last_sale": r["last_sale"],
                }
            )
    low.sort(key=lambda x: x["stock"])
    dead.sort(key=lambda x: x["value"], reverse=True)

    products_ranked = _finish(by_product, revenue_total)

    return {
        "period": period,
        "label": label,
        "date_from": None if start == MIN_DATE else start,
        "date_to": end,
        "currency": CURRENCY,
        "totals": {
            "revenue": round(revenue_total, 2),
            "gross": round(after_discount + discount_total, 2),
            "discount": round(discount_total, 2),
            "units": round(units_total, 3),
            "receipts": receipts,
            "avg_receipt": round(after_discount / receipts, 2) if receipts else 0.0,
            "returns_units": round(returns_units, 3),
            "returns_amount": round(returns_amount, 2),
            "writeoff_units": round(writeoff_units, 3),
            "writeoff_amount": round(writeoff_amount, 2),
            "receipt_units": round(receipt_units, 3),
            "adjust_delta": round(adjust_delta, 3),
            "stock_units": round(stock_units, 3),
            "stock_value": round(stock_value, 2),
        },
        "by_category": _finish(by_category, revenue_total),
        "by_subcategory": _finish(by_subcategory, revenue_total),
        "by_supplier": _finish(by_supplier, revenue_total),
        "by_payment": _finish(by_payment, revenue_total),
        "by_user": _finish(by_user, revenue_total),
        "top_products": products_ranked[:TOP_LIMIT],
        "worst_products": [p for p in products_ranked if p["units"] > 0][-TOP_LIMIT:][::-1],
        "by_attribute": {
            "attribute": attribute_meta,
            "values": _finish(by_attribute, revenue_total),
        }
        if attribute_id
        else None,
        "attributes_available": attributes_available,
        "series": {"granularity": granularity, "points": series},
        "stock": {"low": low, "dead": dead, "dead_after_days": settings.dead_stock_days},
    }


def resolve_or_400(
    period: str, date_from: str | None, date_to: str | None
) -> tuple[str, str, str]:
    if period not in PERIOD_IDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный период")
    try:
        return resolve_period(period, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("")
def stats(
    user: dict = Depends(get_current_user),
    period: str = Query(default="month"),
    date_from: str | None = None,
    date_to: str | None = None,
    attribute_id: int | None = None,
):
    start, end, label = resolve_or_400(period, date_from, date_to)
    return build_stats(start, end, label, period, attribute_id)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export.xlsx")
def export_xlsx(
    user: dict = Depends(get_current_user),
    period: str = Query(default="month"),
    date_from: str | None = None,
    date_to: str | None = None,
    attribute_id: int | None = None,
):
    start, end, label = resolve_or_400(period, date_from, date_to)
    data = build_stats(start, end, label, period, attribute_id)
    buffer = build_workbook(data)

    pretty = f"Статистика {data['date_from'] or 'всё'} — {data['date_to']}.xlsx"
    # Кириллица в имени файла требует RFC 5987: ASCII-вариант для старых клиентов
    # плюс filename* с процентным кодированием для остальных.
    disposition = (
        f'attachment; filename="store-stats.xlsx"; '
        f"filename*=UTF-8''{quote(pretty)}"
    )
    return StreamingResponse(
        buffer, media_type=XLSX_MIME, headers={"Content-Disposition": disposition}
    )

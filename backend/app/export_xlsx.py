from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from .constants import MOVEMENT_LABELS, PAYMENT_METHODS
from .db import get_conn

MONEY = '#,##0.00'
QTY = '#,##0.###'
PERCENT = '#,##0.0'

# Разрезы (поставщики, категории, подкатегории) считаются из одного и того же
# подробного набора строк по товарам, поэтому у всех одинаковые колонки:
# и продажи, и склад в одной таблице — именно этого не хватало в отчёте.
GROUP_HEADERS = [
    "Название", "Товаров", "Продано, шт", "Выручка", "Доля, %",
    "Возвращено, шт", "Списано, шт", "Поступило, шт", "Остаток, шт", "Остаток, сумма",
]
GROUP_FORMATS = {3: QTY, 4: MONEY, 5: PERCENT, 6: QTY, 7: QTY, 8: QTY, 9: QTY, 10: MONEY}

# Выручка по позиции с учётом скидки на чек: скидка задаётся на весь чек,
# поэтому разносится пропорционально суммам позиций — так же, как в статистике.
_FACTOR = "CASE WHEN g.g > 0 THEN (g.g - s.discount) / g.g ELSE 1 END"

_PRODUCTS_SQL = f"""
WITH gross AS (
    SELECT sale_id, SUM(subtotal) AS g FROM sale_items GROUP BY sale_id
),
sold AS (
    SELECT i.product_id,
           SUM(i.qty) AS qty,
           SUM(i.subtotal * {_FACTOR}) AS revenue
    FROM sale_items i
    JOIN sales s ON s.id = i.sale_id
    JOIN gross g ON g.sale_id = i.sale_id
    WHERE s.occurred_at BETWEEN :start AND :end
    GROUP BY i.product_id
),
back AS (
    SELECT i.product_id,
           SUM(m.qty) AS qty,
           SUM(m.qty * i.unit_price * {_FACTOR}) AS amount
    FROM stock_movements m
    JOIN sale_items i ON i.id = m.sale_item_id
    JOIN sales s ON s.id = i.sale_id
    JOIN gross g ON g.sale_id = i.sale_id
    WHERE m.kind = 'return' AND m.occurred_at BETWEEN :start AND :end
    GROUP BY i.product_id
),
moved AS (
    SELECT product_id,
           SUM(CASE WHEN kind = 'receipt'  THEN qty ELSE 0 END) AS received,
           SUM(CASE WHEN kind = 'writeoff' THEN -qty ELSE 0 END) AS written_off,
           SUM(CASE WHEN kind = 'adjust'   THEN qty ELSE 0 END) AS adjusted
    FROM stock_movements
    WHERE occurred_at BETWEEN :start AND :end
    GROUP BY product_id
),
agg AS (
    SELECT product_id, SUM(qty) AS stock,
           MAX(CASE WHEN kind = 'sale' THEN occurred_at END) AS last_sale
    FROM stock_movements GROUP BY product_id
)
SELECT p.id, p.name, p.barcode, p.price, p.min_stock, p.archived, p.note,
       c.name AS category_name, sc.name AS subcategory_name, sup.name AS supplier_name,
       COALESCE(sold.qty, 0)      AS sold_qty,
       COALESCE(sold.revenue, 0)  AS sold_revenue,
       COALESCE(back.qty, 0)      AS returned_qty,
       COALESCE(back.amount, 0)   AS returned_amount,
       COALESCE(moved.received, 0)    AS received,
       COALESCE(moved.written_off, 0) AS written_off,
       COALESCE(moved.adjusted, 0)    AS adjusted,
       COALESCE(agg.stock, 0) AS stock,
       agg.last_sale
FROM products p
JOIN categories c ON c.id = p.category_id
LEFT JOIN subcategories sc ON sc.id = p.subcategory_id
JOIN suppliers sup ON sup.id = p.supplier_id
LEFT JOIN sold  ON sold.product_id = p.id
LEFT JOIN back  ON back.product_id = p.id
LEFT JOIN moved ON moved.product_id = p.id
LEFT JOIN agg   ON agg.product_id = p.id
-- Архивный товар попадает в отчёт, только если в периоде по нему было движение
-- или на складе ещё лежит остаток: иначе он засоряет таблицу нулями.
WHERE p.archived = 0 OR sold.qty IS NOT NULL OR COALESCE(agg.stock, 0) <> 0
ORDER BY sup.name, c.name, p.name
"""

_ATTR_SQL = """
SELECT a.id AS attribute_id, a.name AS attribute_name, c.name AS category_name,
       pa.product_id, pa.value
FROM product_attributes pa
JOIN attributes a ON a.id = pa.attribute_id
JOIN categories c ON c.id = a.category_id
ORDER BY c.sort_order, a.sort_order, pa.value
"""

_MOVEMENTS_SQL = """
SELECT m.occurred_at, m.kind, m.qty, m.reason, m.sale_id,
       p.name AS product_name, p.barcode, p.price,
       c.name AS category_name, sup.name AS supplier_name,
       u.display_name AS author
FROM stock_movements m
JOIN products p ON p.id = m.product_id
JOIN categories c ON c.id = p.category_id
JOIN suppliers sup ON sup.id = p.supplier_id
LEFT JOIN users u ON u.id = m.created_by
WHERE m.occurred_at BETWEEN :start AND :end
ORDER BY m.occurred_at, m.id
"""

_RECEIPTS_SQL = """
SELECT s.id, s.occurred_at, s.payment_method, s.customer, s.note, s.discount, s.total,
       u.display_name AS author,
       i.qty, i.unit_price, i.subtotal,
       p.name AS product_name, p.barcode,
       c.name AS category_name, sc.name AS subcategory_name,
       sup.name AS supplier_name,
       COALESCE((SELECT SUM(qty) FROM stock_movements
                 WHERE kind = 'return' AND sale_item_id = i.id), 0) AS returned
FROM sale_items i
JOIN sales s ON s.id = i.sale_id
LEFT JOIN users u ON u.id = s.created_by
JOIN products p ON p.id = i.product_id
JOIN categories c ON c.id = p.category_id
LEFT JOIN subcategories sc ON sc.id = p.subcategory_id
JOIN suppliers sup ON sup.id = p.supplier_id
WHERE s.occurred_at BETWEEN :start AND :end
ORDER BY s.occurred_at, s.id, i.id
"""


def _sheet(
    wb: Workbook,
    title: str,
    headers: list[str],
    rows: list[list],
    formats: dict[int, str],
    autofilter: bool = True,
):
    # Excel не принимает названия листов длиннее 31 символа.
    ws = wb.create_sheet(title[:31])
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    for row in rows:
        ws.append(row)

    for idx, header in enumerate(headers, start=1):
        letter = get_column_letter(idx)
        # Строки-разделители в сводке короче шапки, поэтому длину берём аккуратно.
        lengths = [len(str(header))] + [
            len(str(r[idx - 1])) for r in rows if idx - 1 < len(r)
        ]
        ws.column_dimensions[letter].width = min(max(11, max(lengths) + 2), 42)
        fmt = formats.get(idx)
        if fmt:
            for cell in ws[letter][1:]:
                cell.number_format = fmt
    if rows and autofilter:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    return ws


def _chart(ws, kind: str, title: str, count: int, value_cols: list[int], cat_col: int = 1):
    """График рисуем средствами openpyxl: он уже в зависимостях, а нативный
    график в Excel остаётся живым — его можно пересчитать и перекрасить."""
    if not count:
        return
    chart = {"bar": BarChart, "line": LineChart, "pie": PieChart}[kind]()
    chart.title = title
    chart.height, chart.width = 9, 22
    for col in value_cols:
        chart.add_data(
            Reference(ws, min_col=col, min_row=1, max_row=count + 1), titles_from_data=True
        )
    chart.set_categories(Reference(ws, min_col=cat_col, min_row=2, max_row=count + 1))
    if kind == "pie":
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showPercent = True
    # Под таблицей: так график не накрывает данные и виден сразу при открытии листа.
    ws.add_chart(chart, f"A{count + 4}")


def _fetch(start: str, end: str) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    with get_conn() as conn:
        dates = {"start": start, "end": end}
        products = [dict(r) for r in conn.execute(_PRODUCTS_SQL, dates)]
        attrs = [dict(r) for r in conn.execute(_ATTR_SQL)]
        movements = [dict(r) for r in conn.execute(_MOVEMENTS_SQL, dates)]
        receipts = [dict(r) for r in conn.execute(_RECEIPTS_SQL, dates)]

    params: dict[int, list[str]] = {}
    for a in attrs:
        params.setdefault(a["product_id"], []).append(f"{a['attribute_name']}: {a['value']}")
    for p in products:
        p["revenue"] = round(p["sold_revenue"] - p["returned_amount"], 2)
        p["stock"] = round(p["stock"], 3)
        p["stock_value"] = round(p["stock"] * p["price"], 2) if p["stock"] > 0 else 0.0
        p["params"] = " · ".join(params.get(p["id"], []))
    return products, attrs, movements, receipts


def _group_rows(products: list[dict], key: str, default: str, revenue_total: float):
    groups: dict[str, dict] = {}
    for p in products:
        g = groups.setdefault(
            p[key] or default,
            dict.fromkeys(
                ("products", "sold_qty", "revenue", "returned_qty",
                 "written_off", "received", "stock", "stock_value"),
                0.0,
            ),
        )
        g["products"] += 1
        for field in ("sold_qty", "revenue", "returned_qty", "written_off", "received",
                      "stock", "stock_value"):
            g[field] += p[field]

    rows = [
        [
            name,
            int(g["products"]),
            round(g["sold_qty"], 3),
            round(g["revenue"], 2),
            round(g["revenue"] / revenue_total * 100, 1) if revenue_total else 0.0,
            round(g["returned_qty"], 3),
            round(g["written_off"], 3),
            round(g["received"], 3),
            round(g["stock"], 3),
            round(g["stock_value"], 2),
        ]
        for name, g in groups.items()
    ]
    rows.sort(key=lambda r: (-r[3], r[0]))
    return rows


def _attribute_rows(products: list[dict], attrs: list[dict], revenue_total: float):
    """Разрез по каждому настраиваемому полю сразу, а не только по выбранному
    на экране: в файле должно быть всё, что вообще посчитано."""
    by_id = {p["id"]: p for p in products}
    groups: dict[tuple, dict] = {}
    for a in attrs:
        product = by_id.get(a["product_id"])
        if product is None:
            continue
        key = (a["category_name"], a["attribute_name"], a["value"])
        g = groups.setdefault(
            key,
            dict.fromkeys(("products", "sold_qty", "revenue", "stock", "stock_value"), 0.0),
        )
        g["products"] += 1
        for field in ("sold_qty", "revenue", "stock", "stock_value"):
            g[field] += product[field]

    rows = [
        [
            cat, attr, value, int(g["products"]),
            round(g["sold_qty"], 3),
            round(g["revenue"], 2),
            round(g["revenue"] / revenue_total * 100, 1) if revenue_total else 0.0,
            round(g["stock"], 3),
            round(g["stock_value"], 2),
        ]
        for (cat, attr, value), g in groups.items()
    ]
    rows.sort(key=lambda r: (r[0], r[1], -r[5]))
    return rows


def _breakdown(wb, title, items, extra_header=None, extra_key=None):
    headers = ["Название"]
    if extra_header:
        headers.append(extra_header)
    headers += ["Выручка", "Штук", "Доля, %"]
    rows = []
    for it in items:
        row = [it["name"]]
        if extra_key:
            row.append(it.get(extra_key) or "")
        row += [it["revenue"], it["units"], it["percent"]]
        rows.append(row)
    money_col = 3 if extra_header else 2
    return _sheet(
        wb, title, headers, rows,
        {money_col: MONEY, money_col + 1: QTY, money_col + 2: PERCENT},
    )


def build_workbook(stats: dict) -> BytesIO:
    wb = Workbook()
    wb.remove(wb.active)
    totals = stats["totals"]
    start = stats["date_from"] or "0001-01-01"
    products, attrs, movements, receipts = _fetch(start, stats["date_to"])
    revenue_total = totals["revenue"]

    # ==== Сводка ====
    in_stock = [p for p in products if p["stock"] > 0]
    summary = [
        ["Период", stats["label"]],
        ["С", stats["date_from"] or "начала учёта"],
        ["По", stats["date_to"]],
        [],
        ["Выручка (после скидок и возвратов)", totals["revenue"]],
        ["Сумма позиций до скидок", totals["gross"]],
        ["Скидки", totals["discount"]],
        ["Возвраты, сумма", totals["returns_amount"]],
        ["Возвраты, штук", totals["returns_units"]],
        [],
        ["Продано единиц", totals["units"]],
        ["Чеков", totals["receipts"]],
        ["Средний чек", totals["avg_receipt"]],
        ["Позиций в чеках", len(receipts)],
        [],
        ["Списано единиц", totals["writeoff_units"]],
        ["Списано на сумму", totals["writeoff_amount"]],
        ["Поступило единиц", totals["receipt_units"]],
        ["Расхождения инвентаризаций", totals["adjust_delta"]],
        ["Движений по складу", len(movements)],
        [],
        ["Остаток на складе, единиц", totals["stock_units"]],
        ["Остаток на складе, сумма", totals["stock_value"]],
        ["Позиций в отчёте", len(products)],
        ["Позиций с остатком", len(in_stock)],
        ["Позиций без остатка", len(products) - len(in_stock)],
        ["Поставщиков", len({p["supplier_name"] for p in products})],
        ["Категорий", len({p["category_name"] for p in products})],
        ["Пора дозаказать, позиций", len(stats["stock"]["low"])],
        [f"Не продаётся дольше {stats['stock']['dead_after_days']} дней, позиций",
         len(stats["stock"]["dead"])],
    ]
    ws = _sheet(
        wb, "Сводка", ["Показатель", f"Значение, {stats['currency']}"],
        summary, {}, autofilter=False,
    )
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 22

    # ==== Каждая позиция: что продано и что лежит на складе ====
    _sheet(
        wb, "Товары",
        [
            "Товар", "Штрихкод", "Категория", "Подкатегория", "Поставщик", "Параметры",
            "Цена", "Продано, шт", "Выручка", "Возвращено, шт", "Возвращено, сумма",
            "Списано, шт", "Поступило, шт", "Инвентаризация, ±", "Остаток, шт",
            "Остаток, сумма", "Минимум", "Последняя продажа", "Архив", "Комментарий",
        ],
        [
            [
                p["name"], p["barcode"] or "", p["category_name"], p["subcategory_name"] or "",
                p["supplier_name"], p["params"], p["price"],
                round(p["sold_qty"], 3), p["revenue"],
                round(p["returned_qty"], 3), round(p["returned_amount"], 2),
                round(p["written_off"], 3), round(p["received"], 3), round(p["adjusted"], 3),
                p["stock"], p["stock_value"], p["min_stock"],
                p["last_sale"] or "не продавался",
                "да" if p["archived"] else "", p["note"],
            ]
            for p in products
        ],
        {7: MONEY, 8: QTY, 9: MONEY, 10: QTY, 11: MONEY, 12: QTY, 13: QTY, 14: QTY,
         15: QTY, 16: MONEY, 17: QTY},
    )

    # ==== Разрезы: продажи и остатки в одной таблице ====
    supplier_rows = _group_rows(products, "supplier_name", "—", revenue_total)
    ws = _sheet(wb, "По поставщикам", GROUP_HEADERS, supplier_rows, GROUP_FORMATS)
    _chart(ws, "bar", "Поставщики: выручка и остаток на складе",
           len(supplier_rows), [4, 10])

    category_rows = _group_rows(products, "category_name", "—", revenue_total)
    ws = _sheet(wb, "По категориям", GROUP_HEADERS, category_rows, GROUP_FORMATS)
    _chart(ws, "pie", "Доля категорий в выручке", len(category_rows), [4])

    sub_rows = _group_rows(products, "subcategory_name", "Без подкатегории", revenue_total)
    ws = _sheet(wb, "По подкатегориям", GROUP_HEADERS, sub_rows, GROUP_FORMATS)
    _chart(ws, "bar", "Подкатегории: выручка", len(sub_rows), [4])

    attribute_rows = _attribute_rows(products, attrs, revenue_total)
    _sheet(
        wb, "По полям товара",
        ["Категория", "Поле", "Значение", "Товаров", "Продано, шт", "Выручка",
         "Доля, %", "Остаток, шт", "Остаток, сумма"],
        attribute_rows,
        {5: QTY, 6: MONEY, 7: PERCENT, 8: QTY, 9: MONEY},
    )

    _breakdown(wb, "Топ товаров", stats["top_products"], "Категория", "category_name")
    _breakdown(wb, "Хуже всего продаётся", stats["worst_products"], "Категория", "category_name")
    _breakdown(wb, "По продавцам", stats["by_user"])
    ws = _breakdown(wb, "По оплате", stats["by_payment"])
    _chart(ws, "pie", "Способы оплаты", len(stats["by_payment"]), [2])

    # ==== Динамика ====
    points = stats["series"]["points"]
    ws = _sheet(
        wb, "Динамика",
        ["Период", "Выручка", "Штук", "Чеков"],
        [[p["label"], p["revenue"], p["units"], p["receipts"]] for p in points],
        {2: MONEY, 3: QTY},
    )
    _chart(ws, "line", "Выручка по периодам", len(points), [2])

    # ==== Первичка ====
    _sheet(
        wb, "Чеки",
        [
            "Чек", "Дата", "Товар", "Штрихкод", "Категория", "Подкатегория", "Поставщик",
            "Кол-во", "Цена", "Сумма", "Возвращено", "Скидка на чек", "Итог чека",
            "Оплата", "Покупатель", "Продавец", "Комментарий",
        ],
        [
            [
                r["id"], r["occurred_at"], r["product_name"], r["barcode"] or "",
                r["category_name"], r["subcategory_name"] or "", r["supplier_name"],
                float(r["qty"]), float(r["unit_price"]), float(r["subtotal"]),
                float(r["returned"]), float(r["discount"]), float(r["total"]),
                PAYMENT_METHODS.get(r["payment_method"], r["payment_method"]),
                r["customer"] or "", r["author"] or "", r["note"] or "",
            ]
            for r in receipts
        ],
        {8: QTY, 9: MONEY, 10: MONEY, 11: QTY, 12: MONEY, 13: MONEY},
    )

    _sheet(
        wb, "Движения склада",
        ["Дата", "Операция", "Товар", "Штрихкод", "Категория", "Поставщик",
         "Количество", "Сумма по цене", "Чек", "Причина", "Кто"],
        [
            [
                m["occurred_at"], MOVEMENT_LABELS.get(m["kind"], m["kind"]),
                m["product_name"], m["barcode"] or "", m["category_name"],
                m["supplier_name"], float(m["qty"]),
                round(float(m["qty"]) * float(m["price"]), 2),
                m["sale_id"] or "", m["reason"], m["author"] or "",
            ]
            for m in movements
        ],
        {7: QTY, 8: MONEY},
    )

    # ==== Склад: что заканчивается и что лежит мёртвым грузом ====
    _sheet(
        wb, "Пора дозаказать",
        ["Товар", "Категория", "Поставщик", "Остаток", "Минимум"],
        [
            [r["name"], r["category_name"], r["supplier_name"], r["stock"], r["min_stock"]]
            for r in stats["stock"]["low"]
        ],
        {4: QTY, 5: QTY},
    )

    _sheet(
        wb, "Мёртвый сток",
        ["Товар", "Категория", "Поставщик", "Остаток", "Сумма", "Последняя продажа"],
        [
            [
                r["name"], r["category_name"], r["supplier_name"],
                r["stock"], r["value"], r["last_sale"] or "не продавался",
            ]
            for r in stats["stock"]["dead"]
        ],
        {4: QTY, 5: MONEY},
    )

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import settings
from ..constants import MANUAL_MOVEMENT_KINDS, MOVEMENT_LABELS
from ..db import fold, get_conn
from ..schemas import MovementIn, ProductIn
from ..security import get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])

# Остаток и дата последней продажи считаются из движений, а не хранятся.
_BASE_SELECT = """
SELECT p.*,
       c.name AS category_name, c.color AS category_color, c.icon AS category_icon,
       sc.name AS subcategory_name,
       s.name AS supplier_name,
       COALESCE(agg.stock, 0) AS stock,
       agg.last_sale
FROM products p
JOIN categories c ON c.id = p.category_id
JOIN suppliers s ON s.id = p.supplier_id
LEFT JOIN subcategories sc ON sc.id = p.subcategory_id
LEFT JOIN (
    SELECT product_id,
           SUM(qty) AS stock,
           MAX(CASE WHEN kind = 'sale' THEN occurred_at END) AS last_sale
    FROM stock_movements GROUP BY product_id
) agg ON agg.product_id = p.id
"""


def stock_of(conn, product_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS s FROM stock_movements WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    return float(row["s"])


def _attributes_for(conn, product_ids: list[int]) -> dict[int, list[dict]]:
    if not product_ids:
        return {}
    marks = ",".join("?" * len(product_ids))
    rows = conn.execute(
        f"""
        SELECT pa.product_id, pa.attribute_id, pa.value, a.name, a.kind
        FROM product_attributes pa
        JOIN attributes a ON a.id = pa.attribute_id
        WHERE pa.product_id IN ({marks})
        ORDER BY a.sort_order, a.id
        """,
        product_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(
            {
                "attribute_id": r["attribute_id"],
                "name": r["name"],
                "kind": r["kind"],
                "value": r["value"],
            }
        )
    return out


def _shape(row: dict, attributes: list[dict]) -> dict:
    item = dict(row)
    item["archived"] = bool(item["archived"])
    item["stock"] = round(float(item["stock"] or 0), 3)
    item["attributes"] = attributes
    item["low_stock"] = item["min_stock"] > 0 and item["stock"] <= item["min_stock"]
    return item


@router.get("")
def list_products(
    user: dict = Depends(get_current_user),
    search: str = "",
    category_id: int | None = None,
    subcategory_id: int | None = None,
    supplier_id: int | None = None,
    attribute_id: int | None = None,
    attribute_value: str | None = None,
    stock: str | None = Query(default=None, description="low | out | in | dead"),
    archived: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    where = ["p.archived = ?"]
    args: list = [int(archived)]

    # Слова ищутся независимо друг от друга: «майка рик» находит «Майка Rick and
    # Morty», хотя подряд эти слова в названии не стоят. fold() — своя функция,
    # она складывает регистр кириллицы и «ё» с «е» (см. db.fold).
    for word in fold(search).split():
        # Ищем и по значениям настраиваемых полей: «найди по надписи» — рабочий сценарий.
        like = f"%{word}%"
        where.append(
            """(fold(p.name) LIKE ? OR p.barcode LIKE ? OR fold(p.note) LIKE ?
                OR EXISTS (SELECT 1 FROM product_attributes pa
                           WHERE pa.product_id = p.id AND fold(pa.value) LIKE ?))"""
        )
        args += [like, like, like, like]
    if category_id:
        where.append("p.category_id = ?")
        args.append(category_id)
    if subcategory_id:
        where.append("p.subcategory_id = ?")
        args.append(subcategory_id)
    if supplier_id:
        where.append("p.supplier_id = ?")
        args.append(supplier_id)
    if attribute_id and attribute_value:
        where.append(
            "EXISTS (SELECT 1 FROM product_attributes pa2 "
            "WHERE pa2.product_id = p.id AND pa2.attribute_id = ? AND pa2.value = ?)"
        )
        args += [attribute_id, attribute_value]

    if stock == "low":
        where.append("p.min_stock > 0 AND COALESCE(agg.stock, 0) <= p.min_stock")
    elif stock == "out":
        where.append("COALESCE(agg.stock, 0) <= 0")
    elif stock == "in":
        where.append("COALESCE(agg.stock, 0) > 0")
    elif stock == "dead":
        cutoff = (date.today() - timedelta(days=settings.dead_stock_days)).isoformat()
        where.append(
            "COALESCE(agg.stock, 0) > 0 AND (agg.last_sale IS NULL OR agg.last_sale < ?)"
        )
        args.append(cutoff)

    sql = f"{_BASE_SELECT} WHERE {' AND '.join(where)} ORDER BY p.name COLLATE NOCASE LIMIT ? OFFSET ?"
    with get_conn() as conn:
        rows = conn.execute(sql, [*args, limit, offset]).fetchall()
        attrs = _attributes_for(conn, [r["id"] for r in rows])
    return [_shape(r, attrs.get(r["id"], [])) for r in rows]


@router.get("/by-barcode/{code}")
def product_by_barcode(code: str, user: dict = Depends(get_current_user)):
    """Используется сканером: код с камеры сразу превращается в товар."""
    with get_conn() as conn:
        row = conn.execute(
            f"{_BASE_SELECT} WHERE p.barcode = ? AND p.archived = 0", (code.strip(),)
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар с таким кодом не найден")
        attrs = _attributes_for(conn, [row["id"]])
    return _shape(row, attrs.get(row["id"], []))


@router.get("/{product_id}")
def get_product(product_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(f"{_BASE_SELECT} WHERE p.id = ?", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
        attrs = _attributes_for(conn, [product_id])
        history = conn.execute(
            """
            SELECT m.id, m.kind, m.qty, m.reason, m.occurred_at, m.sale_id,
                   u.display_name AS author
            FROM stock_movements m
            LEFT JOIN users u ON u.id = m.created_by
            WHERE m.product_id = ?
            ORDER BY m.occurred_at DESC, m.id DESC
            LIMIT 200
            """,
            (product_id,),
        ).fetchall()
    item = _shape(row, attrs.get(product_id, []))
    item["history"] = [
        {**dict(h), "label": MOVEMENT_LABELS.get(h["kind"], h["kind"])} for h in history
    ]
    return item


# ==== Создание и изменение ====


def _clean_barcode(value: str | None) -> str | None:
    code = (value or "").strip()
    return code or None


def _validate_refs(conn, body: ProductIn) -> None:
    if conn.execute(
        "SELECT 1 FROM categories WHERE id = ?", (body.category_id,)
    ).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")
    if conn.execute(
        "SELECT 1 FROM suppliers WHERE id = ?", (body.supplier_id,)
    ).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поставщик не найден")
    if body.subcategory_id is not None:
        row = conn.execute(
            "SELECT category_id FROM subcategories WHERE id = ?", (body.subcategory_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Подкатегория не найдена")
        if row["category_id"] != body.category_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Подкатегория относится к другой категории"
            )


def _write_attributes(conn, product_id: int, category_id: int, values: dict[int, str]) -> None:
    """Значения полей заменяются целиком: при смене категории набор полей другой,
    и остатки старых значений исказили бы статистику."""
    defined = {
        r["id"]: r
        for r in conn.execute(
            "SELECT id, name, required FROM attributes WHERE category_id = ? AND archived = 0",
            (category_id,),
        )
    }
    cleaned: dict[int, str] = {}
    for attr_id, raw in values.items():
        if attr_id not in defined:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Поле не относится к выбранной категории"
            )
        value = " ".join(str(raw).split())
        if value:
            cleaned[attr_id] = value

    for attr_id, attr in defined.items():
        if attr["required"] and attr_id not in cleaned:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Поле «{attr['name']}» обязательно"
            )

    conn.execute("DELETE FROM product_attributes WHERE product_id = ?", (product_id,))
    conn.executemany(
        "INSERT INTO product_attributes (product_id, attribute_id, value) VALUES (?, ?, ?)",
        [(product_id, aid, val) for aid, val in cleaned.items()],
    )


def _check_barcode_free(conn, code: str | None, exclude_id: int | None = None) -> None:
    if not code:
        return
    row = conn.execute(
        "SELECT id, name FROM products WHERE barcode = ? AND id IS NOT ?",
        (code, exclude_id),
    ).fetchone()
    if row is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Этот штрихкод уже у товара «{row['name']}»"
        )


@router.post("")
def create_product(body: ProductIn, user: dict = Depends(get_current_user)):
    name = " ".join(body.name.split())
    barcode = _clean_barcode(body.barcode)
    with get_conn() as conn:
        _validate_refs(conn, body)
        _check_barcode_free(conn, barcode)
        product_id = conn.execute(
            """
            INSERT INTO products
                (name, category_id, subcategory_id, supplier_id, price, barcode,
                 min_stock, note, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                body.category_id,
                body.subcategory_id,
                body.supplier_id,
                body.price,
                barcode,
                body.min_stock,
                body.note.strip(),
                user["id"],
            ),
        ).lastrowid
        _write_attributes(conn, product_id, body.category_id, body.attributes)
        if body.initial_qty > 0:
            conn.execute(
                """
                INSERT INTO stock_movements
                    (product_id, kind, qty, reason, occurred_at, created_by)
                VALUES (?, 'receipt', ?, 'Первичный приход', ?, ?)
                """,
                (product_id, body.initial_qty, date.today().isoformat(), user["id"]),
            )
        conn.commit()
    return {"id": product_id}


@router.patch("/{product_id}")
def update_product(product_id: int, body: ProductIn, user: dict = Depends(get_current_user)):
    name = " ".join(body.name.split())
    barcode = _clean_barcode(body.barcode)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
        _validate_refs(conn, body)
        _check_barcode_free(conn, barcode, product_id)
        conn.execute(
            """
            UPDATE products SET
                name = ?, category_id = ?, subcategory_id = ?, supplier_id = ?,
                price = ?, barcode = ?, min_stock = ?, note = ?
            WHERE id = ?
            """,
            (
                name,
                body.category_id,
                body.subcategory_id,
                body.supplier_id,
                body.price,
                barcode,
                body.min_stock,
                body.note.strip(),
                product_id,
            ),
        )
        _write_attributes(conn, product_id, body.category_id, body.attributes)
        conn.commit()
    return {"ok": True}


@router.delete("/{product_id}")
def delete_product(product_id: int, user: dict = Depends(get_current_user)):
    """Товар, который уже продавался, только архивируется — иначе из статистики
    и чеков пропали бы проданные позиции."""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
        sold = conn.execute(
            "SELECT COUNT(*) AS c FROM sale_items WHERE product_id = ?", (product_id,)
        ).fetchone()["c"]
        if sold:
            conn.execute("UPDATE products SET archived = 1 WHERE id = ?", (product_id,))
            conn.commit()
            return {"archived": True, "sold_count": sold}
        conn.execute("DELETE FROM stock_movements WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM product_attributes WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
    return {"deleted": True}


@router.post("/{product_id}/restore")
def restore_product(product_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        changed = conn.execute(
            "UPDATE products SET archived = 0 WHERE id = ?", (product_id,)
        ).rowcount
        conn.commit()
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
    return {"ok": True}


# ==== Движения склада ====


@router.post("/{product_id}/movements")
def add_movement(product_id: int, body: MovementIn, user: dict = Depends(get_current_user)):
    if body.kind not in MANUAL_MOVEMENT_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимая операция")
    occurred = (body.occurred_at or date.today()).isoformat()

    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
        current = stock_of(conn, product_id)

        if body.kind == "adjust":
            # Пришло фактическое количество по пересчёту, а не изменение.
            if body.qty < 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Фактический остаток не может быть отрицательным"
                )
            delta = body.qty - current
            if delta == 0:
                return {"ok": True, "stock": current, "delta": 0}
            reason = body.reason.strip() or (
                f"Инвентаризация: было {current:g}, стало {body.qty:g}"
            )
        else:
            if body.qty <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Количество должно быть больше нуля")
            delta = body.qty if body.kind == "receipt" else -body.qty
            if current + delta < 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Нельзя списать {body.qty:g}: на складе только {current:g}",
                )
            reason = body.reason.strip()

        conn.execute(
            """
            INSERT INTO stock_movements (product_id, kind, qty, reason, occurred_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (product_id, body.kind, delta, reason, occurred, user["id"]),
        )
        conn.commit()
        return {"ok": True, "stock": current + delta, "delta": delta}


@router.delete("/{product_id}/movements/{movement_id}")
def delete_movement(product_id: int, movement_id: int, user: dict = Depends(get_current_user)):
    """Отмена ошибочно введённой операции. Продажи и возвраты правятся через чек,
    поэтому руками сносить их здесь нельзя."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT kind, qty FROM stock_movements WHERE id = ? AND product_id = ?",
            (movement_id, product_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Операция не найдена")
        if row["kind"] not in MANUAL_MOVEMENT_KINDS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Это движение создано продажей или возвратом — правьте через чек",
            )
        if stock_of(conn, product_id) - row["qty"] < 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "После отмены остаток стал бы отрицательным"
            )
        conn.execute("DELETE FROM stock_movements WHERE id = ?", (movement_id,))
        conn.commit()
    return {"ok": True}

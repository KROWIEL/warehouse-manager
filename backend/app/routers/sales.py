from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..constants import PAYMENT_METHODS
from ..db import get_conn
from ..periods import MAX_DATE, MIN_DATE
from ..schemas import ReturnIn, SaleIn
from ..security import get_current_user
from .products import stock_of

router = APIRouter(prefix="/api/sales", tags=["sales"])


def _items_for(conn, sale_ids: list[int]) -> dict[int, list[dict]]:
    if not sale_ids:
        return {}
    marks = ",".join("?" * len(sale_ids))
    rows = conn.execute(
        f"""
        SELECT i.id, i.sale_id, i.product_id, i.qty, i.unit_price, i.subtotal,
               p.name AS product_name, p.barcode,
               c.name AS category_name, c.color AS category_color,
               COALESCE(r.returned, 0) AS returned
        FROM sale_items i
        JOIN products p ON p.id = i.product_id
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN (
            SELECT sale_item_id, SUM(qty) AS returned
            FROM stock_movements WHERE kind = 'return' GROUP BY sale_item_id
        ) r ON r.sale_item_id = i.id
        WHERE i.sale_id IN ({marks})
        ORDER BY i.id
        """,
        sale_ids,
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        item = dict(r)
        item["returned"] = round(float(item["returned"] or 0), 3)
        out.setdefault(r["sale_id"], []).append(item)
    return out


@router.get("")
def list_sales(
    user: dict = Depends(get_current_user),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    start = date_from or MIN_DATE
    end = date_to or MAX_DATE
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*, u.display_name AS author
            FROM sales s
            LEFT JOIN users u ON u.id = s.created_by
            WHERE s.occurred_at BETWEEN ? AND ?
            ORDER BY s.occurred_at DESC, s.id DESC
            LIMIT ? OFFSET ?
            """,
            (start, end, limit, offset),
        ).fetchall()
        items = _items_for(conn, [r["id"] for r in rows])
    return [
        {
            **dict(r),
            "payment_label": PAYMENT_METHODS.get(r["payment_method"], r["payment_method"]),
            "items": items.get(r["id"], []),
        }
        for r in rows
    ]


@router.get("/{sale_id}")
def get_sale(sale_id: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*, u.display_name AS author
            FROM sales s LEFT JOIN users u ON u.id = s.created_by
            WHERE s.id = ?
            """,
            (sale_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Чек не найден")
        items = _items_for(conn, [sale_id])
    return {
        **dict(row),
        "payment_label": PAYMENT_METHODS.get(row["payment_method"], row["payment_method"]),
        "items": items.get(sale_id, []),
    }


@router.post("")
def create_sale(body: SaleIn, user: dict = Depends(get_current_user)):
    if body.payment_method not in PAYMENT_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный способ оплаты")
    occurred = (body.occurred_at or date.today()).isoformat()

    # Чек, позиции и движения склада пишутся в одной транзакции: соединение
    # закрывается без commit при любой ошибке, и продажа не остаётся половинчатой.
    with get_conn() as conn:
        wanted: dict[int, float] = defaultdict(float)
        for line in body.items:
            wanted[line.product_id] += line.qty

        prices: dict[int, float] = {}
        for product_id, qty in wanted.items():
            row = conn.execute(
                "SELECT name, price, archived FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Товар не найден")
            if row["archived"]:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, f"Товар «{row['name']}» в архиве"
                )
            prices[product_id] = float(row["price"])
            available = stock_of(conn, product_id)
            # Одну и ту же позицию можно добавить в корзину дважды — проверяем сумму.
            if qty > available:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"«{row['name']}»: на складе {available:g}, продать {qty:g} нельзя",
                )

        lines = []
        gross = 0.0
        for line in body.items:
            unit_price = prices[line.product_id] if line.unit_price is None else line.unit_price
            subtotal = round(line.qty * unit_price, 2)
            gross += subtotal
            lines.append((line.product_id, line.qty, unit_price, subtotal))

        gross = round(gross, 2)
        if body.discount > gross:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Скидка больше суммы чека"
            )
        total = round(gross - body.discount, 2)

        sale_id = conn.execute(
            """
            INSERT INTO sales
                (occurred_at, discount, payment_method, customer, total, note, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred,
                body.discount,
                body.payment_method,
                body.customer.strip(),
                total,
                body.note.strip(),
                user["id"],
            ),
        ).lastrowid

        for product_id, qty, unit_price, subtotal in lines:
            item_id = conn.execute(
                """
                INSERT INTO sale_items (sale_id, product_id, qty, unit_price, subtotal)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sale_id, product_id, qty, unit_price, subtotal),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO stock_movements
                    (product_id, kind, qty, sale_id, sale_item_id, occurred_at, created_by)
                VALUES (?, 'sale', ?, ?, ?, ?, ?)
                """,
                (product_id, -qty, sale_id, item_id, occurred, user["id"]),
            )

        conn.commit()
    return {"id": sale_id, "gross": gross, "total": total}


@router.delete("/{sale_id}")
def delete_sale(sale_id: int, user: dict = Depends(get_current_user)):
    """Полная отмена ошибочного чека: позиции и движения склада уходят каскадом,
    товар возвращается на склад сам, потому что остаток — это сумма движений."""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM sales WHERE id = ?", (sale_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Чек не найден")
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()
    return {"deleted": True}


@router.post("/returns")
def create_return(body: ReturnIn, user: dict = Depends(get_current_user)):
    occurred = (body.occurred_at or date.today()).isoformat()
    with get_conn() as conn:
        item = conn.execute(
            """
            SELECT i.id, i.sale_id, i.product_id, i.qty, i.unit_price,
                   p.name AS product_name, s.discount,
                   (SELECT SUM(subtotal) FROM sale_items WHERE sale_id = i.sale_id) AS sale_gross,
                   COALESCE((SELECT SUM(qty) FROM stock_movements
                             WHERE kind = 'return' AND sale_item_id = i.id), 0) AS returned
            FROM sale_items i
            JOIN sales s ON s.id = i.sale_id
            JOIN products p ON p.id = i.product_id
            WHERE i.id = ?
            """,
            (body.sale_item_id,),
        ).fetchone()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Позиция чека не найдена")

        left = float(item["qty"]) - float(item["returned"])
        if body.qty > left:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"По этой позиции можно вернуть не больше {left:g}",
            )

        conn.execute(
            """
            INSERT INTO stock_movements
                (product_id, kind, qty, sale_id, sale_item_id, reason, occurred_at, created_by)
            VALUES (?, 'return', ?, ?, ?, ?, ?, ?)
            """,
            (
                item["product_id"],
                body.qty,
                item["sale_id"],
                item["id"],
                body.reason.strip(),
                occurred,
                user["id"],
            ),
        )
        conn.commit()

    # Возвращаем ровно то, что покупатель заплатил: скидка была на весь чек,
    # поэтому на позицию приходится её пропорциональная часть.
    gross = float(item["sale_gross"] or 0)
    factor = (gross - float(item["discount"])) / gross if gross > 0 else 1.0
    return {
        "ok": True,
        "refund": round(body.qty * float(item["unit_price"]) * factor, 2),
        "left": round(left - body.qty, 3),
    }

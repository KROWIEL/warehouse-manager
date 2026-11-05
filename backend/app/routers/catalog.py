import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from ..constants import ATTRIBUTE_KINDS
from ..db import get_conn
from ..schemas import (
    AttributeIn,
    AttributePatch,
    CategoryIn,
    NameIn,
    OptionIn,
    SubcategoryIn,
    SupplierIn,
)
from ..security import get_current_user

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

# Таблицы, у которых удаление превращается в архивирование, если на запись
# уже кто-то ссылается. Восстановление идёт через один общий эндпоинт.
ARCHIVABLE = {
    "categories": "категория",
    "subcategories": "подкатегория",
    "suppliers": "поставщик",
    "attributes": "поле",
}


def _norm(value: str) -> str:
    """Схлопывает лишние пробелы: «  Майки   белые » -> «Майки белые»."""
    return " ".join(value.split())


def _key(value: str) -> str:
    # COLLATE NOCASE в SQLite работает только с латиницей, поэтому сравнение
    # регистронезависимо делаем в Python.
    return _norm(value).casefold()


def _next_order(conn, table: str, where: str = "", args: tuple = ()) -> int:
    sql = f"SELECT COALESCE(MAX(sort_order), 0) AS m FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql, args).fetchone()["m"] + 1


def _find_by_name(conn, table: str, name: str, where: str = "1=1", args: tuple = ()):
    """Ищет запись с таким же названием в пределах родителя, включая архивные."""
    target = _key(name)
    for row in conn.execute(f"SELECT id, name, archived FROM {table} WHERE {where}", args):
        if _key(row["name"]) == target:
            return row
    return None


# ==== Чтение: всё дерево справочников одним запросом ====
# На телефоне важнее один round-trip, чем аккуратность разбиения на ресурсы.


@router.get("")
def get_catalog(include_archived: bool = False, user: dict = Depends(get_current_user)):
    flt = "" if include_archived else " WHERE archived = 0"
    with get_conn() as conn:
        categories = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM categories{flt} ORDER BY sort_order, id"
            )
        ]
        subs = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM subcategories{flt} ORDER BY sort_order, id"
            )
        ]
        attrs = [
            dict(r)
            for r in conn.execute(f"SELECT * FROM attributes{flt} ORDER BY sort_order, id")
        ]
        options = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM attribute_options ORDER BY sort_order, id"
            )
        ]
        suppliers = [
            dict(r)
            for r in conn.execute(f"SELECT * FROM suppliers{flt} ORDER BY sort_order, id")
        ]
        counts = {
            r["category_id"]: r["c"]
            for r in conn.execute(
                "SELECT category_id, COUNT(*) AS c FROM products WHERE archived = 0 GROUP BY category_id"
            )
        }
        supplier_counts = {
            r["supplier_id"]: r["c"]
            for r in conn.execute(
                "SELECT supplier_id, COUNT(*) AS c FROM products WHERE archived = 0 GROUP BY supplier_id"
            )
        }

    by_attr: dict[int, list] = {}
    for o in options:
        by_attr.setdefault(o["attribute_id"], []).append({"id": o["id"], "value": o["value"]})
    for a in attrs:
        a["required"] = bool(a["required"])
        a["options"] = by_attr.get(a["id"], [])

    for c in categories:
        c["product_count"] = counts.get(c["id"], 0)
        c["subcategories"] = [s for s in subs if s["category_id"] == c["id"]]
        c["attributes"] = [a for a in attrs if a["category_id"] == c["id"]]
    for s in suppliers:
        s["product_count"] = supplier_counts.get(s["id"], 0)

    return {"categories": categories, "suppliers": suppliers}


# ==== Категории ====


@router.post("/categories")
def create_category(body: CategoryIn, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        found = _find_by_name(conn, "categories", name)
        if found:
            if not found["archived"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Такая категория уже есть")
            # Возвращаем из архива вместо создания дубля с тем же названием.
            conn.execute(
                "UPDATE categories SET archived = 0, color = ?, icon = ? WHERE id = ?",
                (body.color, body.icon, found["id"]),
            )
            conn.commit()
            return {"id": found["id"], "restored": True}

        cur = conn.execute(
            "INSERT INTO categories (name, color, icon, sort_order) VALUES (?, ?, ?, ?)",
            (name, body.color, body.icon, _next_order(conn, "categories")),
        )
        conn.commit()
        return {"id": cur.lastrowid}


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryIn, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        found = _find_by_name(conn, "categories", name)
        if found and found["id"] != category_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Категория с таким названием уже есть")
        changed = conn.execute(
            "UPDATE categories SET name = ?, color = ?, icon = ? WHERE id = ?",
            (name, body.color, body.icon, category_id),
        ).rowcount
        conn.commit()
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")
    return {"ok": True}


# ==== Подкатегории ====


@router.post("/subcategories")
def create_subcategory(body: SubcategoryIn, user: dict = Depends(get_current_user)):
    """Вызывается и из настроек, и прямо из формы товара — там подкатегория
    создаётся на лету, если её ещё нет."""
    name = _norm(body.name)
    with get_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", (body.category_id,)
        ).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

        found = _find_by_name(
            conn, "subcategories", name, "category_id = ?", (body.category_id,)
        )
        if found:
            if found["archived"]:
                conn.execute("UPDATE subcategories SET archived = 0 WHERE id = ?", (found["id"],))
                conn.commit()
            return {"id": found["id"], "name": found["name"], "existed": True}

        order = _next_order(conn, "subcategories", "category_id = ?", (body.category_id,))
        cur = conn.execute(
            "INSERT INTO subcategories (category_id, name, sort_order) VALUES (?, ?, ?)",
            (body.category_id, name, order),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": name}


@router.patch("/subcategories/{sub_id}")
def update_subcategory(sub_id: int, body: NameIn, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT category_id FROM subcategories WHERE id = ?", (sub_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Подкатегория не найдена")
        found = _find_by_name(
            conn, "subcategories", name, "category_id = ?", (row["category_id"],)
        )
        if found and found["id"] != sub_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Такая подкатегория уже есть")
        conn.execute("UPDATE subcategories SET name = ? WHERE id = ?", (name, sub_id))
        conn.commit()
    return {"ok": True}


# ==== Поставщики ====


@router.post("/suppliers")
def create_supplier(body: SupplierIn, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        found = _find_by_name(conn, "suppliers", name)
        if found:
            if not found["archived"]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Такой поставщик уже есть")
            conn.execute(
                "UPDATE suppliers SET archived = 0, note = ? WHERE id = ?",
                (body.note.strip(), found["id"]),
            )
            conn.commit()
            return {"id": found["id"], "restored": True}

        cur = conn.execute(
            "INSERT INTO suppliers (name, note, sort_order) VALUES (?, ?, ?)",
            (name, body.note.strip(), _next_order(conn, "suppliers")),
        )
        conn.commit()
        return {"id": cur.lastrowid}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        found = _find_by_name(conn, "suppliers", name)
        if found and found["id"] != supplier_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Поставщик с таким названием уже есть")
        changed = conn.execute(
            "UPDATE suppliers SET name = ?, note = ? WHERE id = ?",
            (name, body.note.strip(), supplier_id),
        ).rowcount
        conn.commit()
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поставщик не найден")
    return {"ok": True}


# ==== Настраиваемые поля товара ====


@router.post("/attributes")
def create_attribute(body: AttributeIn, user: dict = Depends(get_current_user)):
    if body.kind not in ATTRIBUTE_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный тип поля")
    name = _norm(body.name)
    with get_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", (body.category_id,)
        ).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

        found = _find_by_name(conn, "attributes", name, "category_id = ?", (body.category_id,))
        if found and not found["archived"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Такое поле у категории уже есть")

        if found:
            attr_id = found["id"]
            conn.execute(
                "UPDATE attributes SET archived = 0, kind = ?, required = ? WHERE id = ?",
                (body.kind, int(body.required), attr_id),
            )
        else:
            order = _next_order(conn, "attributes", "category_id = ?", (body.category_id,))
            attr_id = conn.execute(
                """
                INSERT INTO attributes (category_id, name, kind, required, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (body.category_id, name, body.kind, int(body.required), order),
            ).lastrowid

        _merge_options(conn, attr_id, body.options)
        conn.commit()
        return {"id": attr_id}


def _merge_options(conn, attr_id: int, values: list[str]) -> None:
    existing = {
        _key(r["value"])
        for r in conn.execute(
            "SELECT value FROM attribute_options WHERE attribute_id = ?", (attr_id,)
        )
    }
    order = _next_order(conn, "attribute_options", "attribute_id = ?", (attr_id,))
    for raw in values:
        value = _norm(raw)
        if not value or _key(value) in existing:
            continue
        existing.add(_key(value))
        conn.execute(
            "INSERT INTO attribute_options (attribute_id, value, sort_order) VALUES (?, ?, ?)",
            (attr_id, value, order),
        )
        order += 1


@router.patch("/attributes/{attr_id}")
def update_attribute(attr_id: int, body: AttributePatch, user: dict = Depends(get_current_user)):
    name = _norm(body.name)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT category_id FROM attributes WHERE id = ?", (attr_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Поле не найдено")
        found = _find_by_name(conn, "attributes", name, "category_id = ?", (row["category_id"],))
        if found and found["id"] != attr_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Поле с таким названием уже есть")
        conn.execute(
            "UPDATE attributes SET name = ?, required = ? WHERE id = ?",
            (name, int(body.required), attr_id),
        )
        conn.commit()
    return {"ok": True}


@router.post("/attributes/{attr_id}/options")
def add_option(attr_id: int, body: OptionIn, user: dict = Depends(get_current_user)):
    """Добавление варианта на лету из формы товара: «такой надписи ещё не было»."""
    value = _norm(body.value)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM attributes WHERE id = ?", (attr_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Поле не найдено")
        for row in conn.execute(
            "SELECT id, value FROM attribute_options WHERE attribute_id = ?", (attr_id,)
        ):
            if _key(row["value"]) == _key(value):
                return {"id": row["id"], "value": row["value"], "existed": True}
        order = _next_order(conn, "attribute_options", "attribute_id = ?", (attr_id,))
        cur = conn.execute(
            "INSERT INTO attribute_options (attribute_id, value, sort_order) VALUES (?, ?, ?)",
            (attr_id, value, order),
        )
        conn.commit()
        return {"id": cur.lastrowid, "value": value}


@router.delete("/attributes/{attr_id}/options/{option_id}")
def delete_option(attr_id: int, option_id: int, user: dict = Depends(get_current_user)):
    """Вариант — только подсказка для ввода. У товаров значение хранится текстом,
    поэтому удаление варианта не портит уже заведённые карточки и статистику."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM attribute_options WHERE id = ? AND attribute_id = ?",
            (option_id, attr_id),
        )
        conn.commit()
    return {"ok": True}


# ==== Удаление с архивированием и восстановление ====

# Чем занята запись: если на неё уже ссылаются, вместо удаления архивируем,
# иначе история и статистика потеряли бы часть данных.
_USAGE_SQL = {
    "categories": "SELECT COUNT(*) AS c FROM products WHERE category_id = ?",
    "subcategories": "SELECT COUNT(*) AS c FROM products WHERE subcategory_id = ?",
    "suppliers": "SELECT COUNT(*) AS c FROM products WHERE supplier_id = ?",
    "attributes": "SELECT COUNT(*) AS c FROM product_attributes WHERE attribute_id = ?",
}


def _remove(table: str, row_id: int) -> dict:
    label = ARCHIVABLE[table]
    with get_conn() as conn:
        if conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Не найдено: {label}")
        used = conn.execute(_USAGE_SQL[table], (row_id,)).fetchone()["c"]
        if used:
            conn.execute(f"UPDATE {table} SET archived = 1 WHERE id = ?", (row_id,))
            conn.commit()
            return {"archived": True, "used_by": used}
        try:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
            conn.commit()
        except sqlite3.IntegrityError:
            # Ссылка из таблицы, которую мы не проверяли явно — архивируем.
            conn.execute(f"UPDATE {table} SET archived = 1 WHERE id = ?", (row_id,))
            conn.commit()
            return {"archived": True}
    return {"deleted": True}


@router.delete("/categories/{row_id}")
def delete_category(row_id: int, user: dict = Depends(get_current_user)):
    return _remove("categories", row_id)


@router.delete("/subcategories/{row_id}")
def delete_subcategory(row_id: int, user: dict = Depends(get_current_user)):
    return _remove("subcategories", row_id)


@router.delete("/suppliers/{row_id}")
def delete_supplier(row_id: int, user: dict = Depends(get_current_user)):
    return _remove("suppliers", row_id)


@router.delete("/attributes/{row_id}")
def delete_attribute(row_id: int, user: dict = Depends(get_current_user)):
    return _remove("attributes", row_id)


@router.post("/{table}/{row_id}/restore")
def restore(table: str, row_id: int, user: dict = Depends(get_current_user)):
    """Архивирование не должно быть ловушкой без выхода: из архива всё возвращается."""
    if table not in ARCHIVABLE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Неизвестный справочник")
    with get_conn() as conn:
        changed = conn.execute(
            f"UPDATE {table} SET archived = 0 WHERE id = ?", (row_id,)
        ).rowcount
        conn.commit()
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Не найдено: {ARCHIVABLE[table]}")
    return {"ok": True}

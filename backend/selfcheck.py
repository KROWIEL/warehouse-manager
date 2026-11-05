"""Самопроверка логики склада на голых assert, без фреймворков и фикстур.

Запуск:  python selfcheck.py
Работает на временной базе, реальные данные не трогает.
Проверяет то, что сломается молча: политику пароля, арифметику остатка по всем
видам движений, границы периодов и сходимость статистики.
"""

import os
import shutil
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="store-selfcheck-")

# Настройки читаются один раз при импорте app.config, поэтому окружение
# подменяем до любых импортов приложения.
os.environ["DATA_DIR"] = _TMP
os.environ["DEAD_STOCK_DAYS"] = "60"
os.environ["SEED_USER1_USERNAME"] = "seller"
os.environ["SEED_USER1_NAME"] = "Продавец"
os.environ["SEED_USER1_PASSWORD"] = "seed-one-time-1"
os.environ["SEED_USER2_USERNAME"] = "boss"
os.environ["SEED_USER2_NAME"] = "Директор"
os.environ["SEED_USER2_PASSWORD"] = "seed-one-time-2"

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import HTTPException  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app import schemas  # noqa: E402
from app.db import get_conn, init_db  # noqa: E402
from app.export_xlsx import build_workbook  # noqa: E402
from app.periods import (  # noqa: E402
    MAX_DATE,
    MIN_DATE,
    bucket_key,
    choose_granularity,
    next_bucket,
    resolve_period,
    shift_months,
)
from app.routers import catalog, products, sales, stats  # noqa: E402
from app.security import (  # noqa: E402
    get_current_user,
    hash_password,
    make_salt,
    password_problem,
    verify_password,
)
from app.seed import run_seed  # noqa: E402

USER = {"id": 1, "must_change_password": 0}
TODAY = date.today()


def section(name: str) -> None:
    print(f"[ok] {name}")


def raises(fn, *, code: int = 400, contains: str | None = None) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == code, f"ждали {code}, получили {exc.status_code}: {exc.detail}"
        if contains:
            assert contains.lower() in str(exc.detail).lower(), exc.detail
        return
    raise AssertionError("ждали HTTPException, но вызов прошёл успешно")


def stock(product_id: int) -> float:
    with get_conn() as conn:
        return products.stock_of(conn, product_id)


def count(table: str) -> int:
    with get_conn() as conn:
        return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


# ============================================================
def check_passwords() -> None:
    assert password_problem("Abc!2345") is None
    assert password_problem("Пароль!1") is None, "кириллица тоже должна проходить"
    assert password_problem("Abc!234") is not None, "7 символов должны отклоняться"
    assert password_problem("abc!2345") is not None, "нет заглавной"
    assert password_problem("ABC!2345") is not None, "нет строчной"
    assert password_problem("Abcd2345") is not None, "нет спецсимвола"
    assert password_problem("Abcd 2345") is not None, "пробел не спецсимвол"

    salt = make_salt()
    digest = hash_password("Abc!2345", salt)
    assert verify_password("Abc!2345", salt, digest)
    assert not verify_password("Abc!2346", salt, digest)
    assert hash_password("Abc!2345", make_salt()) != digest, "соль должна менять хеш"
    section("политика пароля и хеширование")


def check_seed() -> None:
    init_db()
    run_seed()
    assert count("users") == 2, "должно создаться столько аккаунтов, сколько задано в env"

    with get_conn() as conn:
        rows = conn.execute("SELECT username, must_change_password FROM users ORDER BY id").fetchall()
    assert [r["username"] for r in rows] == ["seller", "boss"]
    assert all(r["must_change_password"] == 1 for r in rows), "стартовый пароль обязан меняться"

    # Смена пароля не должна откатываться повторным посевом.
    salt = make_salt()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0 WHERE id = 1",
            (hash_password("Ново!Пароль1", salt), salt),
        )
        conn.commit()

    run_seed()
    assert count("users") == 2, "повторный посев не должен создавать дубли"
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    assert verify_password("Ново!Пароль1", row["salt"], row["password_hash"]), "пароль сбросился"
    assert row["must_change_password"] == 0, "флаг смены пароля вернулся"

    raises(lambda: get_current_user({"must_change_password": 1}), code=403)
    assert get_current_user(USER) is USER
    section("посев аккаунтов идемпотентен, доступ закрыт до смены пароля")


def check_periods() -> None:
    start, end, label = resolve_period("3m")
    assert end == TODAY.isoformat()
    assert start == shift_months(TODAY, -3).isoformat()
    assert "3 месяца" in label

    assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28), "день должен прижиматься"
    assert shift_months(date(2026, 1, 15), -1) == date(2025, 12, 15), "переход через год"

    assert resolve_period("all")[:2] == (MIN_DATE, MAX_DATE)

    start, end, _ = resolve_period("custom", "2026-01-05", "2026-01-01")
    assert (start, end) == ("2026-01-01", "2026-01-05"), "перевёрнутый диапазон должен выправляться"

    for bad in (lambda: resolve_period("nope"), lambda: resolve_period("custom", "2026-01-01", None)):
        try:
            bad()
            raise AssertionError("ждали ValueError")
        except ValueError:
            pass

    assert choose_granularity("2026-08-01", "2026-08-20") == "day"
    assert choose_granularity("2026-01-01", "2026-04-01") == "week"
    assert choose_granularity("2024-01-01", "2026-01-01") == "month"

    assert bucket_key("2026-08-08", "month") == "2026-08"
    assert bucket_key("2026-08-08", "week") == "2026-08-03", "неделя начинается с понедельника"
    assert next_bucket("2026-12", "month") == "2027-01", "переход года в графике"
    assert next_bucket("2026-08-03", "week") == "2026-08-10"
    section("границы периодов и шкала графика")


def build_catalog() -> dict:
    clothes = catalog.create_category(
        schemas.CategoryIn(name="Одежда", color="#6366f1", icon="shirt"), USER
    )["id"]
    souvenirs = catalog.create_category(
        schemas.CategoryIn(name="Сувенирка", color="#f59e0b", icon="gift"), USER
    )["id"]

    print_attr = catalog.create_attribute(
        schemas.AttributeIn(
            category_id=clothes, name="Надпись", kind="select", options=["Rick and Morty", "Nirvana"]
        ),
        USER,
    )["id"]
    size_attr = catalog.create_attribute(
        schemas.AttributeIn(
            category_id=clothes, name="Размер", kind="select", required=True, options=["M", "L"]
        ),
        USER,
    )["id"]

    tees = catalog.create_subcategory(
        schemas.SubcategoryIn(category_id=clothes, name="Майки"), USER
    )
    # Создание на лету должно возвращать существующую запись, а не падать и не дублировать.
    again = catalog.create_subcategory(
        schemas.SubcategoryIn(category_id=clothes, name="  майки "), USER
    )
    assert again["id"] == tees["id"] and again.get("existed"), "подкатегория продублировалась"

    supplier = catalog.create_supplier(schemas.SupplierIn(name="Поставщик А"), USER)["id"]
    other_supplier = catalog.create_supplier(schemas.SupplierIn(name="Поставщик Б"), USER)["id"]
    raises(lambda: catalog.create_supplier(schemas.SupplierIn(name="поставщик а"), USER))

    option = catalog.add_option(print_attr, schemas.OptionIn(value="Nirvana"), USER)
    assert option.get("existed"), "вариант продублировался"
    assert count("attribute_options") == 4

    section("справочники: категории, поля с вариантами, подкатегории, поставщики")
    return {
        "clothes": clothes,
        "souvenirs": souvenirs,
        "print": print_attr,
        "size": size_attr,
        "tees": tees["id"],
        "supplier": supplier,
        "other_supplier": other_supplier,
    }


def check_products(cat: dict) -> dict:
    base = dict(
        category_id=cat["clothes"],
        subcategory_id=cat["tees"],
        supplier_id=cat["supplier"],
        price=10,
    )

    raises(
        lambda: products.create_product(
            schemas.ProductIn(name="Майка без размера", **base), USER
        ),
        contains="обязательно",
    )
    raises(
        lambda: products.create_product(
            schemas.ProductIn(
                name="Чужое поле", **base, attributes={cat["print"]: "Rick and Morty", 999: "x"}
            ),
            USER,
        ),
        code=400,
    )
    raises(
        lambda: products.create_product(
            schemas.ProductIn(
                name="Не та подкатегория",
                category_id=cat["souvenirs"],
                subcategory_id=cat["tees"],
                supplier_id=cat["supplier"],
                price=5,
            ),
            USER,
        ),
        contains="другой категории",
    )

    tee = products.create_product(
        schemas.ProductIn(
            name="Майка Rick and Morty",
            **base,
            barcode="4810123456789",
            min_stock=3,
            initial_qty=10,
            attributes={cat["print"]: "Rick and Morty", cat["size"]: "L"},
        ),
        USER,
    )["id"]
    mug = products.create_product(
        schemas.ProductIn(
            name="Кружка",
            category_id=cat["souvenirs"],
            supplier_id=cat["other_supplier"],
            price=20,
            initial_qty=5,
            note="Ёлочная, для елки",
        ),
        USER,
    )["id"]

    raises(
        lambda: products.create_product(
            schemas.ProductIn(
                name="Дубль кода",
                category_id=cat["souvenirs"],
                supplier_id=cat["supplier"],
                price=1,
                barcode="4810123456789",
            ),
            USER,
        ),
        contains="штрихкод",
    )

    assert stock(tee) == 10, "первичный приход не попал на склад"
    assert stock(mug) == 5

    found = products.product_by_barcode("4810123456789", USER)
    assert found["id"] == tee and found["stock"] == 10
    raises(lambda: products.product_by_barcode("нет-такого", USER), code=404)

    def search_ids(text: str) -> list[int]:
        rows = products.list_products(
            USER, search=text, category_id=None, subcategory_id=None, supplier_id=None,
            attribute_id=None, attribute_value=None, stock=None, archived=False,
            limit=50, offset=0,
        )
        return [p["id"] for p in rows]

    assert search_ids("rick") == [tee], "поиск по названию не сработал"
    # Родной LIKE в SQLite не складывает регистр кириллицы, поэтому запрос
    # в любом регистре должен находить товар — иначе поиск «работает не на всё».
    assert search_ids("МАЙ") == [tee], "кириллица ищется с учётом регистра"
    assert search_ids("кружка") == [mug], "кириллица ищется с учётом регистра"
    assert search_ids("MoRtY") == [tee], "кириллица сломала регистронезависимость латиницы"
    # Слова ищутся независимо: подряд «майка morty» в названии не встречается.
    assert search_ids("майка morty") == [tee], "поиск по нескольким словам не сработал"
    assert search_ids("майка кружка") == [], "слова должны складываться, а не заменять друг друга"
    # «ё» на телефонной клавиатуре под долгим нажатием, её набирают как «е»,
    # и наоборот — записать могли через «е», а искать через «ё».
    assert search_ids("елочная") == [mug], "«е» в запросе не находит «ё» в данных"
    assert search_ids("ЁЛКИ") == [mug], "«ё» в запросе не находит «е» в данных"

    by_value = products.list_products(
        USER, search="", category_id=None, subcategory_id=None, supplier_id=None,
        attribute_id=cat["print"], attribute_value="Rick and Morty", stock=None,
        archived=False, limit=50, offset=0,
    )
    assert [p["id"] for p in by_value] == [tee], "фильтр по значению поля не сработал"
    section("товары: обязательные поля, штрихкоды, поиск и фильтры")
    return {"tee": tee, "mug": mug}


def check_movements(ids: dict) -> None:
    tee = ids["tee"]

    products.add_movement(tee, schemas.MovementIn(kind="receipt", qty=5), USER)
    assert stock(tee) == 15

    products.add_movement(tee, schemas.MovementIn(kind="writeoff", qty=3, reason="Брак"), USER)
    assert stock(tee) == 12

    raises(
        lambda: products.add_movement(tee, schemas.MovementIn(kind="writeoff", qty=100), USER),
        contains="только",
    )
    raises(lambda: products.add_movement(tee, schemas.MovementIn(kind="receipt", qty=0), USER))
    raises(lambda: products.add_movement(tee, schemas.MovementIn(kind="sale", qty=1), USER))

    # Инвентаризация принимает фактический остаток, а не расхождение.
    result = products.add_movement(tee, schemas.MovementIn(kind="adjust", qty=10), USER)
    assert result["delta"] == -2 and stock(tee) == 10, result

    same = products.add_movement(tee, schemas.MovementIn(kind="adjust", qty=10), USER)
    assert same["delta"] == 0, "пересчёт без расхождения не должен создавать движение"

    raises(lambda: products.add_movement(tee, schemas.MovementIn(kind="adjust", qty=-1), USER))

    # Ошибочный приход можно отменить, продажу — нет.
    extra = products.add_movement(tee, schemas.MovementIn(kind="receipt", qty=7), USER)
    assert stock(tee) == 17
    with get_conn() as conn:
        movement_id = conn.execute(
            "SELECT id FROM stock_movements WHERE product_id = ? ORDER BY id DESC LIMIT 1", (tee,)
        ).fetchone()["id"]
    products.delete_movement(tee, movement_id, USER)
    assert stock(tee) == 10, extra
    section("движения склада: приход, списание, инвентаризация, отмена")


def check_sales(cat: dict, ids: dict) -> dict:
    tee, mug = ids["tee"], ids["mug"]

    raises(
        lambda: sales.create_sale(
            schemas.SaleIn(items=[schemas.SaleItemIn(product_id=tee, qty=999)]), USER
        ),
        contains="на складе",
    )
    # Одна позиция дважды в корзине — проверка склада должна смотреть на сумму.
    raises(
        lambda: sales.create_sale(
            schemas.SaleIn(
                items=[
                    schemas.SaleItemIn(product_id=tee, qty=6),
                    schemas.SaleItemIn(product_id=tee, qty=6),
                ]
            ),
            USER,
        ),
        contains="на складе",
    )
    raises(
        lambda: sales.create_sale(
            schemas.SaleIn(
                items=[schemas.SaleItemIn(product_id=tee, qty=1)], payment_method="bitcoin"
            ),
            USER,
        ),
        contains="оплаты",
    )
    raises(
        lambda: sales.create_sale(
            schemas.SaleIn(items=[schemas.SaleItemIn(product_id=tee, qty=1)], discount=1000), USER
        ),
        contains="скидка",
    )

    first = sales.create_sale(
        schemas.SaleIn(
            items=[
                schemas.SaleItemIn(product_id=tee, qty=2),
                schemas.SaleItemIn(product_id=mug, qty=1),
            ],
            discount=4,
            payment_method="cash",
            customer="Ирина",
        ),
        USER,
    )
    assert (first["gross"], first["total"]) == (40.0, 36.0), first
    assert stock(tee) == 8 and stock(mug) == 4

    second = sales.create_sale(
        schemas.SaleIn(
            items=[schemas.SaleItemIn(product_id=tee, qty=1)], payment_method="card"
        ),
        USER,
    )
    assert second["total"] == 10.0
    assert stock(tee) == 7

    # Торг: цена позиции переопределяется, цена в карточке не меняется.
    haggled = sales.create_sale(
        schemas.SaleIn(
            items=[schemas.SaleItemIn(product_id=mug, qty=1, unit_price=15)],
            payment_method="cash",
        ),
        USER,
    )
    assert haggled["total"] == 15.0, haggled
    sales.delete_sale(haggled["id"], USER)
    assert stock(mug) == 4, "отмена чека должна вернуть товар на склад"

    detail = sales.get_sale(first["id"], USER)
    tee_item = next(i for i in detail["items"] if i["product_id"] == tee)

    raises(
        lambda: sales.create_return(schemas.ReturnIn(sale_item_id=tee_item["id"], qty=5), USER),
        contains="не больше",
    )
    refund = sales.create_return(
        schemas.ReturnIn(sale_item_id=tee_item["id"], qty=1, reason="Не подошёл размер"), USER
    )
    # Покупатель заплатил за майку 10 * (36/40) = 9, столько и должно вернуться.
    assert refund["refund"] == 9.0, f"возврат не учёл скидку чека: {refund}"
    assert refund["left"] == 1.0, refund
    assert stock(tee) == 8, "возврат должен вернуть товар на склад"

    with get_conn() as conn:
        sale_movement = conn.execute(
            "SELECT id FROM stock_movements WHERE kind = 'sale' LIMIT 1"
        ).fetchone()["id"]
    raises(
        lambda: products.delete_movement(tee, sale_movement, USER),
        contains="через чек",
    )

    listed = sales.list_sales(USER, date_from=None, date_to=None, limit=50, offset=0)
    assert len(listed) == 2 and listed[0]["items"], listed
    section("продажи: чек, торг, скидка, отмена, возврат")
    return {"first": first["id"], "second": second["id"]}


def check_stats(cat: dict, ids: dict) -> None:
    start, end, label = resolve_period("month")
    data = stats.build_stats(start, end, label, "month", attribute_id=cat["print"])
    totals = data["totals"]

    # Чек 1: 2x10 + 1x20 = 40, скидка 4 -> 36. Чек 2: 1x10 = 10. Итого 46.
    # Возврат 1 майки из чека 1: 10 * (36/40) = 9. Выручка 46 - 9 = 37.
    assert totals["gross"] == 50.0, totals
    assert totals["discount"] == 4.0, totals
    assert totals["receipts"] == 2, totals
    assert totals["avg_receipt"] == 23.0, totals
    assert totals["returns_units"] == 1.0 and totals["returns_amount"] == 9.0, totals
    assert totals["revenue"] == 37.0, totals
    assert totals["units"] == 3.0, totals
    assert totals["writeoff_units"] == 3.0 and totals["writeoff_amount"] == 30.0, totals
    assert totals["stock_units"] == 12.0, totals          # 8 маек + 4 кружки
    assert totals["stock_value"] == 160.0, totals         # 8*10 + 4*20

    def money(rows: list[dict]) -> dict:
        return {r["name"]: r["revenue"] for r in rows}

    # Скидка чека разносится по позициям пропорционально: майки 28-9=19, кружка 18.
    assert money(data["by_category"]) == {"Одежда": 19.0, "Сувенирка": 18.0}, data["by_category"]
    assert money(data["by_supplier"]) == {"Поставщик А": 19.0, "Поставщик Б": 18.0}
    assert money(data["by_payment"]) == {"Наличные": 27.0, "Карта": 10.0}
    assert money(data["by_user"]) == {"Продавец": 37.0}
    assert money(data["top_products"]) == {"Майка Rick and Morty": 19.0, "Кружка": 18.0}
    assert money(data["by_subcategory"]) == {"Майки": 19.0, "Без подкатегории": 18.0}

    values = money(data["by_attribute"]["values"])
    assert values == {"Rick and Morty": 19.0, "Не указано": 18.0}, values

    percents = sum(r["percent"] for r in data["by_category"])
    assert abs(percents - 100) < 0.2, percents

    points = data["series"]["points"]
    assert sum(p["revenue"] for p in points) == 37.0, points
    assert sum(p["receipts"] for p in points) == 2, points

    low_names = [r["name"] for r in data["stock"]["low"]]
    assert low_names == [], f"порог 3 при остатке 8 не должен срабатывать: {low_names}"

    # Пустой период не должен падать и обязан давать нули.
    long_ago = (TODAY - timedelta(days=400)).isoformat()
    empty = stats.build_stats(long_ago, (TODAY - timedelta(days=390)).isoformat(), "тест", "custom")
    assert empty["totals"]["revenue"] == 0.0 and empty["series"]["points"] == []
    assert empty["totals"]["stock_value"] == 160.0, "остаток склада не зависит от периода"
    section("статистика: итоги, все разрезы и разнесение скидки сходятся")
    return data


def check_low_and_dead(ids: dict, cat: dict) -> None:
    tee = ids["tee"]
    products.add_movement(tee, schemas.MovementIn(kind="writeoff", qty=6, reason="Витрина"), USER)
    assert stock(tee) == 2

    start, end, label = resolve_period("month")
    data = stats.build_stats(start, end, label, "month")
    low = {r["name"]: r["stock"] for r in data["stock"]["low"]}
    assert low == {"Майка Rick and Morty": 2.0}, low

    # Кружка на складе есть, но её продажу оформим задним числом за пределами окна.
    old = (TODAY - timedelta(days=120)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE stock_movements SET occurred_at = ? WHERE product_id = ? AND kind = 'sale'",
            (old, ids["mug"]),
        )
        conn.commit()
    dead = {r["name"] for r in stats.build_stats(start, end, label, "month")["stock"]["dead"]}
    assert "Кружка" in dead, dead
    section("низкие остатки и мёртвый сток")


def check_export(cat: dict, ids: dict) -> None:
    start, end, label = resolve_period("year")
    data = stats.build_stats(start, end, label, "year", attribute_id=cat["print"])
    blob = build_workbook(data).getvalue()
    assert blob[:2] == b"PK", "xlsx должен быть zip-контейнером"
    assert len(blob) > 5000, f"файл подозрительно мал: {len(blob)} байт"

    wb = load_workbook(BytesIO(blob))
    expected = {
        "Сводка", "Товары", "По поставщикам", "По категориям", "По подкатегориям",
        "По полям товара", "Топ товаров", "Хуже всего продаётся", "По продавцам",
        "По оплате", "Динамика", "Чеки", "Движения склада", "Пора дозаказать",
        "Мёртвый сток",
    }
    assert expected <= set(wb.sheetnames), f"нет листов: {expected - set(wb.sheetnames)}"

    def table(title: str) -> list[dict]:
        ws = wb[title]
        head = [c.value for c in ws[1]]
        return [dict(zip(head, [c.value for c in row])) for row in ws.iter_rows(min_row=2)]

    # Каждая позиция расписана отдельной строкой: и что продано, и что на складе.
    goods = table("Товары")
    assert {r["Товар"] for r in goods} == {"Майка Rick and Morty", "Кружка"}, goods
    tee = next(r for r in goods if r["Товар"].startswith("Майка"))
    assert tee["Остаток, шт"] == stock(ids["tee"]), tee
    assert tee["Поставщик"] and tee["Категория"] == "Одежда", tee
    assert "Rick and Morty" in tee["Параметры"], "значения полей товара не попали в файл"

    totals = data["totals"]
    assert abs(sum(r["Выручка"] for r in goods) - totals["revenue"]) < 0.01, (
        "выручка по товарам не сходится с итогом"
    )
    sold = sum(r["Продано, шт"] for r in goods) - sum(r["Возвращено, шт"] for r in goods)
    assert abs(sold - totals["units"]) < 0.001, "штуки по товарам не сходятся с итогом"
    assert abs(sum(r["Остаток, сумма"] for r in goods) - totals["stock_value"]) < 0.01

    # Разрез по поставщикам должен нести и остатки, а не только продажи.
    suppliers = table("По поставщикам")
    assert abs(sum(r["Выручка"] for r in suppliers) - totals["revenue"]) < 0.01, suppliers
    assert abs(sum(r["Остаток, сумма"] for r in suppliers) - totals["stock_value"]) < 0.01
    assert sum(r["Товаров"] for r in suppliers) == len(goods), suppliers

    fields = table("По полям товара")
    assert ("Одежда", "Надпись", "Rick and Morty") in {
        (r["Категория"], r["Поле"], r["Значение"]) for r in fields
    }, fields
    # Размер тоже настроен, хотя на экране выбрано другое поле: в файле все.
    assert "Размер" in {r["Поле"] for r in fields}, fields

    movements = table("Движения склада")
    assert {"Приход", "Продажа", "Возврат"} <= {r["Операция"] for r in movements}, movements

    with zipfile.ZipFile(BytesIO(blob)) as zf:
        charts = [n for n in zf.namelist() if n.startswith("xl/charts/chart")]
    assert len(charts) >= 4, f"графики не нарисовались: {charts}"
    section("экспорт статистики в xlsx: все листы, суммы сходятся, графики есть")


def check_archiving(cat: dict, ids: dict) -> None:
    # На поставщике висят товары — удаление обязано превратиться в архивирование.
    result = catalog.delete_supplier(cat["supplier"], USER)
    assert result.get("archived"), result
    catalog.restore("suppliers", cat["supplier"], USER)

    # Проданный товар нельзя удалить бесследно.
    result = products.delete_product(ids["tee"], USER)
    assert result.get("archived"), result
    products.restore_product(ids["tee"], USER)

    empty_category = catalog.create_category(schemas.CategoryIn(name="Пустая"), USER)["id"]
    assert catalog.delete_category(empty_category, USER).get("deleted"), "пустое удаляется совсем"

    visible = catalog.get_catalog(include_archived=False, user=USER)
    assert [c["name"] for c in visible["categories"]] == ["Одежда", "Сувенирка"]
    assert visible["categories"][0]["product_count"] == 1
    assert len(visible["categories"][0]["attributes"]) == 2
    section("удаление превращается в архив, из архива всё возвращается")


def main() -> int:
    try:
        check_passwords()
        check_seed()
        check_periods()
        cat = build_catalog()
        ids = check_products(cat)
        check_movements(ids)
        check_sales(cat, ids)
        check_stats(cat, ids)
        check_low_and_dead(ids, cat)
        check_export(cat, ids)
        check_archiving(cat, ids)
    except AssertionError as exc:
        print(f"\nПРОВАЛ: {exc}")
        return 1
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print("\nВсе проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import settings

# Остаток товара нигде не хранится колонкой — это всегда SUM(stock_movements.qty).
# Одна таблица движений даёт и текущий остаток, и историю, и разрезы статистики,
# и её невозможно рассинхронизировать с самой собой.
# ponytail: на десятках тысяч движений агрегат станет заметен — лечится
# кешированной колонкой products.stock, обновляемой в той же транзакции.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT NOT NULL UNIQUE,
    display_name         TEXT NOT NULL,
    password_hash        TEXT NOT NULL,
    salt                 TEXT NOT NULL,
    avatar               TEXT NOT NULL DEFAULT 'fox',
    theme                TEXT NOT NULL DEFAULT 'light',
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT '#6366f1',
    icon       TEXT NOT NULL DEFAULT 'package',
    sort_order INTEGER NOT NULL DEFAULT 0,
    archived   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subcategories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    note       TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    archived   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Набор полей товара настраивается для каждой категории отдельно:
-- у одежды это размер/цвет/надпись, у канцелярии — что-то своё.
CREATE TABLE IF NOT EXISTS attributes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'select',  -- select | text
    required    INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS attribute_options (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    attribute_id INTEGER NOT NULL REFERENCES attributes(id) ON DELETE CASCADE,
    value        TEXT NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (attribute_id, value)
);

CREATE TABLE IF NOT EXISTS products (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    price          REAL NOT NULL DEFAULT 0,
    barcode        TEXT,
    min_stock      REAL NOT NULL DEFAULT 0,
    note           TEXT NOT NULL DEFAULT '',
    archived       INTEGER NOT NULL DEFAULT 0,
    created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_attributes (
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute_id INTEGER NOT NULL REFERENCES attributes(id) ON DELETE CASCADE,
    value        TEXT NOT NULL,
    PRIMARY KEY (product_id, attribute_id)
);

CREATE TABLE IF NOT EXISTS sales (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at    TEXT NOT NULL,              -- YYYY-MM-DD
    discount       REAL NOT NULL DEFAULT 0,    -- всегда абсолютная сумма в BYN
    payment_method TEXT NOT NULL DEFAULT 'cash',
    customer       TEXT NOT NULL DEFAULT '',
    total          REAL NOT NULL DEFAULT 0,    -- сумма позиций минус скидка
    note           TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sale_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id    INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    qty        REAL NOT NULL,
    unit_price REAL NOT NULL,   -- снимок цены: торг и будущие переоценки не искажают историю
    subtotal   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    kind         TEXT NOT NULL,  -- receipt | sale | return | writeoff | adjust
    qty          REAL NOT NULL,  -- со знаком: приход/возврат/корректировка +, продажа/списание -
    sale_id      INTEGER REFERENCES sales(id) ON DELETE CASCADE,
    -- Возврат ссылается на конкретную позицию чека: только так видно,
    -- сколько из неё уже вернули, и по какой цене считать уменьшение выручки.
    sale_item_id INTEGER REFERENCES sale_items(id) ON DELETE CASCADE,
    reason       TEXT NOT NULL DEFAULT '',
    occurred_at  TEXT NOT NULL,  -- YYYY-MM-DD
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mov_product  ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_mov_occurred ON stock_movements(occurred_at);
CREATE INDEX IF NOT EXISTS idx_mov_kind     ON stock_movements(kind);
CREATE INDEX IF NOT EXISTS idx_mov_item     ON stock_movements(sale_item_id);
CREATE INDEX IF NOT EXISTS idx_items_sale    ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_items_product ON sale_items(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_occurred ON sales(occurred_at);
CREATE INDEX IF NOT EXISTS idx_prod_barcode  ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_prod_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_pattr_attr    ON product_attributes(attribute_id);
"""


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def fold(value):
    """Приводит текст к виду для поиска. Две вещи, без которых поиск «работает
    не на всё»:
    - родной lower() в SQLite складывает регистр только для латиницы, для
      'Майка' он возвращает 'Майка' — питоновский lower знает Unicode;
    - 'ё' на телефонной клавиатуре спрятана под долгим нажатием, поэтому её
      набирают через 'е': 'черная' должно находить 'ЧЁРНАЯ'.
    Используется и как SQL-функция, и для слов запроса — чтобы обе стороны
    сравнения нормализовались одинаково."""
    return value.lower().replace("ё", "е") if isinstance(value, str) else value


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Соединение на операцию. Закрытие без commit откатывает транзакцию,
    поэтому многошаговые записи (чек + позиции + движения) атомарны сами по себе."""
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.create_function("fold", 1, fold, deterministic=True)
    try:
        yield conn
    finally:
        conn.close()

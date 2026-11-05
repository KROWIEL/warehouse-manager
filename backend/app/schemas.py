from datetime import date

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    avatar: str | None = None
    theme: str | None = None


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = "#6366f1"
    icon: str = "package"


class SubcategoryIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=40)


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    note: str = ""


class AttributeIn(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=40)
    kind: str = "select"
    required: bool = False
    options: list[str] = []


class AttributePatch(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    required: bool = False


class OptionIn(BaseModel):
    value: str = Field(min_length=1, max_length=60)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category_id: int
    subcategory_id: int | None = None
    supplier_id: int
    price: float = Field(default=0, ge=0)
    barcode: str | None = None
    min_stock: float = Field(default=0, ge=0)
    note: str = ""
    # Ключи приходят из JSON строками, Pydantic сам приводит их к id атрибута.
    attributes: dict[int, str] = {}
    # Стартовый приход: заводить товар и сразу класть его на склад — одно действие.
    initial_qty: float = Field(default=0, ge=0)


class MovementIn(BaseModel):
    kind: str  # receipt | writeoff | adjust
    # Для receipt и writeoff — количество (всегда положительное, знак ставит бэкенд).
    # Для adjust — фактический остаток по пересчёту, расхождение считается сервером.
    qty: float
    reason: str = ""
    occurred_at: date | None = None


class SaleItemIn(BaseModel):
    product_id: int
    qty: float = Field(gt=0)
    # None — берём цену из карточки товара; число — торг для этой продажи.
    unit_price: float | None = Field(default=None, ge=0)


class SaleIn(BaseModel):
    items: list[SaleItemIn] = Field(min_length=1)
    discount: float = Field(default=0, ge=0)
    payment_method: str = "cash"
    customer: str = ""
    note: str = ""
    occurred_at: date | None = None


class ReturnIn(BaseModel):
    sale_item_id: int
    qty: float = Field(gt=0)
    reason: str = ""
    occurred_at: date | None = None

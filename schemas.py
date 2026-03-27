from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from models import OrderStatus


# ─── Product Schemas ──────────────────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str = Field(..., max_length=200, examples=["無線藍牙耳機"])
    description: Optional[str] = Field(None, examples=["高音質降噪耳機"])
    price: Decimal = Field(..., gt=0, examples=[1299.00])
    category: Optional[str] = Field(None, max_length=100, examples=["3C 電子"])


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0)
    category: Optional[str] = Field(None, max_length=100)


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ─── Inventory Schemas ────────────────────────────────────────────────────────

class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    updated_at: datetime


class InventoryUpdate(BaseModel):
    quantity: int = Field(..., ge=0, examples=[50])


class InventoryAdjust(BaseModel):
    delta: int = Field(..., examples=[10], description="正數為入庫，負數為出庫")


# ─── Order Schemas ────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: int = Field(..., examples=[1])
    quantity: int = Field(..., gt=0, examples=[2])


class OrderCreate(BaseModel):
    customer_name: str = Field(..., max_length=100, examples=["王小明"])
    customer_email: EmailStr = Field(..., examples=["wang@example.com"])
    shipping_address: str = Field(..., examples=["台北市信義區信義路五段7號"])
    items: List[OrderItemCreate] = Field(..., min_length=1)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_name: str
    customer_email: str
    shipping_address: str
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemOut]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderQueuedOut(BaseModel):
    message_id: str
    status: str
    detail: str

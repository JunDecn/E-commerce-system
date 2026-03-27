from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Product, Inventory
from schemas import ProductCreate, ProductOut, ProductUpdate
from services.redis_service import set_stock

router = APIRouter(prefix="/products", tags=["商品"])


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    """新增商品，並自動初始化庫存為 0"""
    product = Product(**payload.model_dump())
    db.add(product)
    await db.flush()  # 取得 product.id

    inventory = Inventory(product_id=product.id, quantity=0)
    db.add(inventory)
    await db.commit()
    await db.refresh(product)
    await set_stock(product.id, 0)
    return product


@router.get("/", response_model=list[ProductOut])
async def list_products(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """列出所有商品（支援分頁）"""
    stmt = select(Product).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """取得單一商品資訊"""
    stmt = select(Product).where(Product.id == product_id)
    product = await db.scalar(stmt)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, payload: ProductUpdate, db: AsyncSession = Depends(get_db)):
    """更新商品資訊（部分更新）"""
    stmt = select(Product).where(Product.id == product_id)
    product = await db.scalar(stmt)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """刪除商品"""
    stmt = select(Product).where(Product.id == product_id)
    product = await db.scalar(stmt)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    await db.delete(product)
    await db.commit()

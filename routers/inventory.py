from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Inventory, Product
from schemas import InventoryOut, InventoryUpdate, InventoryAdjust
from services.redis_service import set_stock

router = APIRouter(prefix="/inventory", tags=["庫存"])


async def _get_inventory_or_404(product_id: int, db: AsyncSession) -> Inventory:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    inv = await db.scalar(select(Inventory).where(Inventory.product_id == product_id))
    if not inv:
        raise HTTPException(status_code=404, detail="庫存紀錄不存在")
    return inv


@router.get("/", response_model=list[InventoryOut])
async def list_inventory(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """列出所有商品庫存"""
    stmt = select(Inventory).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{product_id}", response_model=InventoryOut)
async def get_inventory(product_id: int, db: AsyncSession = Depends(get_db)):
    """查詢特定商品庫存"""
    return await _get_inventory_or_404(product_id, db)


@router.put("/{product_id}", response_model=InventoryOut)
async def set_inventory(product_id: int, payload: InventoryUpdate, db: AsyncSession = Depends(get_db)):
    """直接設定庫存數量"""
    inv = await _get_inventory_or_404(product_id, db)
    inv.quantity = payload.quantity
    await db.commit()
    await db.refresh(inv)
    await set_stock(product_id, inv.quantity)
    return inv


@router.patch("/{product_id}/adjust", response_model=InventoryOut)
async def adjust_inventory(product_id: int, payload: InventoryAdjust, db: AsyncSession = Depends(get_db)):
    """調整庫存數量（delta 正數入庫，負數出庫）"""
    inv = await _get_inventory_or_404(product_id, db)
    new_qty = inv.quantity + payload.delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"庫存不足，目前庫存 {inv.quantity}")
    inv.quantity = new_qty
    await db.commit()
    await db.refresh(inv)
    await set_stock(product_id, inv.quantity)
    return inv

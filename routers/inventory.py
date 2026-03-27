from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Inventory, Product
from schemas import InventoryOut, InventoryUpdate, InventoryAdjust

router = APIRouter(prefix="/inventory", tags=["庫存"])


def _get_inventory_or_404(product_id: int, db: Session) -> Inventory:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="庫存紀錄不存在")
    return inv


@router.get("/", response_model=list[InventoryOut])
def list_inventory(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """列出所有商品庫存"""
    return db.query(Inventory).offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=InventoryOut)
def get_inventory(product_id: int, db: Session = Depends(get_db)):
    """查詢特定商品庫存"""
    return _get_inventory_or_404(product_id, db)


@router.put("/{product_id}", response_model=InventoryOut)
def set_inventory(product_id: int, payload: InventoryUpdate, db: Session = Depends(get_db)):
    """直接設定庫存數量"""
    inv = _get_inventory_or_404(product_id, db)
    inv.quantity = payload.quantity
    db.commit()
    db.refresh(inv)
    return inv


@router.patch("/{product_id}/adjust", response_model=InventoryOut)
def adjust_inventory(product_id: int, payload: InventoryAdjust, db: Session = Depends(get_db)):
    """調整庫存數量（delta 正數入庫，負數出庫）"""
    inv = _get_inventory_or_404(product_id, db)
    new_qty = inv.quantity + payload.delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"庫存不足，目前庫存 {inv.quantity}")
    inv.quantity = new_qty
    db.commit()
    db.refresh(inv)
    return inv

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Order, OrderItem, Product, Inventory, OrderStatus
from schemas import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["訂單"])


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    """
    建立訂單：
    - 驗證商品存在
    - 確認庫存充足
    - 扣除庫存
    - 計算總金額
    """
    order = Order(
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        shipping_address=payload.shipping_address,
        status=OrderStatus.pending,
        total_amount=Decimal("0"),
    )
    db.add(order)
    db.flush()

    total = Decimal("0")
    for item_in in payload.items:
        product = db.query(Product).filter(Product.id == item_in.product_id).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"商品 ID {item_in.product_id} 不存在",
            )

        inv = (
            db.query(Inventory)
            .filter(Inventory.product_id == item_in.product_id)
            .with_for_update()
            .first()
        )
        if not inv or inv.quantity < item_in.quantity:
            available = inv.quantity if inv else 0
            raise HTTPException(
                status_code=400,
                detail=f"商品「{product.name}」庫存不足，目前庫存 {available}",
            )

        inv.quantity -= item_in.quantity
        unit_price = Decimal(str(product.price))
        total += unit_price * item_in.quantity

        order_item = OrderItem(
            order_id=order.id,
            product_id=item_in.product_id,
            quantity=item_in.quantity,
            unit_price=unit_price,
        )
        db.add(order_item)

    order.total_amount = total
    db.commit()
    db.refresh(order)
    return order


@router.get("/", response_model=list[OrderOut])
def list_orders(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    """列出所有訂單（支援分頁）"""
    return db.query(Order).offset(skip).limit(limit).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """查詢單筆訂單詳情"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(order_id: int, payload: OrderStatusUpdate, db: Session = Depends(get_db)):
    """更新訂單狀態（pending → confirmed → shipped / cancelled）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")

    # 已取消的訂單不可再更新
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=400, detail="已取消的訂單不可再變更狀態")

    # 若從 pending/confirmed 取消，歸還庫存
    if payload.status == OrderStatus.cancelled and order.status != OrderStatus.cancelled:
        for item in order.items:
            inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
            if inv:
                inv.quantity += item.quantity

    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    """刪除訂單（僅限 pending 狀態）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="僅限 pending 狀態的訂單可刪除")

    # 歸還庫存
    for item in order.items:
        inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if inv:
            inv.quantity += item.quantity

    db.delete(order)
    db.commit()

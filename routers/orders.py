from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Order, Inventory, OrderStatus
from schemas import OrderCreate, OrderOut, OrderQueuedOut, OrderStatusUpdate
from services.rabbitmq_service import publish_order_message
from services.redis_service import reserve_stock_with_lua, restore_stock

router = APIRouter(prefix="/orders", tags=["訂單"])


@router.post("/", response_model=OrderQueuedOut, status_code=status.HTTP_202_ACCEPTED)
async def create_order(payload: OrderCreate):
    """
    建立訂單（非同步）：
    - 以 Redis Lua script 原子檢查並預扣庫存
    - 庫存足夠則送出 RabbitMQ 訊息
    - 由 worker 非同步建立訂單並扣減 DB 庫存
    """
    payload_dict = payload.model_dump()
    ok, detail = await reserve_stock_with_lua(payload_dict["items"])
    if not ok:
        raise HTTPException(status_code=400, detail=detail)

    message_id = str(uuid4())
    message_payload = {
        "message_id": message_id,
        "customer_name": payload_dict["customer_name"],
        "customer_email": payload_dict["customer_email"],
        "shipping_address": payload_dict["shipping_address"],
        "items": payload_dict["items"],
    }

    try:
        await publish_order_message(message_payload, message_id=message_id)
    except Exception:
        await restore_stock(payload_dict["items"])
        raise HTTPException(status_code=503, detail="訂單佇列服務暫時不可用，請稍後再試")

    return OrderQueuedOut(
        message_id=message_id,
        status="queued",
        detail="庫存預扣成功，訂單已送入處理佇列",
    )


@router.get("/", response_model=list[OrderOut])
async def list_orders(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    """列出所有訂單（支援分頁）"""
    stmt = select(Order).options(selectinload(Order.items)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """查詢單筆訂單詳情"""
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    order = await db.scalar(stmt)
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(order_id: int, payload: OrderStatusUpdate, db: AsyncSession = Depends(get_db)):
    """更新訂單狀態（pending → confirmed → shipped / cancelled）"""
    order = await db.scalar(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")

    # 已取消的訂單不可再更新
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=400, detail="已取消的訂單不可再變更狀態")

    # 若從 pending/confirmed 取消，歸還庫存
    if payload.status == OrderStatus.cancelled and order.status != OrderStatus.cancelled:
        for item in order.items:
            inv = await db.scalar(select(Inventory).where(Inventory.product_id == item.product_id))
            if inv:
                inv.quantity += item.quantity

    order.status = payload.status
    order_id = order.id
    await db.commit()
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    return await db.scalar(stmt)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: int, db: AsyncSession = Depends(get_db)):
    """刪除訂單（僅限 pending 狀態）"""
    order = await db.scalar(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )
    if not order:
        raise HTTPException(status_code=404, detail="訂單不存在")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="僅限 pending 狀態的訂單可刪除")

    # 歸還庫存
    for item in order.items:
        inv = await db.scalar(select(Inventory).where(Inventory.product_id == item.product_id))
        if inv:
            inv.quantity += item.quantity

    await db.delete(order)
    await db.commit()

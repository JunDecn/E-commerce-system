import asyncio
import json
from decimal import Decimal
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import Inventory, Order, OrderItem, OrderStatus, Product
from schemas import OrderCreate
from services.rabbitmq_service import get_queue, init_rabbitmq
from services.redis_service import init_redis, restore_stock


async def deduct_inventory_with_optimistic_lock(
    db, product_id: int, quantity: int, max_retries: int = 3
) -> None:
    """
    用樂觀鎖扣減庫存，避免race condition
    
    Args:
        db: 資料庫連線
        product_id: 商品ID
        quantity: 要扣減的數量
        max_retries: 最大重試次數
    
    Raises:
        ValueError: 庫存不足或商品不存在
    """
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise ValueError(f"商品 ID {product_id} 不存在")
    
    for attempt in range(max_retries):
        # 讀取當前庫存和版本號
        inv = await db.scalar(
            select(Inventory).where(Inventory.product_id == product_id)
        )
        
        if not inv or inv.quantity < quantity:
            available = inv.quantity if inv else 0
            raise ValueError(
                f"商品「{product.name}」庫存不足，目前庫存 {available}"
            )
        
        current_version = inv.version
        current_quantity = inv.quantity
        
        # 使用樂觀鎖更新：只有版本號匹配才會成功
        result = await db.execute(
            update(Inventory)
            .where(
                (Inventory.product_id == product_id)
                & (Inventory.version == current_version)
            )
            .values(
                quantity=current_quantity - quantity,
                version=current_version + 1
            )
        )
        
        if result.rowcount > 0:
            # 更新成功
            return
        
        # 版本號不匹配，等待後重試
        if attempt < max_retries - 1:
            # 指數退避：第一次等待100ms，第二次200ms
            await asyncio.sleep(0.1 * (attempt + 1))
    
    # 重試多次仍然失敗
    raise ValueError(
        f"商品 ID {product_id} 庫存扣減失敗，請稍後重試（版本衝突）"
    )


async def create_order_from_message(payload: dict) -> None:
    order_in = OrderCreate(
        customer_name=payload["customer_name"],
        customer_email=payload["customer_email"],
        shipping_address=payload["shipping_address"],
        items=payload["items"],
    )
    async with SessionLocal() as db:
        try:
            order_id = payload.get("order_id")
            created_at_str = payload.get("created_at")
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                except Exception:
                    created_at = None

            order = Order(
                order_id=order_id,
                customer_name=order_in.customer_name,
                customer_email=order_in.customer_email,
                shipping_address=order_in.shipping_address,
                status=OrderStatus.pending,
                total_amount=Decimal("0"),
            )

            # if API provided created_at, persist it
            if created_at is not None:
                order.created_at = created_at

            db.add(order)
            await db.flush()

            total = Decimal("0")
            sorted_items = sorted(order_in.items, key=lambda item: item.product_id)

            for item_in in sorted_items:
                # 使用樂觀鎖扣減庫存
                await deduct_inventory_with_optimistic_lock(
                    db, item_in.product_id, item_in.quantity
                )
                
                # 取得商品資訊以計算總金額
                product = await db.scalar(select(Product).where(Product.id == item_in.product_id))
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
            await db.commit()
        except IntegrityError:
            # Duplicate order_id -> already processed, treat as success (ack)
            await db.rollback()
            return
        except Exception:
            await db.rollback()
            await restore_stock(payload["items"])
            raise


async def handle_messages() -> None:
    await init_redis()
    await init_rabbitmq()
    queue = get_queue()

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=False):
                payload = json.loads(message.body.decode("utf-8"))
                try:
                    await create_order_from_message(payload)
                except Exception as exc:
                    print(f"[worker] 建立訂單失敗: {exc}")


if __name__ == "__main__":
    asyncio.run(handle_messages())

import asyncio
import json
from decimal import Decimal
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import Inventory, Order, OrderItem, OrderStatus, Product
from schemas import OrderCreate
from services.rabbitmq_service import get_queue, init_rabbitmq
from services.redis_service import init_redis, restore_stock


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
                product = await db.scalar(select(Product).where(Product.id == item_in.product_id))
                if not product:
                    raise ValueError(f"商品 ID {item_in.product_id} 不存在")

                inv = await db.scalar(
                    select(Inventory)
                    .where(Inventory.product_id == item_in.product_id)
                    .with_for_update()
                )

                if not inv or inv.quantity < item_in.quantity:
                    available = inv.quantity if inv else 0
                    raise ValueError(
                        f"商品「{product.name}」庫存不足，目前庫存 {available}"
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

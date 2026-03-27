from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import select

from database import engine, Base, SessionLocal
from models import Inventory
from routers import products, inventory, orders
from services.rabbitmq_service import close_rabbitmq, init_rabbitmq
from services.redis_service import close_redis, init_redis, set_stock


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時自動建立資料表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_redis()
    await init_rabbitmq()

    # 啟動時將現有 DB 庫存同步至 Redis，避免快取 key 遺失。
    async with SessionLocal() as db:
        result = await db.execute(select(Inventory.product_id, Inventory.quantity))
        for product_id, quantity in result.all():
            await set_stock(product_id, quantity)

    yield
    await close_rabbitmq()
    await close_redis()


app = FastAPI(
    title="電商訂單系統",
    description="提供商品管理、庫存管理、訂單下單等功能的單體式後端服務。",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(orders.router)


@app.get("/", tags=["健康檢查"])
async def root():
    return {"message": "電商訂單系統正常運作中", "docs": "/docs"}


@app.get("/health", tags=["健康檢查"])
async def health():
    return {"status": "ok"}

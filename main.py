from fastapi import FastAPI
from contextlib import asynccontextmanager

from database import engine, Base
from routers import products, inventory, orders


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時自動建立資料表
    Base.metadata.create_all(bind=engine)
    yield


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
def root():
    return {"message": "電商訂單系統正常運作中", "docs": "/docs"}


@app.get("/health", tags=["健康檢查"])
def health():
    return {"status": "ok"}

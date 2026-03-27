import os
from collections import defaultdict

from redis.asyncio import Redis


_stock_redis: Redis | None = None

CHECK_AND_DEDUCT_LUA = """
for i = 1, #KEYS do
    local stock = tonumber(redis.call('GET', KEYS[i]) or '-1')
    local qty = tonumber(ARGV[i])
    if stock < qty then
        return {0, i, stock}
    end
end

for i = 1, #KEYS do
    redis.call('DECRBY', KEYS[i], tonumber(ARGV[i]))
end

return {1}
"""


def get_stock_key(product_id: int) -> str:
    return f"stock:product:{product_id}"


def _normalize_items(items: list[dict]) -> list[tuple[int, int]]:
    grouped: dict[int, int] = defaultdict(int)
    for item in items:
        grouped[int(item["product_id"])] += int(item["quantity"])
    return sorted(grouped.items(), key=lambda pair: pair[0])


async def init_redis() -> None:
    global _stock_redis
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    _stock_redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    await _stock_redis.ping()


async def close_redis() -> None:
    global _stock_redis
    if _stock_redis is not None:
        await _stock_redis.aclose()
    _stock_redis = None


def _get_redis() -> Redis:
    if _stock_redis is None:
        raise RuntimeError("Redis 尚未初始化")
    return _stock_redis


async def set_stock(product_id: int, quantity: int) -> None:
    redis = _get_redis()
    await redis.set(get_stock_key(product_id), int(quantity))


async def reserve_stock_with_lua(items: list[dict]) -> tuple[bool, str]:
    if not items:
        return False, "訂單項目不得為空"

    redis = _get_redis()
    normalized = _normalize_items(items)
    keys = [get_stock_key(product_id) for product_id, _ in normalized]
    quantities = [str(quantity) for _, quantity in normalized]

    result = await redis.eval(CHECK_AND_DEDUCT_LUA, len(keys), *keys, *quantities)
    if not isinstance(result, list) or not result:
        return False, "Redis 庫存檢查回傳格式異常"

    success = int(result[0]) == 1
    if success:
        return True, "ok"

    failed_idx = int(result[1]) - 1
    failed_product_id = normalized[failed_idx][0]
    current_stock = int(result[2])
    if current_stock < 0:
        current_stock = 0
    return False, f"商品 ID {failed_product_id} 庫存不足，目前庫存 {current_stock}"


async def restore_stock(items: list[dict]) -> None:
    redis = _get_redis()
    normalized = _normalize_items(items)
    pipeline = redis.pipeline(transaction=True)
    for product_id, quantity in normalized:
        pipeline.incrby(get_stock_key(product_id), int(quantity))
    await pipeline.execute()

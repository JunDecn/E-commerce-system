
# 訂單系統架構

## 概述

本專案實作一個簡易的電子商務訂單系統，包含以下主要服務：

- `db`：PostgreSQL（`postgres:16-alpine`）作為永久儲存。
- `api`：以 FastAPI 提供商品、庫存與訂單 API（下單改為佇列化）。
- `redis`：儲存商品庫存快取，並在下單時用 Lua script 進行原子檢查與預扣。
- `rabbitmq`：作為訂單建立訊息佇列。
- `worker`：RabbitMQ consumer，負責建立訂單與扣減 DB 庫存。
- `k6`：使用 Grafana k6 容器執行負載測試（測試腳本位於 `tests/k6`）。

服務由 `docker-compose.yml` 定義。`k6` 服務被設定在一個 profile（預設不會隨 `docker compose up -d` 啟動），需要額外指定才能啟動。

## 組件說明

- 資料庫：PostgreSQL，使用 `postgres_data` volume 儲存資料。
- API：FastAPI 應用（參考 `main.py`、`routers/`、`models.py`、`schemas.py`）。
- 快取：Redis（`stock:product:{product_id}`）。
- 訊息：RabbitMQ queue（預設 `order.create`）。
- 消費者：`workers/order_consumer.py`。
- 負載測試：`tests/k6/order_flow_test.js`，由 `k6` 容器執行。

## 啟動方式

- 啟動核心服務（DB、Redis、RabbitMQ、API、worker）：

```bash
docker compose up -d --build db redis rabbitmq api worker
```

- 啟動 k6 負載測試（profile 名稱為 `loadtest`）：

```bash
docker compose --profile loadtest up -d --build k6
```

或是在已啟動的 API 上手動執行 k6：

```bash
docker compose run --rm k6
```

## 效能紀錄

- 測試結果：執行 10,000 筆訂單請求，總耗時 **10 秒**。

  - 測試腳本：`tests/k6/order_flow_test.js`
  - 環境：透過 Docker Compose 的 `k6` 服務對 `api` 服務進行測試。

## 併發與資料一致性

- `create_order` API 不再直接寫入訂單。

- API 流程：
  1. 呼叫 Redis Lua script 原子檢查庫存並預扣。
  2. 若成功，送出 RabbitMQ 訊息（`order.create`）。
  3. 回應 `202 Accepted`（`queued`）。

- worker 流程：
  1. 消費 RabbitMQ 訊息。
  2. 建立訂單並扣減 PostgreSQL 庫存（含 row-level lock）。
  3. 若失敗，回補 Redis 預扣庫存。

- 此架構將高併發入口壓力轉移到 Redis + MQ，降低 API 同步等待 DB 鎖的時間。

## 相關檔案

- [docker-compose.yml](docker-compose.yml)
- [services/redis_service.py](services/redis_service.py)
- [services/rabbitmq_service.py](services/rabbitmq_service.py)
- [tests/k6/order_flow_test.js](tests/k6/order_flow_test.js)
- [routers/orders.py](routers/orders.py)
- [workers/order_consumer.py](workers/order_consumer.py)

---

產生日期：2026-03-27

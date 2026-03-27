
# 訂單系統架構

## 概述

本專案實作一個簡易的電子商務訂單系統，包含以下主要服務：

- `db`：PostgreSQL（`postgres:16-alpine`）作為永久儲存。
- `api`：以 FastAPI 提供商品、庫存與訂單等 API。
- `k6`：使用 Grafana k6 容器執行負載測試（測試腳本位於 `tests/k6`）。

服務由 `docker-compose.yml` 定義。`k6` 服務被設定在一個 profile（預設不會隨 `docker compose up -d` 啟動），需要額外指定才能啟動。

## 組件說明

- 資料庫：PostgreSQL，使用 `postgres_data` volume 儲存資料。
- API：FastAPI 應用（參考 `main.py`、`routers/`、`models.py`、`schemas.py`）。
- 負載測試：`tests/k6/order_flow_test.js`，由 `k6` 容器執行。

## 啟動方式

- 啟動資料庫與 API：

```bash
docker compose up -d --build
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

- 測試結果：執行 10,000 筆訂單請求，總耗時 **62 秒**。

  - 測試腳本：`tests/k6/order_flow_test.js`
  - 環境：透過 Docker Compose 的 `k6` 服務對 `api` 服務進行測試。

## 併發與資料一致性

- `create_order` 流程會檢查庫存並扣減。目前實作使用了資料列鎖（`SELECT ... FOR UPDATE` / SQLAlchemy 的 `.with_for_update()`）以避免 lost-update 現象。

- 在高併發場景下，建議採用原子性的 `UPDATE ... WHERE quantity >= n RETURNING` 或樂觀鎖搭配重試的策略，以降低死鎖風險並提升效能。

## 相關檔案

- [docker-compose.yml](docker-compose.yml)
- [tests/k6/order_flow_test.js](tests/k6/order_flow_test.js)
- [routers/orders.py](routers/orders.py)

---

產生日期：2026-03-27

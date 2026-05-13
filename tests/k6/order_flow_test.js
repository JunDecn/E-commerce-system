import http from 'k6/http';
import { check, fail, sleep } from 'k6';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// 測試規模設定
// 50 商品 × 200 庫存 = 10,000 件
// 5000 訂單 × 2 商品/訂單 = 10,000 件，剛好賣完
const PRODUCT_COUNT = 50;
const INVENTORY_PER_PRODUCT = 200;
const ORDER_COUNT = 5000;
const ITEMS_PER_ORDER = 2;
// 將 50 個商品分成 25 組，每組 2 個；每組被訂購 80 次 → 各商品恰好售完
const GROUP_COUNT = PRODUCT_COUNT / ITEMS_PER_ORDER; // 25

export const options = {
  scenarios: {
    order_flow: {
      executor: 'shared-iterations',
      vus: 10,
      iterations: ORDER_COUNT,
      maxDuration: '5m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export function setup() {
  const productIds = [];

  for (let i = 0; i < PRODUCT_COUNT; i++) {
    // 建立商品
    const createProductRes = http.post(
      `${BASE_URL}/products/`,
      JSON.stringify({
        name: `k6-product-${Date.now()}-${i}`,
        description: `k6 load test product ${i}`,
        price: 100,
        category: 'k6-test',
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );

    const productOk = check(createProductRes, {
      [`create product[${i}] status is 201`]: (r) => r.status === 201,
      [`create product[${i}] has id`]: (r) => {
        const body = r.json();
        return body && body.id;
      },
    });

    if (!productOk) {
      fail(`Create product[${i}] failed: status=${createProductRes.status}, body=${createProductRes.body}`);
    }

    const productId = createProductRes.json('id');
    productIds.push(productId);

    // 設定庫存
    const setInventoryRes = http.put(
      `${BASE_URL}/inventory/${productId}`,
      JSON.stringify({ quantity: INVENTORY_PER_PRODUCT }),
      { headers: { 'Content-Type': 'application/json' } }
    );

    const inventoryOk = check(setInventoryRes, {
      [`set inventory[${i}] status is 200`]: (r) => r.status === 200,
      [`inventory[${i}] is ${INVENTORY_PER_PRODUCT}`]: (r) => r.json('quantity') === INVENTORY_PER_PRODUCT,
    });

    if (!inventoryOk) {
      fail(`Set inventory[${i}] failed: status=${setInventoryRes.status}, body=${setInventoryRes.body}`);
    }
  }

  return { productIds };
}

export default function (data) {
  const { productIds } = data;

  // 使用 scenario 全域迭代序號做精準分配，避免 __ITER（每個 VU 本地計數）偏差
  const globalIteration = exec.scenario.iterationInTest;
  const groupIndex = globalIteration % GROUP_COUNT;
  const items = [];
  for (let i = 0; i < ITEMS_PER_ORDER; i++) {
    items.push({
      product_id: productIds[groupIndex * ITEMS_PER_ORDER + i],
      quantity: 1,
    });
  }

  const orderRes = http.post(
    `${BASE_URL}/orders/`,
    JSON.stringify({
      customer_name: `k6-user-${__VU}-${globalIteration}`,
      customer_email: `k6-user-${__VU}-${globalIteration}@example.com`,
      shipping_address: 'Taipei City Test Address 1',
      items,
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  const ok = check(orderRes, {
    'create order status is 202': (r) => r.status === 202,
    'create order queued': (r) => r.json('status') === 'queued',
  });

  if (!ok) {
    console.error(`Create order failed: status=${orderRes.status}, body=${orderRes.body}`);
  }
}

export function teardown(data) {
  // 等待 worker 消化完所有訊息
  sleep(10);

  const { productIds } = data;

  // 驗證每個商品庫存應為 0（全部售完）
  productIds.forEach((productId, i) => {
    const invRes = http.get(`${BASE_URL}/inventory/${productId}`);
    check(invRes, {
      [`product[${i}] inventory endpoint returns 200`]: (r) => r.status === 200,
      [`product[${i}] is sold out (quantity=0)`]: (r) => r.json('quantity') === 0,
    });
  });
}

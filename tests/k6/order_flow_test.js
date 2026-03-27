import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  scenarios: {
    order_101_times: {
      executor: 'shared-iterations',
      vus: 10,
      iterations: 10000,
      maxDuration: '2m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export function setup() {
  const productPayload = JSON.stringify({
    name: `k6-test-product-${Date.now()}`,
    description: 'k6 load test product',
    price: 100,
    category: 'k6-test',
  });

  const createProductRes = http.post(`${BASE_URL}/products/`, productPayload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const productOk = check(createProductRes, {
    'create product status is 201': (r) => r.status === 201,
    'create product has id': (r) => {
      const body = r.json();
      return body && body.id;
    },
  });

  if (!productOk) {
    fail(`Create product failed: status=${createProductRes.status}, body=${createProductRes.body}`);
  }

  const productId = createProductRes.json('id');

  const setInventoryRes = http.put(
    `${BASE_URL}/inventory/${productId}`,
    JSON.stringify({ quantity: 10000 }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  const inventoryOk = check(setInventoryRes, {
    'set inventory status is 200': (r) => r.status === 200,
    'inventory is 10000': (r) => r.json('quantity') === 10000,
  });

  if (!inventoryOk) {
    fail(`Set inventory failed: status=${setInventoryRes.status}, body=${setInventoryRes.body}`);
  }

  return { productId };
}

export default function (data) {
  const orderPayload = JSON.stringify({
    customer_name: `k6-user-${__VU}-${__ITER}`,
    customer_email: `k6-user-${__VU}-${__ITER}@example.com`,
    shipping_address: 'Taipei City Test Address 1',
    items: [
      {
        product_id: data.productId,
        quantity: 1,
      },
    ],
  });

  const orderRes = http.post(`${BASE_URL}/orders/`, orderPayload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const ok = check(orderRes, {
    'create order status is 202': (r) => r.status === 202,
    'create order queued': (r) => r.json('status') === 'queued',
  });

  if (!ok) {
    console.error(`Create order failed: status=${orderRes.status}, body=${orderRes.body}`);
  }

  // sleep(0.05);
}

export function teardown(data) {
  sleep(3);
  const invRes = http.get(`${BASE_URL}/inventory/${data.productId}`);
  check(invRes, {
    'inventory endpoint should return 200': (r) => r.status === 200,
  });
}

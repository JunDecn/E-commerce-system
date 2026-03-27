import json
import os

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue


_connection: AbstractConnection | None = None
_channel: AbstractChannel | None = None
_queue: AbstractQueue | None = None


def get_queue_name() -> str:
    return os.getenv("ORDER_QUEUE_NAME", "order.create")


async def init_rabbitmq() -> None:
    global _connection, _channel, _queue
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    _connection = await aio_pika.connect_robust(rabbitmq_url)
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=10)
    _queue = await _channel.declare_queue(get_queue_name(), durable=True)


async def close_rabbitmq() -> None:
    global _connection, _channel, _queue
    if _channel is not None:
        await _channel.close()
    if _connection is not None:
        await _connection.close()
    _queue = None
    _channel = None
    _connection = None


async def publish_order_message(payload: dict, message_id: str) -> None:
    if _channel is None:
        raise RuntimeError("RabbitMQ channel 尚未初始化")

    message = Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        message_id=message_id,
    )
    await _channel.default_exchange.publish(message, routing_key=get_queue_name())


def get_queue() -> AbstractQueue:
    if _queue is None:
        raise RuntimeError("RabbitMQ queue 尚未初始化")
    return _queue

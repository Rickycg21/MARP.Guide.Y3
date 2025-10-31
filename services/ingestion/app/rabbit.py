import json, pika, os

EXCHANGE = os.getenv("EVENT_EXCHANGE", "events")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

def _channel():
    params = pika.URLParameters(RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    return conn, ch

def publish_event(routing_key: str, payload: dict):
    conn, ch = _channel()
    try:
        ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2  # persistent
            ),
        )
    finally:
        ch.close()
        conn.close()

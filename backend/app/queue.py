from redis import Redis
from rq import Queue

from app.config import get_settings


settings = get_settings()
QUEUE_NAME = "rag-ingestion"


def get_queue() -> Queue:
    redis_conn = Redis.from_url(settings.redis_url)
    return Queue(QUEUE_NAME, connection=redis_conn)


def enqueue_ingestion(document_id: str):
    queue = get_queue()
    return queue.enqueue("app.worker.ingest_document", document_id, job_timeout=1800)

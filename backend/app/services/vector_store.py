from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import get_settings
from app.services.embeddings import VECTOR_SIZE

# Tên riêng để phân biệt model và phiên bản dữ liệu.
COLLECTION_NAME = "enterprise_e5_small_v1"


@lru_cache(maxsize=1)
def get_vector_client() -> QdrantClient:
    settings = get_settings()

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )


def ensure_collection() -> QdrantClient:
    client = get_vector_client()

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )

    info = client.get_collection(COLLECTION_NAME)
    config = info.config.params.vectors

    if (
        not isinstance(config, VectorParams)
        or config.size != VECTOR_SIZE
        or config.distance != Distance.COSINE
    ):
        raise ValueError("Collection có cấu hình vector không phù hợp")

    return client
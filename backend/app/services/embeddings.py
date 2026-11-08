from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-small"
VECTOR_SIZE = 384


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )


def encode_texts(texts: list[str], prefix: str) -> list[list[float]]:
    if not texts:
        return []

    if any(not text.strip() for text in texts):
        raise ValueError("Không tạo embedding cho văn bản rỗng")

    model = get_embedding_model()
    inputs = [f"{prefix}{text}" for text in texts]

    # Không âm thầm cắt mất phần cuối của văn bản quá dài.
    for item in inputs:
        tokens = model.tokenizer(
            item,
            truncation=False,
        )["input_ids"]

        if len(tokens) > model.max_seq_length:
            raise ValueError(
                "Văn bản vượt giới hạn token của model. "
                "Cần chia thành đoạn nhỏ hơn."
            )

    vectors = model.encode(
        inputs,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )

    if vectors.shape[1] != VECTOR_SIZE:
        raise ValueError("Số chiều vector không đúng cấu hình")

    return vectors.tolist()


def embed_passages(texts: list[str]) -> list[list[float]]:
    return encode_texts(texts, prefix="passage: ")


def embed_query(question: str) -> list[float]:
    return encode_texts(
        [question],
        prefix="query: ",
    )[0]
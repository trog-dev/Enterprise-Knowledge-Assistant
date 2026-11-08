from pathlib import Path


def read_txt(file_path: Path) -> str:
    # utf-8-sig đọc được cả UTF-8 thông thường và UTF-8 có BOM.
    text = file_path.read_text(encoding="utf-8-sig")

    # Chuẩn hóa xuống dòng trước khi xác định vị trí các đoạn.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text.strip():
        raise ValueError("Tài liệu không có nội dung văn bản")

    if "\x00" in text:
        raise ValueError("File chứa ký tự không hợp lệ cho văn bản TXT")

    return text


def split_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size phải lớn hơn 0")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap phải từ 0 đến nhỏ hơn chunk_size")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        content = text[start:end]

        if content.strip():
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "content": content,
                    "start_char": start,
                    "end_char": end,
                }
            )

        if end == len(text):
            break

        start = end - overlap

    return chunks
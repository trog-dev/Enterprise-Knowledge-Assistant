import logging
from pathlib import Path
from threading import Lock

import pymupdf
import pytesseract
from PIL import Image
from docx import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.config import get_settings
from app.services.embeddings import get_embedding_model
from app.services.text_processing import read_txt

logger = logging.getLogger(__name__)

# Các request đọc PDF dùng chung khóa để không gọi MuPDF đồng thời.
PDF_LOCK = Lock()

# Giới hạn ban đầu cho xử lý đồng bộ trong request.
MAX_PDF_PAGES = 30


def read_pdf(
    path: Path,
    force_ocr: bool,
) -> tuple[list[dict], list[str]]:
    settings = get_settings()
    units = []
    warnings = []

    with PDF_LOCK:
        with pymupdf.open(str(path)) as document:
            if document.needs_pass:
                raise ValueError(
                    "PDF có mật khẩu. Hãy dùng bản PDF đã mở khóa."
                )

            if len(document) > MAX_PDF_PAGES:
                raise ValueError(
                    f"Bản hiện tại chỉ xử lý tối đa "
                    f"{MAX_PDF_PAGES} trang PDF mỗi file."
                )

            for page_index in range(len(document)):
                page = document[page_index]
                page_number = page_index + 1

                text = page.get_text("text", sort=True)
                compact_text = "".join(text.split())

                # Đây là heuristic, không phải bộ nhận diện scan tuyệt đối.
                needs_ocr = (
                    force_ocr
                    or not compact_text
                    or (
                        len(compact_text) < 40
                        and bool(page.get_images())
                    )
                )

                method = "pdf_text"

                if needs_ocr:
                    if not Path(settings.tesseract_cmd).is_file():
                        raise ValueError(
                            "Cần OCR nhưng chưa tìm thấy Tesseract. "
                            "Kiểm tra TESSERACT_CMD trong .env."
                        )

                    pytesseract.pytesseract.tesseract_cmd = (
                        settings.tesseract_cmd
                    )

                    # Khoảng 200 DPI, giới hạn cạnh dài để tránh ảnh quá lớn.
                    longest_side = max(
                        page.rect.width,
                        page.rect.height,
                    )

                    scale = min(
                        200 / 72,
                        6000 / max(longest_side, 1),
                    )

                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(scale, scale),
                        colorspace=pymupdf.csRGB,
                        alpha=False,
                    )

                    with Image.frombytes(
                        "RGB",
                        (pixmap.width, pixmap.height),
                        pixmap.samples,
                    ) as image:
                        try:
                            text = pytesseract.image_to_string(
                                image,
                                lang=settings.ocr_languages,
                                timeout=60,
                            )
                        except pytesseract.TesseractError:
                            raise ValueError(
                                f"OCR trang {page_number} thất bại. "
                                "Kiểm tra Tesseract và ngôn ngữ vie, eng."
                            ) from None
                        except RuntimeError:
                            raise ValueError(
                                f"OCR trang {page_number} "
                                "vượt quá thời gian chờ."
                            ) from None

                    method = "ocr"

                if not text.strip():
                    warnings.append(
                        f"Trang {page_number}: không đọc được văn bản."
                    )
                    continue

                units.append(
                    {
                        "text": text,
                        "page_number": page_number,
                        "source_location": f"Trang {page_number}",
                        "extracted_with": method,
                    }
                )

    return units, warnings


def read_docx(path: Path) -> tuple[list[dict], list[str]]:
    document = WordDocument(str(path))
    units = []

    paragraph_number = 0
    table_number = 0

    # Đọc đoạn và bảng theo thứ tự trong phần thân tài liệu.
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            paragraph_number += 1
            text = block.text
            location = f"Đoạn {paragraph_number}"

        elif isinstance(block, Table):
            table_number += 1

            text = "\n".join(
                " | ".join(cell.text for cell in row.cells)
                for row in block.rows
            )

            location = f"Bảng {table_number}"

        else:
            continue

        if text.strip():
            units.append(
                {
                    "text": text,
                    "page_number": None,
                    "source_location": location,
                    "extracted_with": "docx",
                }
            )

    warnings = [
        "Word: đang đọc phần thân, đoạn văn và bảng cấp ngoài; "
        "chưa đọc chữ trong ảnh, textbox, header/footer và bảng lồng."
    ]

    return units, warnings


def extract_document(
    path: Path,
    force_ocr: bool = False,
) -> tuple[list[dict], list[str]]:
    extension = path.suffix.lower()

    try:
        if extension == ".txt":
            units = [
                {
                    "text": read_txt(path),
                    "page_number": None,
                    "source_location": "Văn bản TXT",
                    "extracted_with": "txt",
                }
            ]
            warnings = []

        elif extension == ".pdf":
            units, warnings = read_pdf(path, force_ocr)

        elif extension == ".docx":
            units, warnings = read_docx(path)

        else:
            raise ValueError(
                "Chỉ hỗ trợ TXT, PDF và DOCX. "
                "File .doc cần chuyển sang .docx."
            )

    except ValueError:
        raise

    except Exception:
        logger.exception("Document extraction failed")

        raise ValueError(
            "Không đọc được tài liệu. "
            "Kiểm tra định dạng, mã hóa hoặc xem log backend."
        ) from None

    if not units:
        raise ValueError(
            "Không tìm được văn bản có thể sử dụng trong tài liệu."
        )

    return units, warnings


def build_document_chunks(units: list[dict]) -> list[dict]:
    model = get_embedding_model()
    tokenizer = model.tokenizer

    # Chia theo token thay vì 1.000 ký tự để phù hợp model embeddings.
    prefix_tokens = len(
        tokenizer(
            "passage: ",
            add_special_tokens=False,
        )["input_ids"]
    )

    available = (
        model.max_seq_length
        - tokenizer.num_special_tokens_to_add(pair=False)
        - prefix_tokens
        - 8
    )

    chunk_size = min(320, available)

    if chunk_size <= 0:
        raise ValueError("Giới hạn token của model không phù hợp")

    overlap = min(50, chunk_size // 4)
    chunks = []

    for unit in units:
        text = (
            unit["text"]
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\x00", "")
        )

        encoded = tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
        )

        offsets = encoded["offset_mapping"]
        start = 0

        while start < len(offsets):
            end = min(start + chunk_size, len(offsets))

            start_char = offsets[start][0]
            end_char = offsets[end - 1][1]
            content = text[start_char:end_char]

            if content.strip():
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "content": content,
                        "start_char": start_char,
                        "end_char": end_char,
                        "page_number": unit["page_number"],
                        "source_location": unit["source_location"],
                        "extracted_with": unit["extracted_with"],
                    }
                )

            if end == len(offsets):
                break

            start = end - overlap

    if not chunks:
        raise ValueError("Không tạo được đoạn văn bản")

    return chunks
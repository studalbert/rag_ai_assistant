import io

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter

from app.services.text_extraction import TextExtractionError, extract_text


def test_extract_plain_text() -> None:
    content = b"Hello, this is a plain text document."

    result = extract_text(content, "text/plain")

    assert result == "Hello, this is a plain text document."


def test_extract_markdown() -> None:
    content = b"# Title\n\nSome **markdown** content."

    result = extract_text(content, "text/markdown")

    assert "Title" in result


def test_extract_empty_text_file_raises() -> None:
    with pytest.raises(TextExtractionError, match="empty"):
        extract_text(b"   ", "text/plain")


def test_extract_invalid_utf8_raises() -> None:
    invalid_bytes = b"\xff\xfe\x00\x01"

    with pytest.raises(TextExtractionError, match="UTF-8"):
        extract_text(invalid_bytes, "text/plain")


def test_extract_docx() -> None:
    buffer = io.BytesIO()
    doc = DocxDocument()
    doc.add_paragraph("This is a test paragraph in a Word document.")
    doc.save(buffer)

    result = extract_text(
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert "test paragraph" in result


def test_extract_empty_docx_raises() -> None:
    buffer = io.BytesIO()
    doc = DocxDocument()  # без добавленных параграфов
    doc.save(buffer)

    with pytest.raises(TextExtractionError, match="No extractable text"):
        extract_text(
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_extract_from_scanned_pdf_without_text_layer_raises() -> None:
    # PdfWriter без add_blank_page с текстом создаёт пустую страницу без текстового слоя —
    # имитирует скан без OCR
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    with pytest.raises(TextExtractionError, match="No extractable text"):
        extract_text(buffer.getvalue(), "application/pdf")


def test_extract_unsupported_content_type_raises() -> None:
    with pytest.raises(TextExtractionError, match="No text extractor"):
        extract_text(b"whatever", "application/json")

import io

from docx import Document as DocxDocument
from pypdf import PdfReader


class TextExtractionError(Exception):
    pass


def _extract_from_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise TextExtractionError(f"Could not open PDF: {exc}") from exc

    pages_text = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages_text).strip()

    if not text:
        # Частый случай: PDF — это скан (картинки страниц без текстового слоя).
        # OCR сюда не добавляем на этом этапе — явно сообщаем о проблеме,
        # а не молча возвращаем пустоту.
        raise TextExtractionError(
            "No extractable text found in PDF (it might be a scanned image without OCR)"
        )
    return text


def _extract_from_docx(content: bytes) -> str:
    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as exc:
        raise TextExtractionError(f"Could not open DOCX: {exc}") from exc

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs).strip()

    if not text:
        raise TextExtractionError("No extractable text found in DOCX")
    return text


def _extract_from_plain_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TextExtractionError(f"File is not valid UTF-8 text: {exc}") from exc

    if not text.strip():
        raise TextExtractionError("File is empty")
    return text


_EXTRACTORS = {
    "application/pdf": _extract_from_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _extract_from_docx,
    "text/plain": _extract_from_plain_text,
    "text/markdown": _extract_from_plain_text,
}


def extract_text(content: bytes, content_type: str) -> str:
    """Возвращает извлечённый текст или бросает TextExtractionError с понятной причиной."""
    extractor = _EXTRACTORS.get(content_type)
    if extractor is None:
        raise TextExtractionError(f"No text extractor available for content type {content_type}")
    return extractor(content)

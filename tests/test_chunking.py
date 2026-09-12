import pytest

from app.services.chunking import chunk_text


def test_short_text_returns_single_chunk() -> None:
    result = chunk_text("Hello world", chunk_size=1000, chunk_overlap=200)

    assert result == ["Hello world"]


def test_empty_text_returns_empty_list() -> None:
    assert chunk_text("   ", chunk_size=1000, chunk_overlap=200) == []
    assert chunk_text("", chunk_size=1000, chunk_overlap=200) == []


def test_long_text_is_split_into_multiple_chunks() -> None:
    text = "a" * 2500

    result = chunk_text(text, chunk_size=1000, chunk_overlap=200)

    assert len(result) > 1
    # каждый чанк, кроме последнего, не должен превышать заданный размер
    for chunk in result[:-1]:
        assert len(chunk) <= 1000


def test_chunks_actually_overlap() -> None:
    text = "0123456789" * 30  # 300 символов, легко проверить пересечение по содержимому

    result = chunk_text(text, chunk_size=100, chunk_overlap=20)

    # конец первого чанка должен совпадать с началом второго на величину overlap
    assert result[0][-20:] == result[1][:20]


def test_entire_text_is_covered_without_gaps() -> None:
    text = "".join(str(i % 10) for i in range(500))

    result = chunk_text(text, chunk_size=100, chunk_overlap=20)

    # склеиваем чанки обратно, убирая известное перекрытие, и сверяем с оригиналом
    reconstructed = result[0]
    for chunk in result[1:]:
        reconstructed += chunk[20:]

    assert reconstructed == text


def test_invalid_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("some text", chunk_size=0, chunk_overlap=0)


def test_overlap_greater_than_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_text("some text", chunk_size=100, chunk_overlap=100)

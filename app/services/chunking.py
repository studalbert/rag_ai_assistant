def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Режет текст на чанки фиксированного размера (в символах) с перекрытием.

    Перекрытие нужно, чтобы смысл не терялся на границе двух чанков — если важное
    предложение оказалось разрезано ровно пополам, кусок с перекрытием всё равно
    попадёт целиком хотя бы в один из соседних чанков.

    Специально простая реализация без учёта границ слов/предложений — по ТЗ
    "начать просто, без хитрой семантической сегментации". Если качество ретрива
    в RAG-пайплайне окажется недостаточным, можно будет заменить на более умный
    сплиттер (например, разбивку по абзацам/предложениям через spaCy/nltk),
    не трогая остальной пайплайн — эта функция изолирована и легко подменяется.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    step = chunk_size - chunk_overlap
    chunks: list[str] = []

    start = 0
    text_length = len(text)
    while start < text_length:
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)

        if start + chunk_size >= text_length:
            break
        start += step

    return chunks

from typing import Generator


def split_ngrams(text: str, min: int, max: int) -> Generator[str, None, None]:
    # This is gloriously inefficiently implemented.
    for offset in range(len(text) - min + 1):
        for ngram in range(min, max + 1):
            chunk = text[offset : offset + ngram]
            if len(chunk) == ngram:
                # print(offset, ngram, text, repr(chunk))
                yield chunk

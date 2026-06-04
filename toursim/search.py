import re


def normalize_search_text(text):
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()

def split_search_terms(text):
    normalized = normalize_search_text(text)
    if not normalized:
        return []

    terms = []
    for chunk in re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+", normalized):
        if re.fullmatch(r"[0-9a-zA-Z]+", chunk):
            terms.append(chunk)
            continue
        if len(chunk) <= 2:
            terms.append(chunk)
            continue
        terms.append(chunk)
        terms.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return list(dict.fromkeys(terms))

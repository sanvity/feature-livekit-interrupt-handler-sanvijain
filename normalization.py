from typing import List

# --------------------------------------------------------
# Normalization Mappings
# --------------------------------------------------------

# Maps common Hindi/Hinglish variations to a canonical form
HINDI_VARIANTS = {
    "haan": "haan",
    "han": "haan",
    "haanji": "haan",
    "haan ji": "haan",
    "haanji?": "haan",
    "accha": "accha",
    "acha": "accha",
    "achha": "accha",
    "theek": "thik",
    "thik": "thik",
}

# Maps common English filler variations to a canonical form
ENGLISH_VARIANTS = {
    "ok": "okay",
    "okk": "okay",
    "okayyy": "okay",
    "umm": "um",
    "ummm": "um",
    "uhh": "uh",
    "hmm ok": "hmm okay",
    "hmm okay": "hmm okay",
    "hmmkay": "hmm okay",
}

# Combined map for normalization
NORMALIZATION_MAP = {**HINDI_VARIANTS, **ENGLISH_VARIANTS}

# Punctuation to be stripped
STRIP_CHARS = " ,.!?;:-\"'()"


def normalize_speech_tokens(words: List[str]) -> List[str]:
    """
    Normalize a list of speech tokens:
    - Lowercase
    - Strip punctuation
    - Map variants to canonical form
    """

    # Use a list comprehension for a clean, fast transformation
    return [
        NORMALIZATION_MAP.get(cleaned_word, cleaned_word)
        for cleaned_word in (
            w.lower().strip(STRIP_CHARS) for w in words
        )
    ]
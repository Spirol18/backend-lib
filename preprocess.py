# ==============================
# Nepali Audiobook Preprocessing (Robust Version)
# ==============================

import re
import unicodedata
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract
from logger_config import get_logger

logger = get_logger("preprocess")

# ==============================
# PATH CONFIGURATION
# ==============================

BASE_DIR = Path("User_input")
OCR_DIR = BASE_DIR / "ocr_text"
CLEAN_DIR = BASE_DIR / "clean_text"
FINAL_DIR = BASE_DIR / "final_sentences"

for d in [OCR_DIR, CLEAN_DIR, FINAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ==============================
# DIGIT NORMALIZATION
# ==============================

ARABIC_TO_NEPALI = str.maketrans("0123456789", "०१२३४५६७८९")

NEPALI_DIGIT_MAP = {
    '०': 0, '१': 1, '२': 2, '३': 3, '४': 4,
    '५': 5, '६': 6, '७': 7, '८': 8, '९': 9
}

ONES = [
    "शून्य","एक","दुई","तीन","चार",
    "पाँच","छ","सात","आठ","नौ"
]

TENS = {
    10:"दस",11:"एघार",12:"बाह्र",13:"तेह्र",14:"चौध",
    15:"पन्ध्र",16:"सोह्र",17:"सत्र",18:"अठार",19:"उन्नाइस",
    20:"बीस",30:"तीस",40:"चालीस",50:"पचास",
    60:"साठी",70:"सत्तरी",80:"असी",90:"नब्बे"
}

# ==============================
# SAFE NUMBER HELPERS
# ==============================

def safe_nepali_to_int(text):
    digits = []
    for ch in text:
        if ch in NEPALI_DIGIT_MAP:
            digits.append(str(NEPALI_DIGIT_MAP[ch]))
        else:
            return None  # invalid OCR digit
    return int("".join(digits)) if digits else None


def int_to_nepali_words(n):
    if n is None:
        return ""

    if n < 10:
        return ONES[n]

    if n < 20:
        return TENS.get(n, str(n))

    if n < 100:
        tens = (n // 10) * 10
        rest = n % 10
        return TENS[tens] if rest == 0 else f"{TENS[tens]} {ONES[rest]}"

    if n < 1000:
        h, r = n // 100, n % 100
        return f"{ONES[h]} सय" if r == 0 else f"{ONES[h]} सय {int_to_nepali_words(r)}"

    if n < 10000:
        t, r = n // 1000, n % 1000
        return f"{ONES[t]} हजार" if r == 0 else f"{ONES[t]} हजार {int_to_nepali_words(r)}"

    if n < 100000:   # 10,000 – 99,999  (ten-thousands)
        t, r = n // 1000, n % 1000
        base = int_to_nepali_words(t) + " हजार"
        return base if r == 0 else f"{base} {int_to_nepali_words(r)}"

    if n < 10000000:  # 1,00,000 – 99,99,999  (लाख)
        l, r = n // 100000, n % 100000
        base = int_to_nepali_words(l) + " लाख"
        return base if r == 0 else f"{base} {int_to_nepali_words(r)}"

    if n < 1000000000:  # 1,00,00,000 – 99,99,99,999  (करोड)
        c, r = n // 10000000, n % 10000000
        base = int_to_nepali_words(c) + " करोड"
        return base if r == 0 else f"{base} {int_to_nepali_words(r)}"

    return str(n)  # fallback for numbers > 1 अरब


def normalize_numbers(text):
    text = text.translate(ARABIC_TO_NEPALI)

    def replace_number(match):
        token = match.group()

        # Decimal case
        if "." in token:
            try:
                left, right = token.split(".")
                left_num = safe_nepali_to_int(left)
                if left_num is None:
                    return token

                right_words = []
                for d in right:
                    if d in NEPALI_DIGIT_MAP:
                        right_words.append(ONES[NEPALI_DIGIT_MAP[d]])
                    else:
                        return token  # invalid OCR

                return f"{int_to_nepali_words(left_num)} दशमलव {' '.join(right_words)}"
            except Exception:
                return token

        # Integer case
        num = safe_nepali_to_int(token)
        return int_to_nepali_words(num) if num is not None else token

    return re.sub(r"[०-९]+(?:\.[०-९]+)?", replace_number, text)


# ==============================
# OCR
# ==============================

def run_ocr(pdf_path):
    try:
        pages = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        logger.exception("PDF load failed: %s", e)
        return ""

    texts = []

    logger.info("OCR: %d pages", len(pages))

    for i, page in enumerate(pages, 1):
        try:
            txt = pytesseract.image_to_string(page, lang="nep")
            txt = re.sub(r"\n{2,}", "\n\n", txt)
            texts.append(txt)
        except Exception as e:
            logger.warning("OCR failed page %d: %s", i, e)

    return "\n\n".join(texts)


# ==============================
# BASIC CLEANING
# ==============================

def basic_clean(text):
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # remove known noise
        if s in ["हरिबहादुर", "हरिबहादुर ।"]:
            continue
        if "हरिवंश आचार्य" in s:
            continue

        # remove leading numbers
        s = re.sub(r'^[०-९0-9]+\s+', '', s)

        # skip numeric-only lines
        if re.match(r'^[०-९0-9\[\]\.\s।]+$', s):
            continue

        cleaned.append(s)

    text = "\n".join(cleaned)

    # remove quotes safely
    text = re.sub(r"[“”\"'`]", "", text)

    return text


# ==============================
# FINAL PREPROCESS
# ==============================

def preprocess_nepali_text(text):
    text = unicodedata.normalize("NFC", text)

    text = normalize_numbers(text)

    # normalize punctuation
    text = re.sub(r"[|¦!?]", "।", text)
    text = re.sub(r"।{2,}", "।", text)

    # merge lines safely
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)

    # KEEP digits + devanagari (less destructive)
    text = re.sub(r"[^\u0900-\u097F०-९\s।]", "", text)

    # sentence split
    parts = text.split("।")

    sentences = []
    for s in parts:
        s = s.strip()
        if len(s) > 2:
            sentences.append(s + " ।")

    return sentences


# ==============================
# MAIN PIPELINE
# ==============================

def process_pdf(pdf_path):
    name = pdf_path.stem
    logger.info("Processing: %s", name)

    ocr_text = run_ocr(pdf_path)

    if not ocr_text.strip():
        return {"success": False, "error": "Empty OCR output"}

    # save OCR
    (OCR_DIR / f"{name}.txt").write_text(ocr_text, encoding="utf8")

    cleaned = basic_clean(ocr_text)
    (CLEAN_DIR / f"{name}_clean.txt").write_text(cleaned, encoding="utf8")

    try:
        sentences = preprocess_nepali_text(cleaned)

        final_file = FINAL_DIR / f"{name}_sentences.txt"
        final_file.write_text("\n".join(sentences), encoding="utf8")

        logger.info("Done: %d sentences", len(sentences))

        return {
            "success": True,
            "name": name,
            "sentence_count": len(sentences),
            "file_path": str(final_file)
        }

    except Exception as e:
        logger.exception("Failed: %s", e)
        return {"success": False, "error": str(e)}


# ==============================
# RUN
# ==============================

def main():
    pdf_files = sorted(BASE_DIR.glob("*.pdf"))

    logger.info("Found %d PDFs", len(pdf_files))

    results = []
    for pdf in pdf_files:
        results.append(process_pdf(pdf))

    logger.info("All done")
    return results


if __name__ == "__main__":
    main()
# ==============================
# Nepali Audiobook Preprocessing
# ==============================

import os
import re
import unicodedata
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract

# ==============================
# PATH CONFIGURATION
# ==============================

BASE_DIR = Path("User_input")
OCR_DIR = BASE_DIR / "ocr_text"
CLEAN_DIR = BASE_DIR / "clean_text"
FINAL_DIR = BASE_DIR / "final_sentences"

OCR_DIR.mkdir(parents=True, exist_ok=True)
CLEAN_DIR.mkdir(parents=True, exist_ok=True)
FINAL_DIR.mkdir(parents=True, exist_ok=True)

# ==============================
# DIGIT NORMALIZATION
# ==============================

ARABIC_TO_NEPALI = str.maketrans("0123456789", "०१२३४५६७८९")

NEPALI_DIGIT_MAP = {
    '०':0,'१':1,'२':2,'३':3,'४':4,
    '५':5,'६':6,'७':7,'८':8,'९':9
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

def nepali_number_to_int(nep):
    return int("".join(str(NEPALI_DIGIT_MAP[d]) for d in nep))

def int_to_nepali_words(n):

    if n < 10:
        return ONES[n]

    if n < 20:
        return TENS[n]

    if n < 100:
        tens = (n//10)*10
        rest = n%10
        if rest == 0:
            return TENS[tens]
        return TENS[tens] + " " + ONES[rest]

    if n < 1000:
        h = n//100
        r = n%100
        if r == 0:
            return ONES[h] + " सय"
        return ONES[h] + " सय " + int_to_nepali_words(r)

    if n < 10000:
        t = n//1000
        r = n%1000
        if r == 0:
            return ONES[t] + " हजार"
        return ONES[t] + " हजार " + int_to_nepali_words(r)

    return str(n)

def normalize_numbers(text):

    text = text.translate(ARABIC_TO_NEPALI)

    def decimal_replace(m):
        left,right = m.group().split(".")
        return (
            int_to_nepali_words(nepali_number_to_int(left))
            + " दशमलव "
            + " ".join(ONES[NEPALI_DIGIT_MAP[d]] for d in right)
        )

    text = re.sub(r"[०-९]+\.[०-९]+", decimal_replace, text)

    def int_replace(m):
        num = nepali_number_to_int(m.group())
        return int_to_nepali_words(num)

    text = re.sub(r"[०-९]+", int_replace, text)

    return text


# ==============================
# OCR
# ==============================

def run_ocr(pdf_path):

    pages = convert_from_path(pdf_path, dpi=300)

    texts = []

    for i,page in enumerate(pages,1):
        print(f"OCR page {i}/{len(pages)}")
        txt = pytesseract.image_to_string(page, lang="nep")
        txt = re.sub(r"\n{2,}","\n\n",txt)
        texts.append(txt)

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

        if s in ["हरिबहादुर","हरिबहादुर ।"]:
            continue

        if "हरिवंश आचार्य" in s:
            continue

        s = re.sub(r'^[०-९0-9]+\s+','',s)

        if re.match(r'^[०-९0-9\[\]\.\s।]+$',s):
            continue

        cleaned.append(s)

    text = "\n".join(cleaned)

    text = re.sub(r"[“”\"\'`]", "", text)
    text = re.sub(r"\s+\n","\n",text)

    return text


# ==============================
# FULL TEXT PREPROCESS
# ==============================

def preprocess_nepali_text(text):

    text = unicodedata.normalize("NFC", text)

    text = normalize_numbers(text)

    text = re.sub(r"[|¦!?]","।",text)
    text = re.sub(r"।+","।",text)

    text = re.sub(r"\n(?=[^\n])"," ",text)
    text = re.sub(r"\s+"," ",text)

    text = re.sub(r"[^\u0900-\u097F\s।]","",text)

    raw = text.split("।")

    sentences = []

    for s in raw:
        s = s.strip()
        if len(s) > 1:
            sentences.append(s + " ।")

    return sentences


# ==============================
# MAIN PIPELINE
# ==============================

def process_pdf(pdf_path):

    name = pdf_path.stem

    print("\nProcessing:", name)

    # OCR
    ocr_text = run_ocr(pdf_path)

    ocr_file = OCR_DIR / f"{name}.txt"
    ocr_file.write_text(ocr_text,encoding="utf8")

    # Clean
    cleaned = basic_clean(ocr_text)

    clean_file = CLEAN_DIR / f"{name}_clean.txt"
    clean_file.write_text(cleaned,encoding="utf8")

    # Final preprocess
    try:
        sentences = preprocess_nepali_text(cleaned)
        final_file = FINAL_DIR / f"{name}_sentences.txt"
        final_file.write_text("\n".join(sentences), encoding="utf8")
        
        stats = {
            "success": True,
            "name": name,
            "sentence_count": len(sentences),
            "file_path": str(final_file)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

    print("Saved:", final_file)
    return stats


# ==============================
# RUN
# ==============================

def main():

    pdf_files = sorted(BASE_DIR.glob("*.pdf"))

    print("Found PDFs:",len(pdf_files))

    for pdf in pdf_files:
        process_pdf(pdf)

    print("\nAll chapters processed")


if __name__ == "__main__":
    main()
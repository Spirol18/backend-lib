import regex as re
import fitz
import pytesseract
import os
from logger_config import get_logger

logger = get_logger("ocr_text_extraction")

class ocr_pdf:
    doc = None
    tempImageName = os.path.join('output', 'cover.png')

    if os.name == 'nt':  # Windows
        pytesseract.pytesseract.tesseract_cmd = os.path.join(".", "Tesseract-OCR", "tesseract.exe")
    # On Mac/Linux, we assume it is in PATH

    # ---------- Preeti to Unicode Mapping ----------
    unicodeatoz = ["ब","द","अ","म","भ","ा","न","ज","ष्","व","प","ि","फ","ल","य","उ","त्र","च","क","त","ग","ख","ध","ह","थ","श"]
    unicodeAtoZ = ["ब्","ध","ऋ","म्","भ्","ँ","न्","ज्","क्ष्","व्","प्","ी","ः","ल्","इ","ए","त्त","च्","क्","त्","ग्","ख्","ध्","ह्","थ्","श्"]
    unicode0to9 = ["ण्","ज्ञ","द्द","घ","द्ध","छ","ट","ठ","ड","ढ"]
    symbolsDict = {
        "~":"ञ्","`":"ञ","!":"१","@":"२","#":"३","$":"४","%":"५","^":"६","&":"७","*":"८",
        "(":"९",")":"०","-":"(","_":")","+":"ं","[":"ृ","{":"र्","]":"े","}":"ै","\\":"्",
        "|":"्र",";":"स",":":"स्","'":"ु","\"":"ू",",":",","<":"?",".":"।",">":"श्र",
        "/":"र","?":"रु","=":".","ˆ":"फ्","Î":"ङ्ख","Í":"ङ्क","å":"द्व","÷":"/"
    }

    # ---------- Page Count ----------
    def getPageCount():
        return ocr_pdf.doc.page_count
    
    def __del__(self):
        if ocr_pdf.doc:
            ocr_pdf.doc.close()
    
    # ---------- Save first page as image ----------
    def save_front_page(path):
        ocr_pdf.create_temp_img(0, path)
    
    # ---------- OCR ----------
    def ocr_main(img, lang='Devanagari'):
        return pytesseract.image_to_string(img, lang=lang)
    
    # ---------- Load PDF ----------
    def load_pdf(fileLocation:str):
        try:
            ocr_pdf.doc = fitz.open(fileLocation)
            logger.info("PDF loaded successfully: '%s'", fileLocation)
        except Exception as e:
            logger.error("Failed to load PDF '%s': %s", fileLocation, e)
    
    # ---------- Create temporary image for OCR ----------
    def create_temp_img(pageNumber, pageName:str=tempImageName):
        if not ocr_pdf.doc:
            logger.error("create_temp_img called but PDF has not been loaded")
            exit(-1)

        if abs(pageNumber) > ocr_pdf.doc.page_count-1:
            logger.error("create_temp_img: page number %d is out of range (0–%d)", pageNumber, ocr_pdf.doc.page_count-1)
            exit(-1)

        page = ocr_pdf.doc[pageNumber]
        mat = fitz.Matrix(2,2)  # zoom for clarity
        pix = page.get_pixmap(matrix=mat, alpha=False)
        os.makedirs(os.path.dirname(pageName), exist_ok=True)
        pix.save(pageName)
        logger.debug("Temp image saved: '%s' (page %d)", pageName, pageNumber)

    # ---------- OCR a single page ----------
    def ocr_page(pageNumber: int):
        ocr_pdf.create_temp_img(pageNumber)
        extractedText = ocr_pdf.ocr_main(ocr_pdf.tempImageName)
        # Detect Preeti and convert if needed
        if any(ch in extractedText for ch in ['k','f','/']):
            extractedText = ocr_pdf.convert(extractedText)
        filteredText = ocr_pdf.unwantedCharProcessing(extractedText)
        return ocr_pdf.sentenceList(filteredText)

    # ---------- Clean unwanted characters ----------
    def unwantedCharProcessing(extractedText: str):
        extractedText = re.sub(r'\n+', ' ', extractedText)
        # Keep Devanagari letters (\u0900-\u097F), Nepali digits (\u0966-\u096F) and punctuation
        return "".join(re.findall(r'[\u0900-\u097F\u0966-\u096F .,;:!?\-)]', extractedText))

    # ---------- Preeti Normalization ----------
    @staticmethod
    def normalizePreeti(preetitxt):
        normalized = ''
        previoussymbol = ''
        replacements = {
            'qm': 's|', 'f]': 'ो', 'km': 'फ', '0f': 'ण', 'If': 'क्ष',
            'if': 'ष', 'cf': 'आ', 'O{': '', 'Í': '', 'æ': '', 'Æ': '',
            'Ù': '', '«': '|', '¿': '?'
        }
        for k, v in replacements.items():
            preetitxt = preetitxt.replace(k, v)

        index = -1
        while index + 1 < len(preetitxt):
            index += 1
            character = preetitxt[index]
            try:
                if preetitxt[index + 2] == '{':
                    temp = preetitxt[index + 1]
                    if temp in ['f', 'ो', '}', 'L']:
                        normalized += '{' + character + temp
                        index += 2
                        continue
                if preetitxt[index + 1] == '{':
                    if character != 'f':
                        normalized += '{' + character
                        index += 1
                        continue
            except IndexError:
                pass
            if character == 'l':
                previoussymbol = 'l'
                continue
            else:
                normalized += character + previoussymbol
                previoussymbol = ''
        return normalized

    # ---------- Convert Preeti to Unicode ----------
    @staticmethod
    def convert(preeti):
        converted = ''
        normalized = ocr_pdf.normalizePreeti(preeti)
        for ch in normalized:
            try:
                if 'a' <= ch <= 'z':
                    converted += ocr_pdf.unicodeatoz[ord(ch)-97]
                elif 'A' <= ch <= 'Z':
                    converted += ocr_pdf.unicodeAtoZ[ord(ch)-65]
                elif '0' <= ch <= '9':
                    converted += ocr_pdf.unicode0to9[ord(ch)-48]
                else:
                    converted += ocr_pdf.symbolsDict.get(ch, ch)
            except:
                converted += ch
        return converted

    # ---------- Convert Nepali numbers to words ----------
    def num_to_word(num_str):
        nep_to_eng = str.maketrans("०१२३४५६७८९", "0123456789")
        num = int(num_str.translate(nep_to_eng))
        ones = ["", "एक", "दुई", "तीन", "चार", "पाँच", "छ", "सात", "आठ", "नौ"]
        teens = ["दश", "एघार", "बाह्र", "तेह्र", "चौध", "पन्ध्र", "सोह्र", "सत्र", "अठार", "उन्नाइस"]
        tens_words = {20:"बीस",30:"तीस",40:"चालीस",50:"पचास",60:"साठी",70:"सत्तरी",80:"असी",90:"नब्बे"}
        def two_digit(n):
            if n < 10: return ones[n]
            elif 10 <= n < 20: return teens[n-10]
            else: tens=(n//10)*10; unit=n%10; return tens_words.get(tens,"") + (" "+ones[unit] if unit else "")
        def three_digit(n):
            hundred = n//100; rest=n%100; result=""
            if hundred: result += ones[hundred]+" सय "
            if rest: result += two_digit(rest)
            return result.strip()
        result=""
        if num>=100000: lakh=num//100000; result+=two_digit(lakh)+" लाख "; num%=100000
        if num>=1000: thousand=num//1000; result+=two_digit(thousand)+" हजार "; num%=1000
        if num>0: result+=three_digit(num)
        return result.strip()

    # ---------- Split text into sentences and convert numbers ----------
    def sentenceList(processedText: str):
        unprocessedList = re.split(r'(?<=[।!?])', processedText)
        processedList=[]
        for sentence in unprocessedList:
            sentence = sentence.strip()
            if not sentence: continue
            text=''
            for word in sentence.split():
                if re.search("[\u0966-\u096F]+", word): text+=ocr_pdf.num_to_word(word)+' '
                else: text+=word+' '
            text=text.strip()
            if len(text)>164:
                corrected=ocr_pdf.lengthCorrector(text)
                for s in corrected: processedList.append(s+'।')
            else:
                processedList.append(text+'।')
        return processedList

    # ---------- Split long sentences ----------
    def lengthCorrector(sent:str):
        breakdown=[]
        while len(sent)>164:
            i=164
            while i>0 and sent[i]!=' ': i-=1
            breakdown.append(sent[:i+1].strip())
            sent=sent[i+1:].strip()
        if sent: breakdown.append(sent)
        return breakdown
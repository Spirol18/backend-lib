import regex as re
import fitz
import pytesseract

import os

class ocr_pdf:
    doc = None
    tempImageName = os.path.join('output', 'cover.png')

    if os.name == 'nt': # Windows
        pytesseract.pytesseract.tesseract_cmd = os.path.join(".", "Tesseract-OCR", "tesseract.exe")
    # On Mac/Linux, we assume it is in the PATH or the user will install it

    def getPageCount():
        return ocr_pdf.doc.page_count
    
    def __del__(self):
        ocr_pdf.doc.close()
    
    def save_front_page(path):
        ocr_pdf.create_temp_img(0, path)
    
    def ocr_main(img, lang='Devanagari'):
        return pytesseract.image_to_string(img, lang)
    
    def load_pdf(fileLocation:str):
        try:
            ocr_pdf.doc = fitz.open(fileLocation)
        except:
            print("Error: Couldn't load pdf: Wrong Location")

    def create_temp_img(pageNumber, pageName:str=tempImageName):
        if not ocr_pdf.doc:
            print("Error: PDF has not loaded successfully")
            exit(-1)
        
        if abs(pageNumber) > ocr_pdf.doc.page_count-1:
            print("Error: Page Number invalid")
            exit(-1)
        
        page = ocr_pdf.doc[pageNumber]
        #1,1 stands for zoom_x,zoom_y. Higher zoom clear text, unclear images i.e. amplifies noise
        mat = fitz.Matrix(2,2)

        pix = page.get_pixmap(matrix= mat, alpha=False)
        pix.save(pageName)
   
    def ocr_page(pageNumber: int):
        ocr_pdf.create_temp_img(pageNumber)
        extractedText = ocr_pdf.ocr_main(ocr_pdf.tempImageName)
        filteredText = ocr_pdf.unwantedCharProcessing(extractedText)
        return ocr_pdf.sentenceList(filteredText)
        
    def unwantedCharProcessing(extractedText: str):
        extractedText = re.sub(r'\n+', ' ', extractedText)
        #devanagari unicode starts from 0900-097F
        return "".join(re.split("[^\u0900-\u097F .)?:;!|-]*", extractedText))

    def sentenceList(processedText: str):
        #separate from characters excepts unicode excluding ।, ।।, -
        return re.split(r'[^\u0900-\u0963\u0966-\u097F,\- ]', processedText)

    def num_to_word(num):
        return 'नम्बर'

    def sentenceList(processedText: str):
            #separate from characters excepts unicode excluding ।, ।।, -
            unprocessedList = re.split(r'[^\u0900-\u0963\u0966-\u097F,\- ]', processedText)

            processedList = []

            for sentence in unprocessedList:
                #print(sent)
                sentence = sentence.lstrip()
                if not sentence:
                    #if empty then next sentence
                    continue
                
                #if sentence contains number, convert it to wording
                if re.search("[\u0966-\u096F]", sentence):
                    text = ''
                    for word in sentence.split():
                        if re.search("[\u0966-\u096F]", word):
                            text += ocr_pdf.num_to_word(word)
                            continue
                        text += word + ' '

                    if len(sentence) > 164:
                        corrected = ocr_pdf.lengthCorrector(sentence)
                        for sentence in corrected:
                            processedList.append(sentence + '।')
                    else:
                        processedList.append(text + '।')
                else:
                    if len(sentence) > 164:
                        corrected = ocr_pdf.lengthCorrector(sentence)
                        for sentence in corrected:
                            processedList.append(sentence + '।')
                    else:
                        processedList.append(sentence + '।')

            return processedList
    
    def lengthCorrector(sent:str):
        breakdown = []
        while len(sent)>164:
            i = 164
            while sent[i] != ' ':
                i-=1
            breakdown.append(sent[:i+1])
            sent = sent[i+1:len(sent)]

        breakdown.append(sent[:i])
        return breakdown

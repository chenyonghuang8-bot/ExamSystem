import fitz, pytesseract
from PIL import Image
def ocr_pdf(path, dpi=200):
    out = []
    for p in fitz.open(path):
        pix = p.get_pixmap(matrix=fitz.Matrix(2000 / p.rect.width, 2000 / p.rect.width))
        out.append(pytesseract.image_to_string(Image.frombytes("RGB", [pix.width, pix.height], pix.samples), lang="chi_sim", config="--psm 6"))
    return "\n\f\n".join(out)

import fitz, pytesseract, sys, os, glob
from PIL import Image
from concurrent.futures import ProcessPoolExecutor
A=sys.argv[1]; out=sys.argv[2]
def ocr(args):
    f,i=args
    d=fitz.open(f); pix=d[i].get_pixmap(matrix=fitz.Matrix(2000/d[i].rect.width,2000/d[i].rect.width))
    img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
    return pytesseract.image_to_string(img,lang="chi_sim",config="--psm 6")
jobs=[]
for f in sorted(glob.glob(A+"/*.pdf")):
    d=fitz.open(f)
    if len("".join(p.get_text() for p in d).strip())>200: continue
    jobs.append(f)
with ProcessPoolExecutor(os.cpu_count()) as ex:
    for f in jobs:
        n=len(fitz.open(f))
        texts=list(ex.map(ocr,[(f,i) for i in range(n)]))
        open(os.path.join(out,os.path.basename(f)+".txt"),"w").write("\n\f\n".join(texts))
        print("done",f,flush=True)

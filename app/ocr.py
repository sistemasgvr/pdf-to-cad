"""
ocr.py — Hilos de reconocimiento de texto.

OcrWorker: texto impreso (Tesseract, multi-orientación 0/90/270°).
IcrWorker: texto manuscrito (EasyOCR, offline).
Ambos importan sus dependencias de forma perezosa dentro de run(), de modo que la
app arranca aunque cv2/pytesseract/easyocr no estén instalados.
"""
from PySide6 import QtCore


class OcrWorker(QtCore.QThread):
    done = QtCore.Signal(object, str)

    def __init__(self, gray): super().__init__(); self.gray = gray

    def run(self):
        try:
            import cv2, pytesseract
            from pytesseract import Output
            from collections import defaultdict
            g = self.gray; H, W = g.shape
            s = min(1.0, 2400.0 / max(H, W))
            gd = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else g
            Hd, Wd = gd.shape
            codes = {90: cv2.ROTATE_90_CLOCKWISE, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
            def back(o, ox, oy):
                if o == 0: return ox, oy
                if o == 90: return oy, Hd - 1 - ox
                return Wd - 1 - oy, ox
            out = []
            for o in (0, 90, 270):
                img = gd if o == 0 else cv2.rotate(gd, codes[o])
                data = pytesseract.image_to_data(img, output_type=Output.DICT, config="--psm 11")
                lines = defaultdict(list)
                for i in range(len(data["text"])):
                    t = (data["text"][i] or "").strip()
                    if not t: continue
                    try: conf = float(data["conf"][i])
                    except: conf = -1
                    if conf < 25: continue
                    k = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                    lines[k].append((data["left"][i], data["top"][i], data["width"][i], data["height"][i], t))
                for ws in lines.values():
                    ws.sort(key=lambda w: w[0]); txt = " ".join(w[4] for w in ws)
                    x = min(w[0] for w in ws); y = min(w[1] for w in ws)
                    x1 = max(w[0] + w[2] for w in ws); y1 = max(w[1] + w[3] for w in ws)
                    cs = [back(o, x, y), back(o, x1, y), back(o, x, y1), back(o, x1, y1)]
                    xs = [c[0] / s for c in cs]; ys = [c[1] / s for c in cs]
                    out.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), txt))
            self.done.emit(out, "")
        except Exception as e:
            self.done.emit([], str(e))


class IcrWorker(QtCore.QThread):
    done = QtCore.Signal(object, str)

    def __init__(self, gray): super().__init__(); self.gray = gray

    def run(self):
        try:
            import easyocr, cv2
            g = self.gray; H, W = g.shape
            s = min(1.0, 2000.0 / max(H, W))
            gd = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else g
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            out = []
            for bbox, txt, conf in reader.readtext(gd, detail=1, paragraph=False):
                if not txt.strip() or conf < 0.15: continue
                xs = [p[0] / s for p in bbox]; ys = [p[1] / s for p in bbox]
                out.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), txt.strip()))
            self.done.emit(out, "")
        except ModuleNotFoundError:
            self.done.emit(None, "missing")
        except Exception as e:
            self.done.emit([], str(e))

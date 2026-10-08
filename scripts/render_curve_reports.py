"""Render the reported DU06 details with the recognized geometry over the PDF.

Run from the repository root. Writes output/curve_precision_review.png.
Orange is the geometry reconstructed by the editor, not the corner polygon.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'app'), str(ROOT)]
import fitz
from PIL import Image, ImageDraw, ImageFont
from reconocimiento import recognition as rec
from reconocimiento import recognition_trace as trace
from nucleo import model_ops


def main():
    pdf = ROOT/'DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf'
    specs = [
        (3, 'TELECOM', (480, 1438, 610, 1502), '1. Curva en S y fin en el recorte'),
        (3, 'TELECOM', (785, 990, 925, 1040), '2. Conexion a la boveda sin duplicacion'),
        (4, 'TELECOM', (750, 1070, 860, 1145), '3. Lazo y diagonal hasta su extremo'),
        (4, 'ELECTRICO', (895, 810, 927, 887), '4. Curva electrica con cambio de radio'),
        (4, 'TELECOM', (625, 1185, 770, 1260), '5. Lazo inferior y extremo original'),
        (4, 'TELECOM', (680, 1190, 1155, 1225), '6. Ramal inferior'),
    ]
    result = {}
    doc = fitz.open(pdf)
    canvas = Image.new('RGB', (1600, 1650), '#eeeeee')
    for index, (page, utility, bounds, label) in enumerate(specs):
        key = page, utility
        if key not in result:
            result[key] = rec.recognize_page(pdf, page, utility=utility, zoom=3.5)
        box = fitz.Rect(bounds)
        scale = min(760/box.width, 475/box.height)
        pix = doc[page].get_pixmap(matrix=fitz.Matrix(scale, scale), clip=box, alpha=False)
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        draw = ImageDraw.Draw(img)
        for pl in result[key].drawable:
            # Recompute from the editor's corner/radius model to expose any
            # clamping or mismatch instead of just trusting stored arc fields.
            fillets = {}
            for i, g in pl.fillets.items():
                geo = model_ops.fillet_geo(pl.pts_pdf[i-1], pl.pts_pdf[i], pl.pts_pdf[i+1],
                                          g['r_px'], max_frac=1., max_frac_next=1., tol_r=0.)
                if geo:
                    fillets[i] = dict(a=geo['t1'], b=geo['t2'], center=geo['center'], r_px=geo['r'])
            for a, b, arc in trace._drawing((pl.pts_pdf, pl.kinds, fillets)):
                if arc:
                    _, _, c, r, a0, sw = arc
                    n = max(8, math.ceil(abs(sw)*r/3.5*scale))
                    P = [(c[0]+r*math.cos(a0+sw*k/n), c[1]+r*math.sin(a0+sw*k/n)) for k in range(n+1)]
                else:
                    P = [a, b]
                xy = [((x/3.5-box.x0)*scale, (y/3.5-box.y0)*scale) for x, y in P]
                draw.line(xy, fill='#ff8500', width=2)
        left, top = (index % 2)*800+20, (index//2)*550+55
        canvas.paste(img, (left, top))
        if index == 4:
            img.save(ROOT/'output'/'curve_text_gaps_review.png')
        ImageDraw.Draw(canvas).text((left, top-35), label, fill='#222222', font=ImageFont.load_default(size=22))
    target = ROOT/'output'/'curve_precision_review.png'
    canvas.save(target)
    print(target)


if __name__ == '__main__':
    main()

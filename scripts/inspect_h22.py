"""Render DU08 sheet 22 using the editor's actual corner/radius geometry."""
import sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT)]
import fitz
from PIL import Image,ImageDraw
import recognition as rec
import recognition_trace as trace
import model_ops
PDF=Path('C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf')
r=rec.recognize_page(PDF,21,utility='ELECTRICO',zoom=1.)
doc=fitz.open(PDF)
box=fitz.Rect(710,610,805,680)
f=10.
pix=doc[21].get_pixmap(matrix=fitz.Matrix(f,f),clip=box)
im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
draw=ImageDraw.Draw(im)
for p in r.drawable:
 fillets = {}
 for i,fl in p.fillets.items():
  geo = model_ops.fillet_geo(p.pts_pdf[i-1],p.pts_pdf[i],p.pts_pdf[i+1],fl['r_px'],
                             max_frac=1.,max_frac_next=1.,tol_r=0.)
  if geo:
   fillets[i] = dict(a=geo['t1'],b=geo['t2'],center=geo['center'],r_px=geo['r'])
 for a,b,arc in trace._drawing((p.pts_pdf,p.kinds,fillets)):
  if arc:
   _,_,c,rad,a0,sw=arc
   n=max(8,int(abs(sw)*rad*f))
   pts=[(c[0]+rad*math.cos(a0+sw*k/n),c[1]+rad*math.sin(a0+sw*k/n)) for k in range(n+1)]
  else: pts=[a,b]
  draw.line([((x-box.x0)*f,(y-box.y0)*f) for x,y in pts],fill='#ff3333',width=2)
im.save(ROOT/'output'/'du08_h22_detail.png')

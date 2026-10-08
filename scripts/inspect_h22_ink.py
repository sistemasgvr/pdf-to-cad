import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import fitz; from reconocimiento import recognition as r
p=fitz.open('C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf')[21]
paths,*_=r.gather_paths(p,lambda o:r.classify_ocg(o,'ELECTRICO'),set(),None)
for path in paths:
 for s in r.ink_strokes([path],lambda q:q):
  if any(740<x<790 and 620<y<650 for x,y in s): print(path.get('layer'),s)

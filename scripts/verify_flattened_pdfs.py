"""Inspect an external PDF corpus and exercise manually selected style layers.

Usage: python scripts/verify_flattened_pdfs.py <folder>
The chosen widths are validation examples for Phoenix, not application rules.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

import fitz
from hoja import pdf_layers
from reconocimiento import recognition as rec


def main(folder):
    report = []
    for path in sorted(Path(folder).glob("*.pdf")):
        with fitz.open(path) as doc:
            rows = [pdf_layers.page_layers(doc, i, letters=False) for i in range(len(doc))]
            entry = dict(file=path.name, pages=len(doc), native_layers=len(doc.get_ocgs()),
                         style_groups=[len(r) for r in rows],
                         images_first_page=len(doc[0].get_images()))
            if "Sewer" in path.name or "Water" in path.name:
                water = "Water" in path.name
                width = (.71 if water else .73) if "North" in path.name else (.38 if water else .39)
                chosen = [r["name"] for r in rows[0] if r["short"] == f"Negro {width:.2f} pt · continuo"]
                assert chosen, (path.name, width)
                result = rec.recognize_page(path, page_index=0, utility="AGUA" if water else "ALCANTARILLADO",
                    zoom=1, scale_ft_per_pt=1, layer_roles={rec.ROLE_LINEAS: chosen, rec.ROLE_BUZONES: []})
                assert result.drawable, path.name
                assert all(not p.abandoned for p in result.polylines), path.name
                entry.update(selected_width=width, lines=len(result.drawable),
                             structures=len(result.vault_pts), warnings=result.warnings)
            report.append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    out = ROOT / "output" / "flattened-pdf-validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])

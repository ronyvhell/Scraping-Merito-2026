"""Explora extracción con layout=True para preservar columnas."""
from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber

PDF = Path("PDF") / "VERSIÓN 2. CONVOCATORIAS CONCURSO DE MÉRTOS RES 108 DEL 23 DE ABRIL DE 2026.pdf"


def main() -> int:
    with pdfplumber.open(PDF) as pdf:
        for p in [1, 2, 5, 9]:
            page = pdf.pages[p - 1]
            print(f"\n{'='*100}\nPÁGINA {p}  (W={page.width:.0f} H={page.height:.0f})\n{'='*100}")
            text = page.extract_text(layout=True, x_density=6, y_density=10)
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

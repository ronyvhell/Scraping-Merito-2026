"""Explora cómo pdfplumber ve las primeras páginas del PDF.

Imprime el texto crudo y las tablas detectadas para cada página solicitada,
para definir la mejor estrategia de extracción.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pdfplumber

DEFAULT_PDF = Path("PDF") / "VERSIÓN 2. CONVOCATORIAS CONCURSO DE MÉRTOS RES 108 DEL 23 DE ABRIL DE 2026.pdf"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--pages", default="1,2,5,9,10", help="Páginas (1-indexed) separadas por coma")
    parser.add_argument("--mode", choices=["text", "tables", "words"], default="tables")
    args = parser.parse_args()

    pages_to_check = [int(x) for x in args.pages.split(",")]

    with pdfplumber.open(args.pdf) as pdf:
        for p in pages_to_check:
            page = pdf.pages[p - 1]
            print(f"\n{'='*80}\nPÁGINA {p}\n{'='*80}")

            if args.mode == "text":
                print(page.extract_text())
            elif args.mode == "tables":
                tables = page.extract_tables()
                print(f"Tablas detectadas: {len(tables)}")
                for ti, t in enumerate(tables):
                    print(f"\n--- Tabla {ti + 1} ({len(t)} filas) ---")
                    for row in t:
                        print([str(c)[:60] if c else "" for c in row])
            elif args.mode == "words":
                words = page.extract_words(x_tolerance=2, y_tolerance=3)
                for w in words[:80]:
                    print(f"{w['top']:.0f},{w['x0']:.0f}: {w['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

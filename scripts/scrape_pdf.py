"""Scraper de convocatorias del Concurso de Méritos - Procuraduría General de la Nación 2026.

Lee el PDF "VERSIÓN 2. CONVOCATORIAS CONCURSO DE MÉRTOS RES 108 DEL 23 DE ABRIL DE 2026.pdf",
identifica cada convocatoria (~291 en total), extrae todos los campos relevantes
y exporta:
  - csv/convocatorias_por_ciudad.csv (una fila por ciudad/sede)
  - csv/convocatorias_por_ciudad.xlsx (idem en Excel)
  - csv/convocatorias_resumen.csv (una fila por convocatoria, con ubicaciones agregadas)
  - csv/convocatorias_resumen.xlsx

Uso:
    python scripts/scrape_pdf.py
    python scripts/scrape_pdf.py --pdf "ruta.pdf" --out csv/
    python scripts/scrape_pdf.py --max-convocatorias 5   # útil para pruebas
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

import pandas as pd
import pdfplumber

DEFAULT_PDF = Path("PDF") / "VERSIÓN 2. CONVOCATORIAS CONCURSO DE MÉRTOS RES 108 DEL 23 DE ABRIL DE 2026.pdf"
DEFAULT_OUT = Path("csv")


# ---------------------------------------------------------------------------
# Utilidades de limpieza de texto
# ---------------------------------------------------------------------------

# Patrones del header/footer institucional que se repiten en TODAS las páginas.
# Se buscan EN CUALQUIER PARTE de cada línea y se sustituyen por espacios del mismo
# largo para preservar las posiciones X de las demás columnas (que vienen alineadas
# con layout=True).
HEADER_FRAGMENTS = [
    re.compile(r"FORMATO:\s*CONVOCATORIA", re.IGNORECASE),
    re.compile(r"PROCESO:\s*TALENTO\s+HUMANO", re.IGNORECASE),
    re.compile(r"\bPROCURADUR[IÍ]A\b", re.IGNORECASE),
    re.compile(r"\bGENERAL\s+DE\s+LA\s+NACI[OÓ]N\b", re.IGNORECASE),
    re.compile(r"\bCO\s*L\s*O\s*M\s*B\s*I\s*A\b", re.IGNORECASE),
    re.compile(r"\bVersi[óo]n\s+\d+\b(?!\s+No\.)", re.IGNORECASE),
    re.compile(r"\bFecha\s+\d{2}/\d{2}/\d{4}\b", re.IGNORECASE),
    re.compile(r"\bC[óo]digo\s+TH-F-\d+\b", re.IGNORECASE),
]


def _blank_out(text: str, pattern: re.Pattern) -> str:
    """Sustituye cada match de ``pattern`` por espacios del mismo largo."""
    def repl(m: re.Match) -> str:
        return " " * (m.end() - m.start())
    return pattern.sub(repl, text)


def strip_headers_footers(page_text: str) -> str:
    """Quita el encabezado/pie de página preservando posiciones X de las demás columnas."""
    out_lines: list[str] = []
    for raw in page_text.splitlines():
        line = raw
        for pat in HEADER_FRAGMENTS:
            line = _blank_out(line, pat)
        # Línea quedó vacía
        if not line.strip():
            out_lines.append("")
            continue
        # Pie de página: línea cuyo único contenido es un número de página.
        if re.fullmatch(r"\s*\d{1,3}\s*", line):
            continue
        out_lines.append(line.rstrip())

    # Colapsar múltiples líneas vacías
    cleaned: list[str] = []
    prev_blank = False
    for ln in out_lines:
        is_blank = not ln.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(ln)
        prev_blank = is_blank
    # Quitar líneas vacías al inicio y final
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


def collapse_ws(text: str) -> str:
    """Colapsa espacios en blanco internos manteniendo saltos de línea."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Detección de convocatorias en el PDF
# ---------------------------------------------------------------------------

# Número de la convocatoria, p.ej.: "CONVOCATORIA No. 01 – 2026" / "CONVOCATORIA No. 03-2026"
RE_CONVOCATORIA = re.compile(
    r"CONVOCATORIA\s+No\.?\s*(\d{1,4})\s*[-–]\s*\s*2026",
    re.IGNORECASE,
)


@dataclass
class ConvocatoriaSpan:
    numero: int
    pagina_inicio: int  # 1-indexed
    pagina_fin: int  # 1-indexed inclusive


def find_convocatoria_spans(pdf_path: Path, cache_path: Path | None = None) -> list[ConvocatoriaSpan]:
    """Recorre el PDF y devuelve, por cada convocatoria, sus páginas inicial y final.

    Si se proporciona ``cache_path`` y el archivo existe, se carga de allí. Si no,
    se calcula y se guarda al terminar.
    """
    if cache_path and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_mtime = data.get("pdf_mtime")
            if cached_mtime == pdf_path.stat().st_mtime:
                return [ConvocatoriaSpan(**s) for s in data["spans"]]
        except Exception:
            pass  # cache corrupto, ignoramos

    starts: list[tuple[int, int]] = []
    total_pages = 0
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            m = RE_CONVOCATORIA.search(text)
            if m:
                numero = int(m.group(1))
                if not starts or starts[-1][0] != numero:
                    starts.append((numero, i))

    spans: list[ConvocatoriaSpan] = []
    for idx, (numero, page_start) in enumerate(starts):
        page_end = starts[idx + 1][1] - 1 if idx + 1 < len(starts) else total_pages
        spans.append(ConvocatoriaSpan(numero=numero, pagina_inicio=page_start, pagina_fin=page_end))

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "pdf_mtime": pdf_path.stat().st_mtime,
                    "spans": [asdict(s) for s in spans],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return spans


# ---------------------------------------------------------------------------
# Parsing del texto de cada convocatoria
# ---------------------------------------------------------------------------

# Etiquetas de las secciones principales (en mayúsculas). Aparecen al inicio de línea.
SECTION_HEADINGS = [
    ("identificacion", re.compile(r"^\s*1\.\s*IDENTIFICACI[ÓO]N\s+DEL\s+EMPLEO\s*$", re.IGNORECASE)),
    ("requisitos", re.compile(r"^\s*2\.\s*REQUISITOS\s+M[ÍI]NIMOS\s+DEL\s+EMPLEO\s*$", re.IGNORECASE)),
    ("proposito_funciones", re.compile(r"^\s*3\.\s*PROP[ÓO]SITO\s+Y\s+FUNCIONES\s+DEL\s+EMPLEO\s*$", re.IGNORECASE)),
    ("conocimientos_especificos", re.compile(r"^\s*4\.\s*CONOCIMIENTOS\s+ESENCIALES\s+ESPEC[ÍI]FICOS\s*$", re.IGNORECASE)),
    ("conocimientos_comunes", re.compile(r"^\s*5\.\s*CONOCIMIENTOS\s+ESENCIALES\s+COMUNES\s*$", re.IGNORECASE)),
    ("competencias", re.compile(r"^\s*6\.\s*COMPETENCIAS\s+COMPORTAMENTALES\s*$", re.IGNORECASE)),
    ("admitidos", re.compile(r"^\s*7\.\s*LISTA\s+DE\s+ADMITIDOS\s+Y\s+NO\s+ADMITIDOS", re.IGNORECASE)),
    ("pruebas", re.compile(r"^\s*8\.\s*PRUEBAS\s+PARA\s+APLICAR", re.IGNORECASE)),
    ("notas_generales", re.compile(r"^\s*9\.\s*NOTAS\s+GENERALES\s+DE\s+LA\s+CONVOCATORIA", re.IGNORECASE)),
]


def split_into_sections(full_text: str) -> dict[str, str]:
    """Divide el texto de una convocatoria en sus 9 secciones principales.

    Devuelve dict con clave=nombre_seccion y valor=texto entre headings.
    También incluye 'preambulo' con el texto antes de la primera sección.
    """
    lines = full_text.splitlines()
    section_starts: list[tuple[int, str]] = []  # (line_idx, section_key)
    for i, line in enumerate(lines):
        for key, pattern in SECTION_HEADINGS:
            if pattern.match(line):
                section_starts.append((i, key))
                break

    sections: dict[str, str] = {}
    if not section_starts:
        sections["preambulo"] = "\n".join(lines).strip()
        return sections

    sections["preambulo"] = "\n".join(lines[: section_starts[0][0]]).strip()
    for idx, (start_line, key) in enumerate(section_starts):
        end_line = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(lines)
        # +1 para no incluir la línea del título mismo
        sections[key] = "\n".join(lines[start_line + 1 : end_line]).strip()
    return sections


# ---------------------------------------------------------------------------
# Extracción de campos individuales
# ---------------------------------------------------------------------------

RE_FECHA_FIJACION = re.compile(r"Fecha\s+de\s+fijaci[óo]n\s*:\s*(.+)", re.IGNORECASE)
RE_VERSION_CONV = re.compile(r"Versi[óo]n\s+No\.?\s*(\d+)", re.IGNORECASE)
RE_TERMINO_INSCR = re.compile(
    r"T[ée]rmino\s+para\s+las\s+inscripciones\s*:\s*(.+?)(?=Medio\s+de\s+divulgaci[óo]n\s*:|1\.\s+IDENTIFICACI|$)",
    re.IGNORECASE | re.DOTALL,
)
RE_MEDIO_DIV = re.compile(
    r"Medio\s+de\s+divulgaci[óo]n\s*:\s*(.+?)(?=1\.\s+IDENTIFICACI|$)",
    re.IGNORECASE | re.DOTALL,
)


def parse_preambulo(preambulo: str) -> dict[str, str]:
    out: dict[str, str] = {}
    m = RE_VERSION_CONV.search(preambulo)
    if m:
        out["version_convocatoria"] = m.group(1).strip()
    m = RE_FECHA_FIJACION.search(preambulo)
    if m:
        # Tomar sólo hasta fin de línea
        line = m.group(1).splitlines()[0]
        out["fecha_fijacion"] = line.strip()
    m = RE_TERMINO_INSCR.search(preambulo)
    if m:
        out["termino_inscripciones"] = collapse_ws(m.group(1).replace("\n", " "))
    m = RE_MEDIO_DIV.search(preambulo)
    if m:
        out["medio_divulgacion"] = collapse_ws(m.group(1).replace("\n", " "))
    return out


# Identificación del empleo: layout con varias columnas. Buscamos cada etiqueta.
RE_DENOMINACION = re.compile(r"Denominaci[óo]n\s+del\s+empleo\s*:?", re.IGNORECASE)
RE_CODIGO_GRADO = re.compile(r"C[óo]digo\s+y\s+Grado\s*:?", re.IGNORECASE)
RE_NIVEL = re.compile(r"Nivel\s+jer[áa]rquico\s*:?", re.IGNORECASE)
RE_ASIGNACION = re.compile(r"Asignaci[óo]n\s+b[áa]sica\s*:?", re.IGNORECASE)
RE_UBICACION = re.compile(r"Ubicaci[óo]n\(es\)\s+inicial\(es\)\s+del\s+cargo\s*:?", re.IGNORECASE)
RE_NUM_CARGOS = re.compile(r"N[úu]mero\s+de\s+cargos\s*:?", re.IGNORECASE)
RE_DEPENDENCIA = re.compile(r"Dependencia\(s\)\s+inicial\(es\)\s*:?", re.IGNORECASE)


def _slice_by_columns(line: str, cols: list[tuple[str, int]]) -> dict[str, str]:
    """Divide ``line`` en sub-cadenas según las posiciones de inicio de cada columna.

    ``cols`` es una lista de tuplas (clave, posición_inicio) ordenada por posición.
    """
    cols_sorted = sorted(cols, key=lambda c: c[1])
    result: dict[str, str] = {}
    for i, (key, start) in enumerate(cols_sorted):
        end = cols_sorted[i + 1][1] if i + 1 < len(cols_sorted) else len(line)
        chunk = line[start:end] if start < len(line) else ""
        result[key] = chunk.strip()
    return result


# Mapa etiqueta -> regex usado para buscarla en una línea
LABEL_PATTERNS: dict[str, re.Pattern] = {
    "denominacion": re.compile(r"Denominaci[óo]n\s+del\s+empleo", re.IGNORECASE),
    "codigo_grado": re.compile(r"C[óo]digo\s+y\s+Grado", re.IGNORECASE),
    "nivel": re.compile(r"Nivel\s+jer[áa]rquico", re.IGNORECASE),
    "asignacion": re.compile(r"Asignaci[óo]n\s+b[áa]sica", re.IGNORECASE),
    "ubicacion": re.compile(r"Ubicaci[óo]n\(es\)\s+inicial\(es\)\s+del\s+cargo", re.IGNORECASE),
    "num_cargos": re.compile(r"N[úu]mero", re.IGNORECASE),  # parte de "Número de cargos:"
    "dependencia": re.compile(r"Dependencia\(s\)\s+inicial\(es\)", re.IGNORECASE),
}


def _find_label_columns(line: str, label_keys: list[str]) -> list[tuple[str, int]]:
    """En una línea con varias etiquetas, devuelve [(label_key, posición_x_inicio)]."""
    found: list[tuple[str, int]] = []
    for key in label_keys:
        pat = LABEL_PATTERNS[key]
        m = pat.search(line)
        if m:
            found.append((key, m.start()))
    return found


# ---------------------------------------------------------------------------
# Parser basado en extract_words con coordenadas reales
# ---------------------------------------------------------------------------

# Palabras del header institucional. Match case-sensitive porque el header usa
# todo en mayúsculas y el contenido usa minúsculas o capitalización Title.
HEADER_WORDS_RE = re.compile(
    r"^(?:PROCURADUR[IÍ]A|GENERAL|NACI[OÓ]N|COLOMB[IÍ]A|COLOMBI|LOMBI|LOMB|"
    r"FORMATO:|FORMATO|CONVOCATORIA|TALENTO|HUMANO|CO|A|"
    r"DE|LA|"
    r"Versi[óo]n|Fecha|C[óo]digo)$"
)
HEADER_ALWAYS_RE = re.compile(r"^(?:TH-F-\d+|PROCESO:)$")


def _is_header_word(text: str, top: float = 0.0, header_threshold: float = 70.0) -> bool:
    """¿Esta palabra es parte del header institucional?

    Si está en el área del header (top <= 70) usamos un filtro amplio.
    Fuera del área, sólo filtramos las palabras inequívocamente del header.
    """
    t = text.strip()
    if not t:
        return False
    if top <= header_threshold and HEADER_WORDS_RE.match(t):
        return True
    if HEADER_ALWAYS_RE.match(t):
        return True
    return False


def get_visual_rows(page, x_tol: float = 2.0, y_tol: float = 3.0) -> list[list[dict]]:
    """Devuelve las palabras de la página agrupadas por fila visual (mismo top).

    Cada elemento es una lista de words (dict con keys: text, x0, x1, top, bottom).
    Filtra las palabras del header institucional y los números de página del footer.
    """
    try:
        words = page.extract_words(x_tolerance=x_tol, y_tolerance=y_tol, keep_blank_chars=False)
    except Exception:
        return []

    page_height = float(page.height or 0)
    page_width = float(page.width or 0)
    # Header ocupa aproximadamente top 0..115 (4 líneas), footer desde altura-35
    header_top_max = 115.0
    footer_top_min = page_height - 35.0 if page_height else 9999

    filtered = []
    for w in words:
        text = w.get("text", "")
        top = float(w.get("top", 0))
        if _is_header_word(text, top=top, header_threshold=header_top_max):
            continue
        # Versión / Fecha / Código del formato (en el header)
        if top <= header_top_max and re.match(
            r"^(?:Versi[óo]n|Fecha|C[óo]digo|\d{1,2}/\d{1,2}/\d{4}|\d+)$", text, re.IGNORECASE
        ):
            continue
        # "23/02/2026" suele ser parte del header en cualquier posición visual del top
        if re.match(r"^\d{2}/\d{2}/2026$", text):
            continue
        # Número aislado en footer (número de página)
        if re.fullmatch(r"\d{1,3}", text):
            if top >= footer_top_min:
                continue
        filtered.append(w)

    # Agrupar por top similar
    filtered.sort(key=lambda w: (round(w["top"]), w["x0"]))
    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_top: float | None = None
    for w in filtered:
        if current_top is None or abs(w["top"] - current_top) <= y_tol:
            current_row.append(w)
            current_top = w["top"] if current_top is None else current_top
        else:
            rows.append(sorted(current_row, key=lambda x: x["x0"]))
            current_row = [w]
            current_top = w["top"]
    if current_row:
        rows.append(sorted(current_row, key=lambda x: x["x0"]))
    return rows


def split_row_into_cells(row: list[dict], gap_threshold: float = 8.0) -> list[dict]:
    """Divide una fila en celdas según gaps en X. Cada celda tiene {x0, x1, text}."""
    if not row:
        return []
    cells: list[list[dict]] = [[row[0]]]
    for w in row[1:]:
        prev = cells[-1][-1]
        gap = w["x0"] - prev["x1"]
        if gap > gap_threshold:
            cells.append([w])
        else:
            cells[-1].append(w)
    return [
        {
            "x0": c[0]["x0"],
            "x1": c[-1]["x1"],
            "text": " ".join(w["text"] for w in c).strip(),
        }
        for c in cells
    ]


def _find_label_xs_in_row(row: list[dict], label_first_words: dict[str, list[str]]) -> dict[str, float]:
    """Para cada etiqueta (clave -> primeras palabras posibles), busca su posición X
    como la x0 de la primera palabra que matchee. Esto evita problemas cuando una
    etiqueta como "Nivel jerárquico:" se separa en celdas.
    """
    out: dict[str, float] = {}
    for key, candidates in label_first_words.items():
        for w in row:
            text = w.get("text", "")
            for cand in candidates:
                if text.startswith(cand) or text.lower().startswith(cand.lower()):
                    out[key] = w["x0"]
                    break
            if key in out:
                break
    return out


def parse_identificacion_visual(
    page,
    subgrupo_state: list[str] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Parsea la sección IDENTIFICACIÓN DEL EMPLEO usando coordenadas reales.

    ``subgrupo_state`` es una lista mutable de 1 elemento que mantiene el subgrupo
    actual entre llamadas de página (para convocatorias multi-página).
    """
    rows = get_visual_rows(page)
    if not rows:
        return {}, []

    if subgrupo_state is None:
        subgrupo_state = [""]

    out: dict[str, object] = {}
    ubicaciones: list[dict[str, object]] = []

    # ----- Localizar fila de etiquetas (Denominación / Código / Nivel / Asignación) -----
    label_row1_idx: int | None = None
    label_row1_xs: dict[str, float] = {}
    for i, row in enumerate(rows):
        joined = " ".join(w["text"] for w in row)
        if RE_DENOMINACION.search(joined) and (RE_CODIGO_GRADO.search(joined) or RE_ASIGNACION.search(joined)):
            # Para cada etiqueta, encontrar la posición X de su PRIMERA palabra en el row.
            # "Asignaci" cubre casos atípicos donde el PDF parte la palabra "Asignación"
            # en dos líneas (e.g. "Asignaci" arriba y "ón" abajo).
            label_row1_xs = _find_label_xs_in_row(row, {
                "denominacion": ["Denominación", "Denominacion"],
                "codigo_grado": ["Código", "Codigo"],
                "nivel": ["Nivel"],
                "asignacion": ["Asignación", "Asignacion", "Asignaci"],
            })
            if len(label_row1_xs) >= 2:
                label_row1_idx = i
                break

    # Fallback: si no detectamos la X de la columna "asignacion" (p.ej. porque la
    # palabra "Asignación" se partió en dos líneas), buscar en filas siguientes la
    # primera palabra que comience con "$" y usar su x0 como inicio de columna.
    if label_row1_idx is not None and "asignacion" not in label_row1_xs:
        for j in range(label_row1_idx + 1, min(label_row1_idx + 6, len(rows))):
            for w in rows[j]:
                if w["text"].startswith("$"):
                    label_row1_xs["asignacion"] = w["x0"]
                    break
            if "asignacion" in label_row1_xs:
                break

    # ----- Localizar fila de etiquetas (Ubicación / Número / Dependencia) -----
    # Lo detectamos ANTES de procesar la sección 1 para usarlo como tope superior.
    label_row2_idx: int | None = None
    label_row2_xs: dict[str, float] = {}
    for i, row in enumerate(rows):
        joined = " ".join(w["text"] for w in row)
        if RE_UBICACION.search(joined) and (RE_DEPENDENCIA.search(joined) or "Número" in joined or "Numero" in joined):
            label_row2_xs = _find_label_xs_in_row(row, {
                "ubicacion": ["Ubicación", "Ubicacion"],
                "num_cargos": ["Número", "Numero"],
                "dependencia": ["Dependencia"],
            })
            if "ubicacion" in label_row2_xs and (
                "num_cargos" in label_row2_xs or "dependencia" in label_row2_xs
            ):
                label_row2_idx = i
                break

    # ----- Valores de las filas siguientes -----
    # Recolectamos las palabras de cada columna a lo largo de las filas que
    # están entre la fila de etiquetas (sec. 1) y la fila de etiquetas (sec. 2).
    # Esto evita mezclar palabras de la sección 2 (Ubicación/Número/Dependencia)
    # con la sección 1 cuando los datos quedan apilados en pocas filas.
    LABEL_CONTINUATION = {
        "jerárquico:", "jerarquico:", "básica:", "basica:", "Grado:", "del",
        "empleo:", "y", "Vigencia",
    }
    LABEL_TOKENS_SEC1 = {
        "Denominación", "Denominacion", "del", "empleo:", "Código", "Codigo", "y",
        "Grado:", "Nivel", "jerárquico:", "jerarquico:", "Asignación", "Asignacion",
        "Asignaci", "ón", "básica:", "basica:",
    }
    if label_row1_idx is not None and label_row1_xs:
        col_words: dict[str, list[dict]] = {
            "denominacion": [],
            "codigo_grado": [],
            "nivel": [],
            "asignacion": [],
        }
        # Tope superior: la siguiente fila de etiquetas (Ubicación/Número/Dependencia)
        # o, si no se detectó, label_row1_idx + 5.
        end_idx = label_row2_idx if label_row2_idx is not None else min(label_row1_idx + 5, len(rows))
        for j in range(label_row1_idx + 1, end_idx):
            row = rows[j]
            for w in row:
                key = _closest_label(w["x0"], label_row1_xs)
                if key in col_words:
                    col_words[key].append(w)

        # Para asignación, también incluimos la propia fila de etiquetas (los montos
        # a veces aparecen en la misma línea que "Asignación básica:", e.g. conv 38).
        for w in rows[label_row1_idx]:
            if w["text"] in LABEL_TOKENS_SEC1:
                continue
            key = _closest_label(w["x0"], label_row1_xs)
            if key == "asignacion":
                col_words["asignacion"].append(w)

        def _strip_label_cont(text: str) -> str:
            tokens = [t for t in text.split() if t not in LABEL_CONTINUATION and not (t.endswith(":") and t != ":")]
            return " ".join(tokens).strip()

        denom = _strip_label_cont(" ".join(w["text"] for w in col_words["denominacion"]))
        if denom:
            out["denominacion_empleo"] = denom

        cg = _strip_label_cont(" ".join(w["text"] for w in col_words["codigo_grado"]))
        if cg:
            out["codigo_grado"] = cg

        nivel = _strip_label_cont(" ".join(w["text"] for w in col_words["nivel"]))
        # Si "Asignación" se partió y el fragmento "ón" cayó en la columna nivel,
        # eliminar todo lo que sigue (incluyendo $XXX, "básica:", "Vigencia", etc.)
        nivel = re.sub(r"\s*\bón\b.*$", "", nivel).strip()
        nivel = re.sub(r"\s*\$.*$", "", nivel).strip()
        if nivel:
            out["nivel_jerarquico"] = nivel

        # Asignación básica: buscar el patrón $X.XXX.XXX en el texto de la columna.
        # Tolera espacios entre $ y los dígitos, y entre dígitos cuando el PDF parte
        # el monto en varias líneas (e.g. "$6.334.8 64" -> "$6.334.864").
        asig_text = " ".join(w["text"] for w in col_words["asignacion"])
        m_sal = re.search(r"\$\s*[\d][\d\.,]*(?:\s+\d+)*", asig_text)
        if m_sal:
            raw = m_sal.group(0)
            normalized = re.sub(r"\$\s+", "$", raw)
            normalized = re.sub(r"(\d)\s+(\d)", r"\1\2", normalized)
            out["asignacion_basica"] = normalized
        m_vig = re.search(r"Vigencia\s+(\d{4})", asig_text, re.IGNORECASE)
        if m_vig:
            out["vigencia_salario"] = m_vig.group(1)

    # ----- Procesar filas siguientes hasta sección 2 -----
    dep_lines: list[str] = []  # acumulamos para procesar Proceso al final

    if label_row2_idx is not None and label_row2_xs:
        for j in range(label_row2_idx + 1, len(rows)):
            row = rows[j]
            joined_text = " ".join(w["text"] for w in row)
            if re.search(r"\b2\.\s*REQUISITOS\b", joined_text, re.IGNORECASE):
                break

            # Asignar cada palabra a su columna por posición X
            col_words: dict[str, list[dict]] = {"ubicacion": [], "num_cargos": [], "dependencia": []}
            for w in row:
                key = _closest_label(w["x0"], label_row2_xs)
                if key in col_words:
                    col_words[key].append(w)

            # Re-armar el texto de la columna ubicación juntando palabras (sin reseparar)
            ubic_text = " ".join(w["text"] for w in col_words["ubicacion"]).strip()
            nc_text = " ".join(w["text"] for w in col_words["num_cargos"]).strip()
            dep_text = " ".join(w["text"] for w in col_words["dependencia"]).strip()

            if ubic_text:
                _process_ubicacion_text(ubic_text, ubicaciones, subgrupo_state)

            if "num_cargos" not in out:
                for token in nc_text.split():
                    if token.isdigit():
                        out["num_cargos"] = int(token)
                        break

            if dep_text:
                dep_lines.append(dep_text)
    else:
        # Página sin etiquetas: tratar como posible continuación de ubicaciones SOLO si
        # vínimos con un subgrupo activo. Frenar al primer indicio de cualquier otra
        # sección y validar que cada línea procesada parezca realmente una ciudad.
        SECTION_BOUNDARY = re.compile(
            r"\b(?:2\.\s*REQUISITOS|3\.\s*PROP[ÓO]SITO|4\.\s*CONOCIMIENTOS|"
            r"5\.\s*CONOCIMIENTOS|6\.\s*COMPETENCIAS|7\.\s*LISTA|8\.\s*PRUEBAS|"
            r"9\.\s*NOTAS|Estudio\s*:|Experiencia\s*:|Prop[óo]sito|Funciones|"
            r"Tipo\s+de\s+Prueba|CONVOCATORIA\s+No\.|Las\s+pruebas|"
            r"Conocimientos\s+Eliminatoria|sobre\s+cien|puntos\s+sobre)",
            re.IGNORECASE,
        )
        if subgrupo_state[0]:
            for row in rows:
                joined_text = " ".join(w["text"] for w in row).strip()
                if SECTION_BOUNDARY.search(joined_text):
                    break
                if not _looks_like_location_line(joined_text):
                    continue
                _process_ubicacion_text(joined_text, ubicaciones, subgrupo_state)

    # Consolidar dependencia y extraer Proceso
    if dep_lines:
        dep_full = " ".join(dep_lines)
        m_proc = re.search(r"Proceso\s*:\s*(.+?)$", dep_full, re.IGNORECASE)
        if m_proc:
            proc_val = m_proc.group(1).strip()
            # Quitar tokens basura al final (números de página, restos)
            proc_val = re.sub(r"\s+\d{1,3}\s*$", "", proc_val).strip()
            if "proceso" not in out and proc_val:
                out["proceso"] = proc_val
            dep_full = dep_full[: m_proc.start()].strip()
        # Limpieza: quitar palabras espurias de continuación de etiquetas
        dep_full = re.sub(r"\b(?:cargos:?)\b", "", dep_full, flags=re.IGNORECASE)
        dep_full = re.sub(r"\s{2,}", " ", dep_full).strip()
        if "dependencia_inicial" not in out:
            out["dependencia_inicial"] = dep_full
        else:
            out["dependencia_inicial"] = (str(out["dependencia_inicial"]) + " " + dep_full).strip()

    if "dependencia_inicial" in out:
        out["dependencia_inicial"] = collapse_ws(str(out["dependencia_inicial"]))

    return out, ubicaciones


def _closest_label(x: float, label_xs: dict[str, float]) -> str:
    """Devuelve la clave de la etiqueta cuya X es la mayor que aún sea <= x.

    Es decir, asigna ``x`` al "compartimiento" que comienza en la última etiqueta
    cuya posición no supera a x (con un pequeño margen para que valores ligeramente
    a la izquierda de la etiqueta sigan asignándose a esa).
    """
    items = sorted(label_xs.items(), key=lambda kv: kv[1])
    chosen = items[0][0]
    for key, x0 in items:
        if x >= x0 - 8.0:  # tolerancia: hasta 8pt antes del inicio de la etiqueta
            chosen = key
        else:
            break
    return chosen


def _looks_like_location_line(text: str) -> bool:
    """Heurística para validar que una línea es candidata a ser ciudad/subgrupo de
    ubicación, no parte de otro texto (ej. cuerpo de funciones).
    """
    if not text:
        return False
    # Debe contener un patrón "(<dígitos>)" donde dígitos < 1000 (cantidades de cargos)
    # y la cadena anterior debe ser corta (típicamente nombre de ciudad <= 35 chars).
    m = re.search(r"^\s*([^()]{1,40}?)\s*\(\s*(\d{1,3})\s*\)\s*$", text)
    if m:
        return True
    # Múltiples ciudades en línea (ej: "Cali (4)  Pereira (2)")
    matches = list(re.finditer(r"([^()]+?)\s*\((\d{1,3})\)", text))
    if matches:
        # Cada match debe tener prefijo corto
        for mm in matches:
            prefix = mm.group(1).strip()
            if len(prefix) > 40 or any(k in prefix.lower() for k in (
                "puntos", "sobre", "cien", "horas", "días", "calendario", "minutos",
                "elimina", "clasifica", "punto", "edad", "años", "doce", "decreto",
                "artículo", "ley", "resolución",
            )):
                return False
        return True
    # Línea sin paréntesis: puede ser subgrupo si es corta
    if len(text) <= 60 and not any(k in text.lower() for k in (
        "puntos", "sobre cien", "horas", "días calendario", "decreto", "artículo",
        "ley ", "resolución", "eliminatoria", "clasificatoria",
    )):
        return True
    return False


def _process_ubicacion_text(text: str, ubicaciones: list[dict[str, object]], state: list) -> None:
    """Procesa el texto de la columna ubicación de una fila visual.

    ``state`` es una lista mutable: state[0] = subgrupo actual.
    Se añade dinámicamente state[1] = bool indicando si ya se asignó al menos una
    ciudad al subgrupo actual (para distinguir continuación vs nuevo subgrupo).
    """
    text = text.strip().strip(",")
    if not text:
        return
    lower_clean = text.lower().rstrip(".:,")
    if lower_clean in NOISE_LINES:
        return

    # Inicializar flag de "ciudades asignadas a este subgrupo"
    if len(state) < 2:
        state.append(False)

    matches = list(re.finditer(r"([^()]+?)\s*\((\d+)\)", text))
    if matches:
        # Si hay texto antes del primer match, es un subgrupo nuevo
        first_start = matches[0].start()
        if first_start > 0:
            prefix = text[:first_start].strip().rstrip(",.:")
            prefix = _clean_subgrupo(prefix)
            if prefix and prefix.lower() not in NOISE_LINES:
                state[0] = prefix
                state[1] = False
        for m in matches:
            ciudad = m.group(1).strip().rstrip("-").strip(",").strip()
            cantidad = int(m.group(2))
            ciudad_lower = ciudad.lower()
            if not ciudad or ciudad_lower in NOISE_LINES:
                continue
            # "PLANTA GLOBAL (X)", "PLANTA FIJA (X)" representan agregados,
            # no ciudades. Convertirlos en cambio de subgrupo y no agregar fila.
            if re.match(r"^planta\s+(?:global|fija|temporal)$", ciudad_lower):
                state[0] = ciudad.upper()
                state[1] = False
                continue
            ubicaciones.append(
                {"subgrupo": state[0].strip(), "ciudad": ciudad, "cantidad_ciudad": cantidad}
            )
            state[1] = True
        return

    # No es una ciudad: es subgrupo (o continuación de subgrupo)
    cleaned = _clean_subgrupo(text)
    if not cleaned:
        return

    # Continuación: solo concatenar si no hemos asignado todavía ninguna ciudad al
    # subgrupo y el texto se ve como una palabra/frase corta de continuación.
    can_concat = (
        state[0]
        and not state[1]  # aún no se ha asignado ciudad
        and len(state[0]) < 90
        and len(cleaned) < 50
        and not cleaned.startswith(GROUP_PREFIXES)
    )
    if can_concat:
        state[0] = f"{state[0]} {cleaned}".strip()
    else:
        state[0] = cleaned
        state[1] = False


_SUBGRUPO_TOKEN_NOISE = re.compile(
    r"^(?:PROCURADUR[IÍ]A|COLOMBI?A?|LOMBI|LOMB|FORMATO:?|TALENTO|HUMANO|"
    r"PROCESO:?|CONVOCATORIA|TH-F-\d+|CO|A|DE|LA|GENERAL|NACI[OÓ]N|"
    r"Versi[óo]n|Fecha|C[óo]digo|\d{2}/\d{2}/\d{4})$"
)


def _clean_subgrupo(text: str) -> str:
    """Limpia un texto candidato a subgrupo, quitando palabras espurias del header."""
    if not text:
        return ""
    tokens = text.split()
    out: list[str] = []
    for t in tokens:
        if _SUBGRUPO_TOKEN_NOISE.match(t):
            continue
        out.append(t)
    cleaned = " ".join(out).strip()
    # Descartar si solo quedan números o palabras muy cortas
    if not cleaned or re.fullmatch(r"[\d\s\-]+", cleaned):
        return ""
    return cleaned


# ---------------------------------------------------------------------------
# Parser legacy (texto layout) - mantenido como fallback
# ---------------------------------------------------------------------------


def parse_identificacion(text: str) -> dict[str, object]:
    """Parsea la sección 1. IDENTIFICACIÓN DEL EMPLEO usando posiciones de columnas.

    El texto debe venir extraído con ``layout=True`` para que las posiciones X
    estén alineadas. La estrategia: identificar la línea con varias etiquetas y
    usar sus posiciones para cortar las líneas de valores siguientes en columnas.
    """
    out: dict[str, object] = {}
    lines = text.splitlines()

    # ----- FILA 1: Denominación / Código / Nivel / Asignación -----
    header1_idx: int | None = None
    cols1: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if RE_DENOMINACION.search(line) and (RE_CODIGO_GRADO.search(line) or RE_NIVEL.search(line)):
            cols1 = _find_label_columns(line, ["denominacion", "codigo_grado", "nivel", "asignacion"])
            if len(cols1) >= 2:
                header1_idx = i
                break

    if header1_idx is not None:
        # Buscar siguiente línea no vacía con valores
        for j in range(header1_idx + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                continue
            sliced = _slice_by_columns(line, cols1)
            denom = sliced.get("denominacion", "").strip()
            cg = sliced.get("codigo_grado", "").strip()
            nivel = sliced.get("nivel", "").strip()
            asig = sliced.get("asignacion", "").strip()
            if denom:
                out["denominacion_empleo"] = denom
            if cg:
                out["codigo_grado"] = cg
            if nivel:
                out["nivel_jerarquico"] = nivel
            # asignación puede estar en línea siguiente; tomar la primera con $
            if "$" in asig:
                out["asignacion_basica"] = asig.split()[0]
            break

    # ----- Fallbacks por regex global para asignación / vigencia -----
    compact = collapse_ws(text)
    if "asignacion_basica" not in out:
        m = re.search(r"\$[\d\.,]+", compact)
        if m:
            out["asignacion_basica"] = m.group(0)
    m_vig = re.search(r"Vigencia\s+(\d{4})", compact, re.IGNORECASE)
    if m_vig:
        out["vigencia_salario"] = m_vig.group(1)

    # ----- FILA 2: Ubicación / Número de cargos / Dependencia -----
    header2_idx: int | None = None
    cols2: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if RE_UBICACION.search(line) and (RE_DEPENDENCIA.search(line) or "Número" in line):
            cols2 = _find_label_columns(line, ["ubicacion", "num_cargos", "dependencia"])
            if cols2:
                header2_idx = i
                break

    dep_lines: list[str] = []
    num_cargos_lines: list[str] = []
    ubic_lines: list[str] = []  # serán reusadas en parse_ubicaciones_v2

    if header2_idx is not None and cols2:
        ubicacion_x = cols2[0][1]  # X inicial de la columna ubicación
        for j in range(header2_idx + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                continue
            stripped = line.strip()
            if re.match(r"^\s*2\.\s*REQUISITOS", stripped, re.IGNORECASE):
                break

            sliced = _slice_by_columns(line, cols2)
            ubic = sliced.get("ubicacion", "")
            nc = sliced.get("num_cargos", "")
            dep = sliced.get("dependencia", "")

            # Si la línea sólo tiene contenido en la columna izquierda (subgrupo largo
            # que se desborda sobre las siguientes columnas vacías), reagruparla.
            if ubic.strip() and not nc.strip() and not dep.strip():
                ubic_lines.append(line[ubicacion_x:].rstrip())
                num_cargos_lines.append("")
                dep_lines.append("")
            else:
                ubic_lines.append(ubic)
                num_cargos_lines.append(nc)
                dep_lines.append(dep)

    # Número total de cargos: primer número entero en la columna num_cargos
    for chunk in num_cargos_lines:
        for token in chunk.split():
            if token.isdigit():
                out["num_cargos"] = int(token)
                break
        if "num_cargos" in out:
            break

    # Dependencia(s) inicial(es) y Proceso (van en la última columna)
    # Limpiamos línea por línea descartando palabras espurias "de", "cargos:", etc.
    dep_clean_lines: list[str] = []
    for chunk in dep_lines:
        s = chunk.strip()
        if not s:
            continue
        if re.match(r"^(?:de|cargos:?|N[úu]mero)\s*$", s, re.IGNORECASE):
            continue
        s = re.sub(r"^\s*(?:de|cargos:?)\s+", "", s, flags=re.IGNORECASE)
        dep_clean_lines.append(s)
    dep_text = "\n".join(dep_clean_lines)

    if dep_text:
        m_proc = re.search(r"Proceso\s*:\s*([^\n]+)", dep_text, re.IGNORECASE)
        if m_proc:
            out["proceso"] = m_proc.group(1).strip()
            dep_text = (dep_text[: m_proc.start()] + dep_text[m_proc.end():]).strip()
        out["dependencia_inicial"] = collapse_ws(dep_text).strip()

    # Guardamos las líneas de ubicación pre-cortadas para que parse_ubicaciones las use
    out["_ubicacion_lines"] = ubic_lines  # interno, no se exporta como campo final

    return out


# ---------------------------------------------------------------------------
# Parsing de UBICACIONES (lo más importante para el desglose por ciudad)
# ---------------------------------------------------------------------------

# Una "ciudad" es algo que termina con (número). Las líneas que NO terminan así
# suelen ser sub-grupos / categorías (ej: "Procuradurías Provinciales de Juzgamiento").
RE_CIUDAD = re.compile(r"^(.+?)\s*[\-–]?\s*\((\d+)\)\s*$")
RE_CIUDAD_SIN_PAREN = re.compile(r"^(.+?)\s+(\d+)\s*$")  # fallback (raro)


# Frases que nunca son ciudad. Algunas (PLANTA GLOBAL) sí son subgrupos válidos.
NOISE_LINES = {
    "o donde se ubique el cargo",
    "o donde se ubique el cargo.",
    "procuraduria",
    "procuraduría",
    "general de la nacion",
    "general de la nación",
    "colombia",
    "duria",
    "duría",
}

# Texto que indica continuación del grupo previo (sub-categoría)
GROUP_PREFIXES = ("Procuradur", "Despacho", "Oficina", "Direcci", "Secretar", "Instituto", "Centro", "PLANTA")


def parse_ubicaciones(ubic_lines: list[str]) -> list[dict[str, object]]:
    """Recibe las líneas YA pre-cortadas a la columna de ubicaciones y devuelve la lista
    de [{subgrupo, ciudad, cantidad_ciudad}].
    """
    locations: list[dict[str, object]] = []
    current_group = ""

    for raw in ubic_lines:
        chunk = raw.strip()
        if not chunk:
            continue

        # Algunas líneas traen varios elementos pegados por dobles espacios; los procesamos
        # como sub-tokens cuando todos parecen ser ciudades.
        sub_items = [s.strip() for s in re.split(r"\s{2,}", chunk) if s.strip()]
        for first_col in sub_items:
            lower = first_col.lower().rstrip(".:,")
            if lower in NOISE_LINES:
                continue
            # Las etiquetas que aún se pueden colar
            if re.match(r"^(de|cargos:?|N[úu]mero)$", first_col, re.IGNORECASE):
                continue

            m = RE_CIUDAD.match(first_col)
            if m:
                ciudad = m.group(1).strip().rstrip("-").strip()
                if not ciudad:
                    continue
                cantidad = int(m.group(2))
                locations.append(
                    {
                        "subgrupo": current_group.strip(),
                        "ciudad": ciudad,
                        "cantidad_ciudad": cantidad,
                    }
                )
            else:
                # Subgrupo (categoría). Heurística: si parece continuación del grupo previo,
                # concatenamos (ej: "Procuradurías Provinciales de" + "Juzgamiento").
                if (
                    current_group
                    and not first_col.startswith(GROUP_PREFIXES)
                    and len(current_group) < 90
                    and len(first_col) < 50
                ):
                    current_group = f"{current_group} {first_col}".strip()
                else:
                    current_group = first_col

    return locations


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------


@dataclass
class ConvocatoriaRecord:
    numero: int = 0
    pagina_inicio: int = 0
    pagina_fin: int = 0
    version_convocatoria: str = ""
    fecha_fijacion: str = ""
    termino_inscripciones: str = ""
    medio_divulgacion: str = ""
    denominacion_empleo: str = ""
    codigo_grado: str = ""
    nivel_jerarquico: str = ""
    asignacion_basica: str = ""
    vigencia_salario: str = ""
    num_cargos: int | None = None
    dependencia_inicial: str = ""
    proceso: str = ""
    estudio: str = ""
    experiencia: str = ""
    equivalencias: str = ""
    proposito: str = ""
    funciones: str = ""
    conocimientos_especificos: str = ""
    conocimientos_comunes: str = ""
    competencias_comportamentales: str = ""
    lista_admitidos_reclamaciones: str = ""
    pruebas: str = ""
    notas_generales: str = ""
    ubicaciones_raw: str = ""
    ubicaciones: list[dict[str, object]] = field(default_factory=list)


def parse_requisitos(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    compact = collapse_ws(text)
    m = re.search(
        r"Estudio\s*:\s*(.+?)(?=Experiencia\s*:|Equivalencias\s+entre|$)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["estudio"] = collapse_ws(m.group(1)).strip()
    m = re.search(
        r"Experiencia\s*:\s*(.+?)(?=Equivalencias\s+entre|Los\s+documentos|$)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["experiencia"] = collapse_ws(m.group(1)).strip()
    m = re.search(
        r"Equivalencias\s+entre\s+estudios\s+y\s+experiencia\s*:?\s*(.+?)(?=Los\s+documentos|3\.\s*PROP|$)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["equivalencias"] = collapse_ws(m.group(1)).strip()
    return out


def parse_proposito_funciones(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    compact = text
    # Propósito: bloque entre la etiqueta "Propósito" y "Funciones"
    m = re.search(
        r"Prop[óo]sito\s*\n+(.+?)(?=\n\s*Funciones\b|\Z)",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["proposito"] = collapse_ws(m.group(1).replace("\n", " ")).strip()
    m = re.search(
        r"Funciones\s*\n+(.+)\Z",
        compact,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["funciones"] = collapse_ws(m.group(1)).strip()
    else:
        # fallback: todo el texto
        out["funciones"] = collapse_ws(text).strip()
    return out


def parse_convocatoria_text(
    numero: int,
    span: ConvocatoriaSpan,
    full_text: str,
    pdf=None,
) -> ConvocatoriaRecord:
    sections = split_into_sections(full_text)
    rec = ConvocatoriaRecord(numero=numero, pagina_inicio=span.pagina_inicio, pagina_fin=span.pagina_fin)

    if "preambulo" in sections:
        for k, v in parse_preambulo(sections["preambulo"]).items():
            setattr(rec, k, v)

    ident = sections.get("identificacion", "")
    rec.ubicaciones_raw = ident

    used_visual = False
    if pdf is not None:
        ident_data: dict[str, object] = {}
        ubicaciones: list[dict[str, object]] = []
        subgrupo_state = [""]
        for p in range(span.pagina_inicio, span.pagina_fin + 1):
            page = pdf.pages[p - 1]
            d, ubics = parse_identificacion_visual(page, subgrupo_state=subgrupo_state)
            for k, v in d.items():
                if k not in ident_data and v not in (None, ""):
                    ident_data[k] = v
            ubicaciones.extend(ubics)
            txt = page.extract_text() or ""
            if re.search(r"\b2\.\s*REQUISITOS\s+M[ÍI]NIMOS", txt, re.IGNORECASE):
                break
        if ident_data or ubicaciones:
            for k, v in ident_data.items():
                setattr(rec, k, v)
            # Deduplicar ubicaciones idénticas (algunas convs repiten etiquetas en
            # cada página y reextraen las mismas ciudades varias veces).
            seen: set[tuple[str, str, int]] = set()
            deduped: list[dict[str, object]] = []
            for u in ubicaciones:
                key = (
                    str(u.get("subgrupo", "")),
                    str(u.get("ciudad", "")),
                    int(u.get("cantidad_ciudad", 0) or 0),
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(u)
            rec.ubicaciones = deduped
            used_visual = True

    if not used_visual and ident:
        ident_data = parse_identificacion(ident)
        ubic_lines = ident_data.pop("_ubicacion_lines", [])
        for k, v in ident_data.items():
            setattr(rec, k, v)
        rec.ubicaciones = parse_ubicaciones(ubic_lines)

    # Fallback final para asignacion_basica: si tras procesar todas las páginas
    # aún está vacía, hacer una búsqueda regex sobre el texto completo de la
    # convocatoria. Cubre PDFs muy mal formateados donde la sección
    # IDENTIFICACIÓN tiene texto roto (palabras con letras separadas por espacios).
    if not rec.asignacion_basica and pdf is not None:
        try:
            for p in range(span.pagina_inicio, span.pagina_fin + 1):
                page_text = pdf.pages[p - 1].extract_text() or ""
                m = re.search(r"\$\s*[\d][\d\.,]{6,}", page_text)
                if m:
                    rec.asignacion_basica = re.sub(r"\$\s+", "$", m.group(0)).strip(",.")
                    break
        except Exception:
            pass

    if "requisitos" in sections:
        for k, v in parse_requisitos(sections["requisitos"]).items():
            setattr(rec, k, v)

    if "proposito_funciones" in sections:
        for k, v in parse_proposito_funciones(sections["proposito_funciones"]).items():
            setattr(rec, k, v)

    rec.conocimientos_especificos = collapse_ws(sections.get("conocimientos_especificos", ""))
    rec.conocimientos_comunes = collapse_ws(sections.get("conocimientos_comunes", ""))
    rec.competencias_comportamentales = collapse_ws(sections.get("competencias", ""))
    rec.lista_admitidos_reclamaciones = collapse_ws(sections.get("admitidos", ""))
    rec.pruebas = collapse_ws(sections.get("pruebas", ""))
    rec.notas_generales = collapse_ws(sections.get("notas_generales", ""))
    return rec


def extract_text_for_span(pdf, span: ConvocatoriaSpan) -> str:
    """Extrae texto en modo layout para todas las páginas de una convocatoria y limpia headers."""
    parts: list[str] = []
    for p in range(span.pagina_inicio, span.pagina_fin + 1):
        page = pdf.pages[p - 1]
        try:
            txt = page.extract_text(layout=True, x_density=6, y_density=10) or ""
        except Exception:
            txt = page.extract_text() or ""
        parts.append(strip_headers_footers(txt))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Exportación a CSV / XLSX
# ---------------------------------------------------------------------------

COLUMN_ORDER_DETALLE = [
    "numero_convocatoria",
    "version_convocatoria",
    "fecha_fijacion",
    "denominacion_empleo",
    "codigo_grado",
    "nivel_jerarquico",
    "asignacion_basica",
    "vigencia_salario",
    "num_cargos_total",
    "subgrupo_ubicacion",
    "ciudad",
    "cantidad_cargos_ciudad",
    "dependencia_inicial",
    "proceso",
    "estudio",
    "experiencia",
    "equivalencias",
    "proposito",
    "funciones",
    "conocimientos_especificos",
    "conocimientos_comunes",
    "competencias_comportamentales",
    "lista_admitidos_reclamaciones",
    "pruebas",
    "notas_generales",
    "termino_inscripciones",
    "medio_divulgacion",
    "pagina_inicio",
    "pagina_fin",
]


def record_to_city_rows(rec: ConvocatoriaRecord) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    common = {
        "numero_convocatoria": rec.numero,
        "version_convocatoria": rec.version_convocatoria,
        "fecha_fijacion": rec.fecha_fijacion,
        "denominacion_empleo": rec.denominacion_empleo,
        "codigo_grado": rec.codigo_grado,
        "nivel_jerarquico": rec.nivel_jerarquico,
        "asignacion_basica": rec.asignacion_basica,
        "vigencia_salario": rec.vigencia_salario,
        "num_cargos_total": rec.num_cargos,
        "dependencia_inicial": rec.dependencia_inicial,
        "proceso": rec.proceso,
        "estudio": rec.estudio,
        "experiencia": rec.experiencia,
        "equivalencias": rec.equivalencias,
        "proposito": rec.proposito,
        "funciones": rec.funciones,
        "conocimientos_especificos": rec.conocimientos_especificos,
        "conocimientos_comunes": rec.conocimientos_comunes,
        "competencias_comportamentales": rec.competencias_comportamentales,
        "lista_admitidos_reclamaciones": rec.lista_admitidos_reclamaciones,
        "pruebas": rec.pruebas,
        "notas_generales": rec.notas_generales,
        "termino_inscripciones": rec.termino_inscripciones,
        "medio_divulgacion": rec.medio_divulgacion,
        "pagina_inicio": rec.pagina_inicio,
        "pagina_fin": rec.pagina_fin,
    }
    if not rec.ubicaciones:
        rows.append({**common, "subgrupo_ubicacion": "", "ciudad": "", "cantidad_cargos_ciudad": None})
    else:
        for u in rec.ubicaciones:
            rows.append(
                {
                    **common,
                    "subgrupo_ubicacion": u.get("subgrupo", ""),
                    "ciudad": u.get("ciudad", ""),
                    "cantidad_cargos_ciudad": u.get("cantidad_ciudad"),
                }
            )
    return rows


def record_to_summary_row(rec: ConvocatoriaRecord) -> dict[str, object]:
    ubicaciones_resumen = "; ".join(
        f"{u.get('subgrupo','')} > {u.get('ciudad','')} ({u.get('cantidad_ciudad', '')})"
        for u in rec.ubicaciones
    )
    return {
        "numero_convocatoria": rec.numero,
        "version_convocatoria": rec.version_convocatoria,
        "fecha_fijacion": rec.fecha_fijacion,
        "denominacion_empleo": rec.denominacion_empleo,
        "codigo_grado": rec.codigo_grado,
        "nivel_jerarquico": rec.nivel_jerarquico,
        "asignacion_basica": rec.asignacion_basica,
        "vigencia_salario": rec.vigencia_salario,
        "num_cargos_total": rec.num_cargos,
        "num_ciudades": len(rec.ubicaciones),
        "dependencia_inicial": rec.dependencia_inicial,
        "proceso": rec.proceso,
        "ubicaciones_resumen": ubicaciones_resumen,
        "estudio": rec.estudio,
        "experiencia": rec.experiencia,
        "equivalencias": rec.equivalencias,
        "proposito": rec.proposito,
        "funciones": rec.funciones,
        "conocimientos_especificos": rec.conocimientos_especificos,
        "conocimientos_comunes": rec.conocimientos_comunes,
        "competencias_comportamentales": rec.competencias_comportamentales,
        "lista_admitidos_reclamaciones": rec.lista_admitidos_reclamaciones,
        "pruebas": rec.pruebas,
        "notas_generales": rec.notas_generales,
        "termino_inscripciones": rec.termino_inscripciones,
        "medio_divulgacion": rec.medio_divulgacion,
        "pagina_inicio": rec.pagina_inicio,
        "pagina_fin": rec.pagina_fin,
    }


def write_outputs(records: list[ConvocatoriaRecord], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    detalle_rows: list[dict[str, object]] = []
    for r in records:
        detalle_rows.extend(record_to_city_rows(r))

    df_detalle = pd.DataFrame(detalle_rows, columns=COLUMN_ORDER_DETALLE)
    detalle_csv = out_dir / "convocatorias_por_ciudad.csv"
    detalle_xlsx = out_dir / "convocatorias_por_ciudad.xlsx"
    df_detalle.to_csv(detalle_csv, index=False, encoding="utf-8-sig")
    df_detalle.to_excel(detalle_xlsx, index=False)
    print(f"  -> {detalle_csv}  ({len(df_detalle)} filas)")
    print(f"  -> {detalle_xlsx}")

    resumen_rows = [record_to_summary_row(r) for r in records]
    df_resumen = pd.DataFrame(resumen_rows)
    resumen_csv = out_dir / "convocatorias_resumen.csv"
    resumen_xlsx = out_dir / "convocatorias_resumen.xlsx"
    df_resumen.to_csv(resumen_csv, index=False, encoding="utf-8-sig")
    df_resumen.to_excel(resumen_xlsx, index=False)
    print(f"  -> {resumen_csv}  ({len(df_resumen)} filas)")
    print(f"  -> {resumen_xlsx}")

    # JSON crudo opcional para depuración o uso por el visualizador
    raw = [
        {
            **{k: v for k, v in asdict(r).items() if k != "ubicaciones"},
            "ubicaciones": r.ubicaciones,
        }
        for r in records
    ]
    raw_json = out_dir / "convocatorias_raw.json"
    raw_json.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {raw_json}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="Ruta al PDF de convocatorias.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Carpeta de salida.")
    parser.add_argument(
        "--max-convocatorias",
        type=int,
        default=None,
        help="Procesar solo las primeras N convocatorias (útil para pruebas).",
    )
    parser.add_argument(
        "--skip-spans",
        action="store_true",
        help="Mostrar páginas detectadas y salir sin parsear.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    pdf_path = Path(args.pdf)
    out_dir = Path(args.out)

    if not pdf_path.exists():
        print(f"ERROR: no existe el PDF {pdf_path}", file=sys.stderr)
        return 1

    print(f"Leyendo PDF: {pdf_path}")
    t0 = time.time()
    cache_path = out_dir / ".spans_cache.json"
    spans = find_convocatoria_spans(pdf_path, cache_path=cache_path)
    print(f"Detectadas {len(spans)} convocatorias en {time.time() - t0:.1f}s")

    if args.max_convocatorias:
        spans = spans[: args.max_convocatorias]
        print(f"Limitando a las primeras {len(spans)} para esta corrida.")

    if args.skip_spans:
        for s in spans[:20]:
            print(f"  conv {s.numero:>3}: páginas {s.pagina_inicio}-{s.pagina_fin}")
        return 0

    records: list[ConvocatoriaRecord] = []
    t1 = time.time()
    with pdfplumber.open(pdf_path) as pdf:
        for idx, span in enumerate(spans, start=1):
            full_text = extract_text_for_span(pdf, span)
            rec = parse_convocatoria_text(span.numero, span, full_text, pdf=pdf)
            records.append(rec)
            if idx % 10 == 0 or idx == len(spans):
                elapsed = time.time() - t1
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (len(spans) - idx) / rate if rate > 0 else 0
                print(
                    f"  [{idx}/{len(spans)}] conv {span.numero}  pp{span.pagina_inicio}-{span.pagina_fin}"
                    f"  | {rate:.1f} conv/s  ETA {eta:.0f}s"
                )

    print(f"\nParseo completo en {time.time() - t1:.1f}s. Escribiendo salidas...")
    write_outputs(records, out_dir)
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

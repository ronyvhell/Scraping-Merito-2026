"""Genera un visualizador HTML estático con DataTables para explorar el CSV.

El HTML resultante (visualizador.html) carga los datos desde
``csv/convocatorias_por_ciudad.csv`` (vía fetch local) o, si los datos se
embeben con ``--embed``, los incluye directamente en el HTML para abrirlo
sin servidor.

Uso:
    python scripts/build_viewer.py            # genera visualizador.html con datos embebidos
    python scripts/build_viewer.py --no-embed # carga el CSV en runtime (requiere servidor)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_CSV = Path("csv") / "convocatorias_por_ciudad.csv"
DEFAULT_OUT = Path("visualizador.html")

# Columnas a mostrar y sus etiquetas. Orden = orden de columnas en la tabla.
COLUMNS = [
    ("numero_convocatoria", "Conv. N°"),
    ("denominacion_empleo", "Denominación"),
    ("codigo_grado", "Código y Grado"),
    ("nivel_jerarquico", "Nivel"),
    ("asignacion_basica", "Salario"),
    ("vigencia_salario", "Vigencia"),
    ("num_cargos_total", "Total cargos"),
    ("subgrupo_ubicacion", "Subgrupo / Sede"),
    ("ciudad", "Ciudad"),
    ("cantidad_cargos_ciudad", "Cargos ciudad"),
    ("dependencia_inicial", "Dependencia"),
    ("proceso", "Proceso"),
    ("estudio", "Estudios"),
    ("experiencia", "Experiencia"),
    ("equivalencias", "Equivalencias"),
    ("proposito", "Propósito"),
    ("funciones", "Funciones"),
    ("conocimientos_especificos", "Conocimientos específicos"),
    ("conocimientos_comunes", "Conocimientos comunes"),
    ("competencias_comportamentales", "Competencias"),
    ("lista_admitidos_reclamaciones", "Lista admitidos"),
    ("pruebas", "Pruebas"),
    ("notas_generales", "Notas generales"),
    ("fecha_fijacion", "Fecha fijación"),
    ("termino_inscripciones", "Inscripciones"),
    ("medio_divulgacion", "Medio divulgación"),
    ("pagina_inicio", "Pág. inicio"),
    ("pagina_fin", "Pág. fin"),
]

# Columnas largas que conviene truncar en la vista (pero conservar en detalle)
LONG_COLUMNS = {
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
    "dependencia_inicial",
}


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Convocatorias - Concurso de Méritos PGN 2026</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://cdn.datatables.net/2.1.8/css/dataTables.dataTables.min.css">
<link rel="stylesheet" href="https://cdn.datatables.net/buttons/3.2.0/css/buttons.dataTables.min.css">
<link rel="stylesheet" href="https://cdn.datatables.net/searchbuilder/1.8.1/css/searchBuilder.dataTables.min.css">
<style>
  :root {
    --bg: #f5f7fb;
    --card: #fff;
    --primary: #1e3a8a;
    --primary-light: #3b82f6;
    --text: #1f2937;
    --muted: #6b7280;
    --border: #e5e7eb;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
  }
  header {
    background: linear-gradient(135deg, var(--primary), var(--primary-light));
    color: #fff;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
  }
  header h1 { margin: 0 0 0.25rem 0; font-size: 1.25rem; font-weight: 600; }
  header .sub { font-size: 0.85rem; opacity: 0.9; }
  .summary {
    display: flex;
    gap: 1rem;
    padding: 1rem 1.5rem;
    flex-wrap: wrap;
    background: var(--card);
    border-bottom: 1px solid var(--border);
  }
  .summary .stat {
    flex: 1 1 180px;
    background: #fafbff;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }
  .summary .stat .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .summary .stat .value { font-size: 1.4rem; font-weight: 600; color: var(--primary); margin-top: 0.25rem; }
  .container { padding: 1rem 1.5rem 4rem; }
  .filters {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.75rem;
  }
  .filters label { display: block; font-size: 0.75rem; color: var(--muted); margin-bottom: 0.25rem; font-weight: 500; }
  .filters select, .filters input {
    width: 100%;
    padding: 0.45rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.85rem;
    background: #fff;
  }
  .table-wrap {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
    overflow: auto;
  }
  table.dataTable thead th {
    background: #f3f4f6;
    color: var(--text);
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  table.dataTable tbody td {
    font-size: 0.82rem;
    vertical-align: top;
  }
  td.truncate { max-width: 320px; }
  td.truncate .full { display: none; }
  td.truncate .preview { display: inline; }
  td.truncate.expanded .full { display: inline; white-space: pre-wrap; }
  td.truncate.expanded .preview { display: none; }
  td.truncate .toggle {
    color: var(--primary-light);
    cursor: pointer;
    font-size: 0.75rem;
    margin-left: 0.25rem;
    text-decoration: underline;
  }
  .badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    background: #eef2ff;
    color: var(--primary);
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .clear-btn {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    cursor: pointer;
    align-self: end;
  }
  .clear-btn:hover { background: #f3f4f6; }
  details.row-detail summary { cursor: pointer; color: var(--primary-light); }
  /* Footer */
  footer.site-footer {
    margin-top: 3rem;
    padding: 1.25rem 1.5rem;
    border-top: 1px solid var(--border);
    background: var(--card);
    text-align: center;
    color: var(--muted);
    font-size: 0.85rem;
  }
  footer.site-footer a {
    color: var(--primary);
    text-decoration: none;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  footer.site-footer a:hover { text-decoration: underline; }
  footer.site-footer svg { vertical-align: middle; }
  /* Modal */
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: none; align-items: center; justify-content: center; z-index: 100;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: #fff; border-radius: 8px; max-width: 900px; width: 90%;
    max-height: 85vh; overflow-y: auto; padding: 1.5rem;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  }
  .modal h2 { margin-top: 0; color: var(--primary); }
  .modal .field { margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border); }
  .modal .field:last-child { border-bottom: none; }
  .modal .field-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.25rem; }
  .modal .field-value { white-space: pre-wrap; word-break: break-word; }
  .modal .close-btn {
    float: right; background: transparent; border: none; font-size: 1.5rem;
    cursor: pointer; color: var(--muted);
  }
</style>
</head>
<body>
<header>
  <h1>Convocatorias - Concurso de Méritos Procuraduría General de la Nación 2026</h1>
  <div class="sub">Visualizador de datos extraídos de la Resolución 108 del 23 de abril de 2026 (Versión 2)</div>
</header>

<section class="summary">
  <div class="stat"><div class="label">Convocatorias</div><div class="value" id="stat-conv">—</div></div>
  <div class="stat"><div class="label">Filas (sedes)</div><div class="value" id="stat-rows">—</div></div>
  <div class="stat"><div class="label">Total de cargos</div><div class="value" id="stat-cargos">—</div></div>
  <div class="stat"><div class="label">Ciudades distintas</div><div class="value" id="stat-ciudades">—</div></div>
</section>

<div class="container">
  <div class="filters">
    <div>
      <label>Convocatoria N°</label>
      <select id="filter-numero"><option value="">— todas —</option></select>
    </div>
    <div>
      <label>Denominación del empleo</label>
      <select id="filter-denominacion"><option value="">— todas —</option></select>
    </div>
    <div>
      <label>Código y Grado</label>
      <select id="filter-codigo"><option value="">— todos —</option></select>
    </div>
    <div>
      <label>Nivel jerárquico</label>
      <select id="filter-nivel"><option value="">— todos —</option></select>
    </div>
    <div>
      <label>Ciudad</label>
      <select id="filter-ciudad"><option value="">— todas —</option></select>
    </div>
    <div>
      <label>Subgrupo / Sede</label>
      <select id="filter-subgrupo"><option value="">— todos —</option></select>
    </div>
    <div>
      <label>Proceso</label>
      <select id="filter-proceso"><option value="">— todos —</option></select>
    </div>
    <div>
      <label>Buscar texto (en cualquier campo)</label>
      <input type="search" id="filter-search" placeholder="Ej: derecho, ingeniería, anticorrupción">
    </div>
    <button class="clear-btn" id="btn-clear">Limpiar filtros</button>
  </div>

  <div class="table-wrap">
    <table id="tabla" class="display compact" style="width:100%">
      <thead><tr id="thead-row"></tr></thead>
    </table>
  </div>
</div>

<footer class="site-footer">
  Realizado por
  <a href="https://github.com/ronyvaldelamar" target="_blank" rel="noopener noreferrer">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.4 3-.405 1.02.005 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
    Rony Valdelamar
  </a>
</footer>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <button class="close-btn" id="modal-close">&times;</button>
    <h2 id="modal-title"></h2>
    <div id="modal-body"></div>
  </div>
</div>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/2.1.8/js/dataTables.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.2.0/js/dataTables.buttons.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.2.0/js/buttons.html5.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>

<script>
const COLUMNS = __COLUMNS__;
const LONG_COLS = new Set(__LONG_COLS__);
const DATA = __DATA__;

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truncate(text, len = 80) {
  if (!text) return "";
  text = String(text);
  if (text.length <= len) return text;
  return text.slice(0, len) + "…";
}

$(function () {
  const $thead = $("#thead-row");
  COLUMNS.forEach(([key, label]) => {
    $thead.append(`<th>${label}</th>`);
  });

  const cols = COLUMNS.map(([key, label]) => ({
    title: label,
    data: key,
    render: function (data, type, row) {
      if (type !== "display") return data ?? "";
      if (data == null || data === "") return "";
      if (LONG_COLS.has(key)) {
        const str = String(data);
        const preview = truncate(str, 80);
        return `<span class="preview">${escapeHtml(preview)}</span><span class="full">${escapeHtml(str)}</span>` +
               (str.length > 80 ? `<span class="toggle" onclick="this.parentElement.classList.toggle('expanded'); event.stopPropagation();">[+]</span>` : "");
      }
      if (key === "asignacion_basica") {
        return `<span class="num">${escapeHtml(data)}</span>`;
      }
      if (key === "num_cargos_total" || key === "cantidad_cargos_ciudad" || key === "pagina_inicio" || key === "pagina_fin") {
        return `<span class="num">${escapeHtml(data)}</span>`;
      }
      return escapeHtml(data);
    },
    className: LONG_COLS.has(key) ? "truncate" : "",
  }));

  // Estadísticas globales
  const numConvUnicas = new Set(DATA.map(r => r.numero_convocatoria)).size;
  const totalCargos = DATA.reduce((sum, r) => sum + (parseInt(r.cantidad_cargos_ciudad) || 0), 0);
  const ciudadesUnicas = new Set(DATA.map(r => r.ciudad).filter(Boolean)).size;
  $("#stat-conv").text(numConvUnicas.toLocaleString("es-CO"));
  $("#stat-rows").text(DATA.length.toLocaleString("es-CO"));
  $("#stat-cargos").text(totalCargos.toLocaleString("es-CO"));
  $("#stat-ciudades").text(ciudadesUnicas.toLocaleString("es-CO"));

  // Llenar selects de filtros con valores únicos
  function fillSelect(id, key, sortNumeric = false) {
    const $sel = $(id);
    const values = Array.from(new Set(DATA.map(r => r[key]).filter(v => v != null && v !== "")));
    if (sortNumeric) {
      values.sort((a, b) => (+a) - (+b));
    } else {
      values.sort((a, b) => String(a).localeCompare(String(b), "es"));
    }
    values.forEach(v => $sel.append(`<option value="${escapeHtml(String(v))}">${escapeHtml(String(v))}</option>`));
  }
  fillSelect("#filter-numero", "numero_convocatoria", true);
  fillSelect("#filter-denominacion", "denominacion_empleo");
  fillSelect("#filter-codigo", "codigo_grado");
  fillSelect("#filter-nivel", "nivel_jerarquico");
  fillSelect("#filter-ciudad", "ciudad");
  fillSelect("#filter-subgrupo", "subgrupo_ubicacion");
  fillSelect("#filter-proceso", "proceso");

  // Inicializar DataTable
  const dt = $("#tabla").DataTable({
    data: DATA,
    columns: cols,
    pageLength: 25,
    lengthMenu: [10, 25, 50, 100, 250],
    order: [[0, "asc"]],
    language: {
      url: "https://cdn.datatables.net/plug-ins/2.1.8/i18n/es-ES.json",
    },
    dom: '<"top"Bf>rt<"bottom"lip>',
    buttons: [
      { extend: "csvHtml5", text: "Exportar CSV", filename: "convocatorias_filtradas",
        exportOptions: { orthogonal: "export" } },
      { extend: "excelHtml5", text: "Exportar Excel", filename: "convocatorias_filtradas",
        exportOptions: { orthogonal: "export" } },
    ],
    columnDefs: [
      { targets: COLUMNS.findIndex(([k]) => k === "asignacion_basica"), className: "num" },
      { targets: COLUMNS.findIndex(([k]) => k === "num_cargos_total"), className: "num" },
      { targets: COLUMNS.findIndex(([k]) => k === "cantidad_cargos_ciudad"), className: "num" },
    ],
  });

  // Conectar selects a DataTable
  function applyFilters() {
    // Limpiar filtros previos
    dt.columns().search("");
    const map = {
      "numero_convocatoria": $("#filter-numero").val(),
      "denominacion_empleo": $("#filter-denominacion").val(),
      "codigo_grado": $("#filter-codigo").val(),
      "nivel_jerarquico": $("#filter-nivel").val(),
      "ciudad": $("#filter-ciudad").val(),
      "subgrupo_ubicacion": $("#filter-subgrupo").val(),
      "proceso": $("#filter-proceso").val(),
    };
    Object.entries(map).forEach(([key, val]) => {
      const colIdx = COLUMNS.findIndex(([k]) => k === key);
      if (colIdx >= 0) {
        dt.column(colIdx).search(val ? "^" + val.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$" : "", true, false);
      }
    });
    dt.search($("#filter-search").val() || "");
    dt.draw();
  }

  $("#filter-numero, #filter-denominacion, #filter-codigo, #filter-nivel, #filter-ciudad, #filter-subgrupo, #filter-proceso")
    .on("change", applyFilters);
  $("#filter-search").on("input", applyFilters);
  $("#btn-clear").on("click", function () {
    $(".filters select").val("");
    $("#filter-search").val("");
    applyFilters();
  });

  // Click en una fila → abrir modal con detalle completo
  $("#tabla tbody").on("click", "tr", function (e) {
    if ($(e.target).hasClass("toggle")) return;
    const data = dt.row(this).data();
    if (!data) return;
    $("#modal-title").text(`Convocatoria N° ${data.numero_convocatoria} — ${data.denominacion_empleo || ""}`);
    const $body = $("#modal-body").empty();
    COLUMNS.forEach(([key, label]) => {
      const val = data[key];
      if (val == null || val === "") return;
      $body.append(
        `<div class="field"><div class="field-label">${escapeHtml(label)}</div>` +
        `<div class="field-value">${escapeHtml(String(val))}</div></div>`
      );
    });
    $("#modal").addClass("open");
  });
  $("#modal-close, #modal").on("click", function (e) {
    if (e.target.id === "modal" || e.target.id === "modal-close") {
      $("#modal").removeClass("open");
    }
  });
});
</script>
</body>
</html>
"""


def load_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convertir strings vacíos a None para JSON
            cleaned = {k: (v if v != "" else None) for k, v in row.items()}
            rows.append(cleaned)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: no existe {csv_path}", file=sys.stderr)
        return 1

    rows = load_csv(csv_path)
    print(f"Leídas {len(rows)} filas de {csv_path}")

    html = (
        HTML_TEMPLATE
        .replace("__COLUMNS__", json.dumps([list(c) for c in COLUMNS], ensure_ascii=False))
        .replace("__LONG_COLS__", json.dumps(sorted(LONG_COLUMNS)))
        .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    )

    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Escrito {out_path}  ({size_mb:.2f} MB)")
    print(f"Abrir: file://{out_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

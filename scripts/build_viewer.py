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
    --primary-soft: #eef4ff;
    --accent: #0ea5e9;
    --text: #1f2937;
    --muted: #6b7280;
    --border: #e5e7eb;
    --success: #059669;
    --warning: #d97706;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
    --shadow-lg: 0 20px 60px rgba(0,0,0,0.25);
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

  /* ---------- Filtros ---------- */
  .filters-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem 1.1rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-sm);
  }
  .filters-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.85rem;
  }
  .filters-title {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .filters-actions { display: flex; gap: 0.5rem; align-items: center; }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: var(--primary-soft);
    color: var(--primary);
    border: 1px solid #dbe6fb;
    border-radius: 999px;
    padding: 0.2rem 0.6rem;
    font-size: 0.72rem;
    font-weight: 600;
  }
  .clear-btn {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.45rem 0.85rem;
    font-size: 0.82rem;
    cursor: pointer;
    color: var(--text);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    transition: all 0.15s;
  }
  .clear-btn:hover { background: #f3f4f6; border-color: #cbd5e1; }
  .clear-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .search-row {
    display: flex;
    align-items: center;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0 0.75rem;
    margin-bottom: 0.85rem;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .search-row:focus-within { border-color: var(--primary-light); box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }
  .search-row svg { color: var(--muted); flex-shrink: 0; }
  .search-row input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    padding: 0.65rem 0.5rem;
    font-size: 0.9rem;
    font-family: inherit;
    color: var(--text);
  }

  .filters-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.7rem;
  }
  .filter-field { display: flex; flex-direction: column; gap: 0.25rem; }
  .filter-field label {
    font-size: 0.7rem;
    color: var(--muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
  .filter-field select {
    width: 100%;
    padding: 0.45rem 0.55rem;
    border: 1px solid var(--border);
    border-radius: 7px;
    font-size: 0.85rem;
    font-family: inherit;
    background: #fff
      url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>")
      no-repeat right 0.55rem center;
    -webkit-appearance: none;
    -moz-appearance: none;
    appearance: none;
    padding-right: 1.7rem;
    cursor: pointer;
    color: var(--text);
    transition: border-color 0.15s;
  }
  .filter-field select:hover { border-color: #cbd5e1; }
  .filter-field select:focus { outline: none; border-color: var(--primary-light); box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }

  /* ---------- Tabla ---------- */
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
  table.dataTable tbody td { font-size: 0.82rem; vertical-align: top; }
  table.dataTable tbody tr { cursor: pointer; }
  table.dataTable tbody tr:hover { background: #f9fafb; }
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
  .num { text-align: right; font-variant-numeric: tabular-nums; }

  /* ---------- Footer ---------- */
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

  /* ---------- Modal de detalle ---------- */
  .modal-overlay {
    position: fixed; inset: 0; background: rgba(15,23,42,0.55);
    backdrop-filter: blur(3px);
    display: none; align-items: flex-start; justify-content: center;
    z-index: 100; padding: 2rem 1rem; overflow-y: auto;
    animation: fadeIn 0.18s ease-out;
  }
  .modal-overlay.open { display: flex; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  .modal {
    background: #fff;
    border-radius: 14px;
    max-width: 1080px;
    width: 100%;
    max-height: calc(100vh - 4rem);
    display: flex;
    flex-direction: column;
    box-shadow: var(--shadow-lg);
    overflow: hidden;
    animation: slideUp 0.22s ease-out;
  }
  .modal-header {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    color: #fff;
    padding: 1.5rem 1.75rem 1.25rem;
    position: relative;
  }
  .modal-header .conv-badge {
    display: inline-block;
    background: rgba(255,255,255,0.2);
    color: #fff;
    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 999px;
    padding: 0.2rem 0.7rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
  }
  .modal-header h2 {
    margin: 0 0 0.4rem 0;
    font-size: 1.4rem;
    font-weight: 700;
    line-height: 1.25;
    padding-right: 3rem;
  }
  .modal-header .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.75rem;
    font-size: 0.85rem;
    opacity: 0.95;
  }
  .modal-header .meta span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .modal-header .meta .dot { color: rgba(255,255,255,0.5); }
  .modal-close {
    position: absolute;
    top: 0.85rem;
    right: 1rem;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: rgba(255,255,255,0.18);
    border: none;
    color: #fff;
    font-size: 1.4rem;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s;
  }
  .modal-close:hover { background: rgba(255,255,255,0.32); }

  .modal-body { padding: 1.5rem 1.75rem 2rem; overflow-y: auto; flex: 1; }

  .quick-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }
  .qs {
    background: linear-gradient(180deg, #fafbff, #f3f6fc);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem 0.9rem;
  }
  .qs-label {
    font-size: 0.7rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .qs-value {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--primary);
    margin-top: 0.2rem;
    word-break: break-word;
  }
  .qs.salary .qs-value { color: var(--success); }

  .section {
    margin-bottom: 1.4rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    background: #fff;
  }
  .section-head {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.7rem 1rem;
    background: #f8fafc;
    border-bottom: 1px solid var(--border);
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--primary);
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
  .section-head svg { color: var(--primary-light); }
  .section-body { padding: 0.9rem 1rem; }

  .field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.85rem 1.25rem;
  }
  .field-grid .f { display: flex; flex-direction: column; gap: 0.15rem; }
  .field-grid .f-label {
    font-size: 0.7rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600;
  }
  .field-grid .f-value {
    font-size: 0.92rem;
    color: var(--text);
    word-break: break-word;
    line-height: 1.4;
  }

  .longtext {
    font-size: 0.92rem;
    color: var(--text);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .ubicaciones-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .ubic-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: var(--primary-soft);
    color: var(--primary);
    border: 1px solid #dbe6fb;
    padding: 0.3rem 0.65rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 500;
  }
  .ubic-tag .count {
    background: var(--primary);
    color: #fff;
    padding: 0.05rem 0.4rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
  }

  @media (max-width: 640px) {
    .modal-header h2 { font-size: 1.15rem; }
    .modal-body { padding: 1rem; }
    .modal-header { padding: 1.1rem 1.1rem 0.9rem; }
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
  <div class="filters-card">
    <div class="filters-head">
      <div class="filters-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
        Filtros
        <span class="chip" id="active-count" style="display:none">0 activos</span>
      </div>
      <div class="filters-actions">
        <button class="clear-btn" id="btn-clear" disabled>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          Limpiar
        </button>
      </div>
    </div>

    <div class="search-row">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="search" id="filter-search" placeholder="Buscar varias palabras (sin importar tildes ni mayúsculas). Ej: ingenieria sistemas">
    </div>

    <div class="filters-grid">
      <div class="filter-field">
        <label>Convocatoria N°</label>
        <select id="filter-numero"><option value="">Todas</option></select>
      </div>
      <div class="filter-field">
        <label>Denominación</label>
        <select id="filter-denominacion"><option value="">Todas</option></select>
      </div>
      <div class="filter-field">
        <label>Código y Grado</label>
        <select id="filter-codigo"><option value="">Todos</option></select>
      </div>
      <div class="filter-field">
        <label>Nivel jerárquico</label>
        <select id="filter-nivel"><option value="">Todos</option></select>
      </div>
      <div class="filter-field">
        <label>Ciudad</label>
        <select id="filter-ciudad"><option value="">Todas</option></select>
      </div>
      <div class="filter-field">
        <label>Subgrupo / Sede</label>
        <select id="filter-subgrupo"><option value="">Todos</option></select>
      </div>
      <div class="filter-field">
        <label>Proceso</label>
        <select id="filter-proceso"><option value="">Todos</option></select>
      </div>
    </div>
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
    <div class="modal-header">
      <button class="modal-close" id="modal-close" aria-label="Cerrar">&times;</button>
      <div class="conv-badge" id="m-badge">Convocatoria</div>
      <h2 id="m-title"></h2>
      <div class="meta" id="m-meta"></div>
    </div>
    <div class="modal-body" id="m-body"></div>
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

  // ---------- Filtros ----------
  // Normaliza un string para búsqueda: minúsculas + sin acentos/diacríticos.
  // Esto permite que "ingenieria de sistemas" matchee "Ingeniería de Sistemas".
  function normalize(s) {
    return String(s == null ? "" : s)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  // Cache del texto normalizado por fila (concatenando todas las columnas).
  // Acelera la búsqueda y se calcula una sola vez.
  const HAYSTACK_BY_INDEX = DATA.map(r => normalize(Object.values(r).join(" \u0001 ")));

  // Estado de los filtros (los selects siguen filtrando por columna en DataTables,
  // pero el buscador global lo manejamos vía $.fn.dataTable.ext.search para
  // tener control fino sobre normalización y multi-término).
  let SEARCH_TERMS = [];

  $.fn.dataTable.ext.search.push(function (settings, searchData, dataIndex) {
    if (SEARCH_TERMS.length === 0) return true;
    const haystack = HAYSTACK_BY_INDEX[dataIndex] || "";
    return SEARCH_TERMS.every(t => haystack.includes(t));
  });

  function updateActiveCount() {
    const selects = ["#filter-numero","#filter-denominacion","#filter-codigo","#filter-nivel","#filter-ciudad","#filter-subgrupo","#filter-proceso"];
    let active = selects.filter(s => $(s).val()).length;
    if ($("#filter-search").val()) active += 1;
    const $chip = $("#active-count");
    if (active > 0) {
      $chip.text(`${active} activo${active===1?"":"s"}`).show();
      $("#btn-clear").prop("disabled", false);
    } else {
      $chip.hide();
      $("#btn-clear").prop("disabled", true);
    }
  }

  function applyFilters() {
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
    // Búsqueda global: dividir en términos, normalizar cada uno
    const raw = ($("#filter-search").val() || "").trim();
    SEARCH_TERMS = raw
      ? normalize(raw).split(/\s+/).filter(Boolean)
      : [];
    dt.draw();
    updateActiveCount();
  }

  $("#filter-numero, #filter-denominacion, #filter-codigo, #filter-nivel, #filter-ciudad, #filter-subgrupo, #filter-proceso")
    .on("change", applyFilters);
  // Debounce para evitar redraws en cada keypress
  let searchTimer = null;
  $("#filter-search").on("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 180);
  });
  $("#btn-clear").on("click", function () {
    $(".filter-field select").val("");
    $("#filter-search").val("");
    applyFilters();
  });

  // ---------- Modal de detalle ----------
  // Iconos SVG inline
  const ICONS = {
    id:       '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M15 8h3M15 12h3M7 16h10"/></svg>',
    pin:      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    book:     '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    target:   '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    brain:    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 4 17.5a2.5 2.5 0 0 1-1.98-3A2.5 2.5 0 0 1 2 12a2.5 2.5 0 0 1 .02-2.5A2.5 2.5 0 0 1 4 6.5a2.5 2.5 0 0 1 .54-2A2.5 2.5 0 0 1 7 2"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 20 17.5a2.5 2.5 0 0 0 1.98-3A2.5 2.5 0 0 0 22 12a2.5 2.5 0 0 0-.02-2.5A2.5 2.5 0 0 0 20 6.5a2.5 2.5 0 0 0-.54-2A2.5 2.5 0 0 0 17 2"/></svg>',
    check:    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    clipboard:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>',
    info:     '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    cash:     '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    users:    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    calendar: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    layers:   '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
  };

  // Mapa de campos por sección, en orden
  const SECTION_DEFS = [
    { id: "ubicacion", title: "Ubicación y dependencia", icon: ICONS.pin, fields: [
      ["dependencia_inicial", "Dependencia"],
      ["proceso", "Proceso"],
      ["subgrupo_ubicacion", "Subgrupo / Sede"],
      ["ciudad", "Ciudad"],
      ["cantidad_cargos_ciudad", "Cargos en la ciudad"],
    ]},
    { id: "requisitos", title: "Requisitos mínimos", icon: ICONS.check, fields: [
      ["estudio", "Estudios"],
      ["experiencia", "Experiencia"],
      ["equivalencias", "Equivalencias"],
    ]},
    { id: "proposito", title: "Propósito y funciones", icon: ICONS.target, fields: [
      ["proposito", "Propósito"],
      ["funciones", "Funciones"],
    ]},
    { id: "conocimientos", title: "Conocimientos esenciales", icon: ICONS.brain, fields: [
      ["conocimientos_especificos", "Específicos"],
      ["conocimientos_comunes", "Comunes"],
      ["competencias_comportamentales", "Competencias comportamentales"],
    ]},
    { id: "pruebas", title: "Pruebas y admisión", icon: ICONS.clipboard, fields: [
      ["pruebas", "Pruebas"],
      ["lista_admitidos_reclamaciones", "Lista de admitidos / Reclamaciones"],
    ]},
    { id: "fechas", title: "Fechas y divulgación", icon: ICONS.calendar, fields: [
      ["fecha_fijacion", "Fecha de fijación"],
      ["termino_inscripciones", "Término de inscripciones"],
      ["medio_divulgacion", "Medio de divulgación"],
    ]},
    { id: "notas", title: "Notas generales", icon: ICONS.info, fields: [
      ["notas_generales", "Notas"],
    ]},
  ];

  // Campos considerados "largos" → se renderizan como longtext en lugar de field-grid
  const LONGTEXT_FIELDS = new Set([
    "estudio","experiencia","equivalencias","proposito","funciones",
    "conocimientos_especificos","conocimientos_comunes","competencias_comportamentales",
    "lista_admitidos_reclamaciones","pruebas","notas_generales",
    "termino_inscripciones","medio_divulgacion","dependencia_inicial",
  ]);

  // Para mostrar todas las ubicaciones de la convocatoria, agrupamos las filas
  // del CSV por número de convocatoria.
  const BY_CONV = (() => {
    const m = new Map();
    DATA.forEach(r => {
      const k = String(r.numero_convocatoria);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(r);
    });
    return m;
  })();

  function renderModal(data) {
    const conv = String(data.numero_convocatoria);
    const allRows = BY_CONV.get(conv) || [data];

    // Header
    $("#m-badge").text(`Convocatoria N° ${data.numero_convocatoria || "—"}`);
    $("#m-title").text(data.denominacion_empleo || "Sin denominación");

    const $meta = $("#m-meta").empty();
    const metaItems = [];
    if (data.codigo_grado) metaItems.push(`${ICONS.layers} <span>${escapeHtml(data.codigo_grado)}</span>`);
    if (data.nivel_jerarquico) metaItems.push(`<span>${escapeHtml(data.nivel_jerarquico)}</span>`);
    if (data.pagina_inicio) metaItems.push(`<span>Pág. ${escapeHtml(data.pagina_inicio)}${data.pagina_fin && data.pagina_fin !== data.pagina_inicio ? "–"+escapeHtml(data.pagina_fin) : ""}</span>`);
    metaItems.forEach((html, i) => {
      if (i > 0) $meta.append('<span class="dot">•</span>');
      $meta.append(`<span>${html}</span>`);
    });

    // Body
    const $body = $("#m-body").empty();

    // Quick stats
    const totalCargos = data.num_cargos_total || allRows.reduce((s,r)=>s+(parseInt(r.cantidad_cargos_ciudad)||0),0);
    const ciudadesDistintas = new Set(allRows.map(r=>r.ciudad).filter(Boolean)).size;
    const stats = [
      { cls: "salary", label: "Asignación básica", icon: ICONS.cash, value: data.asignacion_basica || "No disponible" },
      { cls: "", label: "Vigencia", icon: ICONS.calendar, value: data.vigencia_salario || "—" },
      { cls: "", label: "Total de cargos", icon: ICONS.users, value: (totalCargos || "—").toLocaleString ? Number(totalCargos).toLocaleString("es-CO") : totalCargos },
      { cls: "", label: "Ciudades", icon: ICONS.pin, value: ciudadesDistintas || 1 },
    ];
    const $qs = $('<div class="quick-stats"></div>');
    stats.forEach(s => {
      $qs.append(`<div class="qs ${s.cls}"><div class="qs-label">${s.icon}${escapeHtml(s.label)}</div><div class="qs-value">${escapeHtml(String(s.value))}</div></div>`);
    });
    $body.append($qs);

    // Sección "Identificación" como field-grid compacto
    const idFields = [
      ["denominacion_empleo", "Denominación"],
      ["codigo_grado", "Código y Grado"],
      ["nivel_jerarquico", "Nivel jerárquico"],
      ["asignacion_basica", "Asignación básica"],
      ["vigencia_salario", "Vigencia"],
      ["num_cargos_total", "Total de cargos"],
    ];
    let idHtml = '<div class="field-grid">';
    idFields.forEach(([k, lbl]) => {
      const v = data[k];
      if (v == null || v === "") return;
      idHtml += `<div class="f"><div class="f-label">${escapeHtml(lbl)}</div><div class="f-value">${escapeHtml(String(v))}</div></div>`;
    });
    idHtml += '</div>';
    $body.append(`<div class="section"><div class="section-head">${ICONS.id}Identificación del empleo</div><div class="section-body">${idHtml}</div></div>`);

    // Sección "Ubicaciones" especial: tags con todas las ciudades de la conv
    const ubicSet = new Map(); // key=subgrupo|ciudad -> cantidad
    allRows.forEach(r => {
      if (!r.ciudad) return;
      const key = (r.subgrupo_ubicacion || "") + "|" + r.ciudad;
      ubicSet.set(key, {
        subgrupo: r.subgrupo_ubicacion || "",
        ciudad: r.ciudad,
        cantidad: (ubicSet.get(key)?.cantidad || 0) + (parseInt(r.cantidad_cargos_ciudad)||0),
      });
    });
    if (ubicSet.size > 0) {
      let html = '<div class="ubicaciones-list">';
      Array.from(ubicSet.values())
        .sort((a,b)=>String(a.ciudad).localeCompare(String(b.ciudad),"es"))
        .forEach(u => {
          const lbl = u.subgrupo ? `${u.subgrupo} — ${u.ciudad}` : u.ciudad;
          html += `<span class="ubic-tag">${escapeHtml(lbl)}${u.cantidad?`<span class="count">${u.cantidad}</span>`:""}</span>`;
        });
      html += '</div>';
      // Plus dependencia/proceso como field-grid abajo
      const extras = [["dependencia_inicial","Dependencia inicial"], ["proceso","Proceso"]]
        .filter(([k]) => data[k] && data[k] !== "")
        .map(([k,lbl]) => `<div class="f"><div class="f-label">${escapeHtml(lbl)}</div><div class="f-value">${escapeHtml(String(data[k]))}</div></div>`)
        .join("");
      const extrasHtml = extras ? `<div class="field-grid" style="margin-top:0.85rem">${extras}</div>` : "";
      $body.append(`<div class="section"><div class="section-head">${ICONS.pin}Ubicaciones (${ubicSet.size}) y dependencia</div><div class="section-body">${html}${extrasHtml}</div></div>`);
    }

    // Resto de secciones
    const SECTIONS_REMAINING = SECTION_DEFS.filter(s => s.id !== "ubicacion");
    SECTIONS_REMAINING.forEach(sec => {
      const items = sec.fields.filter(([k]) => data[k] != null && data[k] !== "");
      if (items.length === 0) return;
      let inner = "";
      const longItems = items.filter(([k]) => LONGTEXT_FIELDS.has(k));
      const shortItems = items.filter(([k]) => !LONGTEXT_FIELDS.has(k));
      if (shortItems.length > 0) {
        inner += '<div class="field-grid">';
        shortItems.forEach(([k, lbl]) => {
          inner += `<div class="f"><div class="f-label">${escapeHtml(lbl)}</div><div class="f-value">${escapeHtml(String(data[k]))}</div></div>`;
        });
        inner += '</div>';
      }
      longItems.forEach(([k, lbl], i) => {
        inner += `<div${i>0||shortItems.length>0?' style="margin-top:1rem"':""}><div class="f-label" style="margin-bottom:0.3rem">${escapeHtml(lbl)}</div><div class="longtext">${escapeHtml(String(data[k]))}</div></div>`;
      });
      $body.append(`<div class="section"><div class="section-head">${sec.icon}${escapeHtml(sec.title)}</div><div class="section-body">${inner}</div></div>`);
    });

    $("#modal").addClass("open");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    $("#modal").removeClass("open");
    document.body.style.overflow = "";
  }

  $("#tabla tbody").on("click", "tr", function (e) {
    if ($(e.target).hasClass("toggle")) return;
    const data = dt.row(this).data();
    if (!data) return;
    renderModal(data);
  });
  $("#modal-close").on("click", closeModal);
  $("#modal").on("click", function (e) { if (e.target.id === "modal") closeModal(); });
  $(document).on("keydown", function (e) {
    if (e.key === "Escape" && $("#modal").hasClass("open")) closeModal();
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

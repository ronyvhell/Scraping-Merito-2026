# Scraper de Convocatorias - Concurso de Méritos PGN 2026

Extrae y estructura los datos del PDF de convocatorias del Concurso Abierto
de Méritos de la Procuraduría General de la Nación (Resolución 108 del 23 de
abril de 2026, Versión 2). Genera CSV, Excel y un visualizador HTML con
filtros y búsqueda.

## Estructura del proyecto

```
.
├── PDF/                                         # PDFs de entrada (no modificar)
├── csv/                                         # Salidas
│   ├── convocatorias_por_ciudad.csv             # 1 fila por (convocatoria, ciudad)
│   ├── convocatorias_por_ciudad.xlsx
│   ├── convocatorias_resumen.csv                # 1 fila por convocatoria
│   ├── convocatorias_resumen.xlsx
│   ├── convocatorias_raw.json                   # JSON crudo con la estructura completa
│   └── .spans_cache.json                        # Cache de páginas (acelera re-corridas)
├── scripts/
│   ├── scrape_pdf.py                            # Scraper principal
│   ├── build_viewer.py                          # Generador del visualizador HTML
│   ├── explore.py / explore2.py                 # Utilidades de inspección del PDF
├── visualizador.html                            # Visualizador interactivo (auto-contenido)
├── requirements.txt
└── README.md
```

## Requisitos

Python 3.10+ y las dependencias de `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Uso

### 1. Ejecutar el scraper

```bash
python scripts/scrape_pdf.py
```

La primera corrida tarda unos 4-5 minutos:
- ~110 s detectando los inicios de cada convocatoria en el PDF (1764 páginas).
- ~120 s extrayendo y estructurando los campos.

Los inicios se cachean en `csv/.spans_cache.json`, por lo que las corridas
posteriores tardan ~2 min.

Opciones útiles:

```bash
# Procesar sólo las primeras N convocatorias (útil para pruebas)
python scripts/scrape_pdf.py --max-convocatorias 10

# Mostrar las páginas detectadas y salir sin parsear
python scripts/scrape_pdf.py --skip-spans

# Especificar otro PDF y/o carpeta de salida
python scripts/scrape_pdf.py --pdf "PDF/otro.pdf" --out "salida/"
```

### 2. Generar el visualizador HTML

```bash
python scripts/build_viewer.py
```

Se crea `visualizador.html` con los datos embebidos. Ábrelo en cualquier
navegador (doble click).

## El visualizador HTML

El archivo `visualizador.html` es **autocontenido**: todos los datos están
embebidos y sólo carga DataTables y jQuery desde CDN. Funciona sin servidor.

Funciones:
- Tabla con todas las filas (1 fila por sede / ciudad).
- Filtros por: número de convocatoria, denominación, código y grado, nivel
  jerárquico, ciudad, subgrupo y proceso.
- Búsqueda libre en cualquier campo.
- Paginación, ordenamiento por columna.
- Click en una fila → abre modal con el detalle completo (incluye textos
  largos como funciones, propósito, conocimientos esenciales, etc.).
- Botones para exportar la vista filtrada a CSV y Excel.

## Esquema de los CSV

### `convocatorias_por_ciudad.csv` (1233 filas, ~278 convocatorias)

| Columna                          | Descripción                                          |
| -------------------------------- | ---------------------------------------------------- |
| `numero_convocatoria`            | Número de la convocatoria (1..291)                   |
| `version_convocatoria`           | Versión (`No. 2` en este PDF)                        |
| `fecha_fijacion`                 | Fecha de fijación del aviso                          |
| `denominacion_empleo`            | Denominación del cargo                               |
| `codigo_grado`                   | Código y grado del cargo                             |
| `nivel_jerarquico`               | Nivel jerárquico                                     |
| `asignacion_basica`              | Salario mensual                                      |
| `vigencia_salario`               | Año de vigencia del salario                          |
| `num_cargos_total`               | Total de cargos de la convocatoria                   |
| `subgrupo_ubicacion`             | Subgrupo / sede / dependencia agrupadora             |
| `ciudad`                         | Ciudad / sede específica                             |
| `cantidad_cargos_ciudad`         | Cargos a proveer en esa ciudad                       |
| `dependencia_inicial`            | Dependencia(s) inicial(es)                           |
| `proceso`                        | Proceso al que pertenece                             |
| `estudio`                        | Estudios requeridos                                  |
| `experiencia`                    | Experiencia requerida                                |
| `equivalencias`                  | Equivalencias entre estudios y experiencia           |
| `proposito`                      | Propósito del empleo                                 |
| `funciones`                      | Texto completo de funciones                          |
| `conocimientos_especificos`      | Sección 4                                            |
| `conocimientos_comunes`          | Sección 5                                            |
| `competencias_comportamentales`  | Sección 6                                            |
| `lista_admitidos_reclamaciones`  | Sección 7                                            |
| `pruebas`                        | Sección 8 (pruebas, carácter, puntaje)               |
| `notas_generales`                | Sección 9                                            |
| `termino_inscripciones`          | Texto del prólogo (fechas, horarios, etc.)           |
| `medio_divulgacion`              | Medio de divulgación                                 |
| `pagina_inicio` / `pagina_fin`   | Rango de páginas en el PDF                           |

### `convocatorias_resumen.csv` (278 filas)

Una fila por convocatoria. Mismas columnas excepto que las ciudades se
consolidan en `ubicaciones_resumen` y se añade `num_ciudades`.

## Validación de calidad

Tras procesar el PDF completo:

- **278 convocatorias detectadas** (de un PDF de 1764 páginas).
- **1233 filas por ciudad/sede**.
- **24 denominaciones distintas**, **114 ciudades distintas**.
- **~88% de las convocatorias** tienen suma de cargos por ciudad coincidente
  con el total declarado. El resto presenta layouts atípicos.

### Limitaciones conocidas

Algunas convocatorias usan formatos especiales que el parser no captura
perfectamente:

1. **Ciudades sin cantidad entre paréntesis** (convs. 89, 95: Procurador
   Judicial I/II). En estos casos cada ciudad lleva 1 cargo implícito que el
   PDF no expresa con `(N)`.
2. **Layouts ligeramente diferentes** que dejan algunos campos sin extraer
   (ej. `nivel_jerarquico` en algunas convocatorias muy compactas).
3. **Subgrupos largos** que en el PDF aparecen partidos en 3+ líneas pueden
   quedar parcialmente truncados.

Las salidas en `csv/convocatorias_raw.json` permiten inspeccionar el detalle
crudo de cada convocatoria si necesitas validar manualmente.

## Cómo funciona el parser (resumen técnico)

1. **Detección de convocatorias**: recorre cada página y busca
   `CONVOCATORIA No. NN - 2026`. Determina el rango de páginas de cada una.
2. **Limpieza del header/footer**: filtra las palabras `PROCURADURÍA`,
   `GENERAL DE LA NACIÓN`, `COLOMBIA`, `FORMATO: CONVOCATORIA`,
   `PROCESO: TALENTO HUMANO`, `Versión 3`, `Fecha 23/02/2026`,
   `Código TH-F-211` por posición Y (top ≤ 115pt) y por contenido.
3. **Sección IDENTIFICACIÓN (1)**: usa `extract_words` con coordenadas X/Y
   para asignar cada palabra a la columna correcta (Denominación, Código,
   Nivel, Asignación, Ubicación, Número, Dependencia). Detecta etiquetas
   partidas en varias líneas.
4. **Ciudades vs subgrupos**: una "ciudad" siempre termina en `(N)`. Una
   línea sin paréntesis se interpreta como subgrupo. La heurística diferencia
   continuaciones (cuando aún no hay ciudades en el subgrupo actual) de
   nuevos subgrupos paralelos.
5. **Otras secciones (2-9)**: se extraen como texto plano usando regex sobre
   el texto en modo layout.
6. **Deduplicación**: las ubicaciones idénticas que se repiten cuando una
   convocatoria abarca varias páginas se colapsan al final.

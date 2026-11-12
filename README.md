# Datos Economicos

Dashboard económico automático para Chile: series oficiales del Banco Central (TPM, IPC, desempleo, IMACEC) + cotización en vivo (IPSA, tipo de cambio).

## Setup local

1. Pedir credenciales gratis de la API BDE del Banco Central en:
   https://si3.bcentral.cl/Siete/es/Siete/API
   (te llegan por email un usuario y contraseña)

2. Crear un archivo `.env` en la raíz del proyecto (no se sube al repo, está en `.gitignore`) con:

   ```
   BCCH_USER=tu_usuario
   BCCH_PASSWORD=tu_contraseña
   ```

3. Activar el entorno virtual e instalar dependencias:

   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Monitor (versión tipo tablero)

`docs/monitor/` es una página estática (sin paso de compilación: HTML + JavaScript + ECharts desde CDN) que dibuja los JSON de `docs/monitor/data/`. Esos JSON los genera `app/exportar_monitor.py` (el cálculo vive en Python, la página solo muestra) y los workflows lo corren después del reporte HTML. Se ve en https://sebam123.github.io/datos-economicos/monitor/. Para probarlo local: `cd docs && python3 -m http.server 8000` y abrir `http://localhost:8000/monitor/`. La pestaña «Composición del PIB» sale de `data/composicion.csv` (`data_pipeline/fetch_composicion.py`, ~110 series del Banco Central) y `app/composicion.py`, que arma los árboles de componentes (gasto, actividad, exportaciones por producto); para agregar o reordenar componentes se edita ahí. La pestaña «Población» (pirámide y reparto por edad, 1960-2050) sale de `data_pipeline/fetch_poblacion.py`, que baja del Banco Mundial las estimaciones y proyecciones de la ONU directo a `docs/monitor/data/poblacion.json` (cada 14 días). Ojo: los totales de la ONU no calzan con los censos del INE (el Censo 2024 contó 18,48 millones); los puntos de los censos están copiados a mano en ese script. La pestaña «Mercado laboral» sale de `data_pipeline/fetch_laboral.py` (Banco Central, familia F049: población en edad de trabajar, fuerza de trabajo, ocupados, desocupados e inactivos por sexo y 12 tramos de edad, más ocupados por rama CIIU4; comprueba que las identidades contables cuadren antes de guardar `docs/monitor/data/laboral.json`). No hay series de informalidad en el Banco Central; el INE las tiene en `stat.ine.cl` (API SDMX), pero ese portal quedó congelado en mayo de 2024. La pestaña «Profesionales y técnicos» sale de `docs/monitor/data/titulados.json`, que NO se actualiza sola: lo genera a mano `data_pipeline/procesar_titulados.py` a partir de los archivos «Titulados Ed Superior AAAA» del Mineduc (https://datosabiertos.mineduc.cl/titulados-en-educacion-superior/, un .rar por año, ~2 GB descomprimidos; el Mineduc publica el año nuevo hacia septiembre). Para renovarlo: bajar los .rar a una carpeta (fuera del repo), correr `.venv/bin/python data_pipeline/procesar_titulados.py CARPETA` y subir el JSON resultante (solo conteos, nada individual). Los ocupados por grupo ocupacional de esa pestaña vienen de `laboral.json` (se actualiza solo). La pestaña «Fondos de pensiones» sale de `data_pipeline/fetch_pensiones.py` (patrimonio diario de las AFP de la Superintendencia de Pensiones, solo valores confirmados; % del PIB oficial del Banco Central F029.ACF.PPIB18.AFP.T; comparación OCDE DF_PA). `data_pipeline/fetch_presupuesto.py` ya baja el presupuesto de la Dipres (datos.gob.cl, cierres 2009-2025 y ejecución del año en curso, ya a `docs/monitor/data/presupuesto.json`), y alimenta la pestaña «Presupuesto fiscal» (gasto por ministerio y por tipo, ingresos y ejecución del año en curso; el gasto por ministerio descuenta el «aporte fiscal» del Tesoro Público para no duplicar). Los cierres de años pasados no se vuelven a bajar. La pestaña «Deuda pública» sale de `data_pipeline/fetch_deuda.py` (Banco Central, familia F051: deuda bruta y neta del Gobierno Central y del sector público en % del PIB y en pesos, trimestral desde 2006, más la deuda de otros países F019.DBPIB; el Banco Central la publica con rezago respecto de la cifra provisoria de la Dipres) y reusa `presupuesto.json` para el endeudamiento y el servicio de la deuda. La pestaña «Déficit fiscal» sale de `data_pipeline/fetch_balance.py` (Banco Central, familia F051: ingresos, gasto total y balance efectivo mensual del Gobierno Central en base devengada, y balance estructural anual; el balance efectivo coincide con el de la Dipres). La pestaña «Insumo-producto» sale de `docs/monitor/data/mip.json`, que NO se actualiza sola: lo genera a mano `data_pipeline/procesar_mip.py` (con `mip_lib.py`; requiere numpy y openpyxl, no están en requirements.txt porque no corre en el flujo automático) a partir de las matrices anuales a 111 actividades del Banco Central (https://www.bcentral.cl/web/banco-central/cuentas-nacionales-anuales-excel, 2008-2023 en tres bases; el Banco Central las publica con ~27 meses de rezago). El sitio nuevo del Banco Central tiene protección anti-bot (CAPTCHA), así que los Excel se bajan desde un navegador y se dejan en una carpeta fuera del repo; ahí están además los nombres de archivo que espera el script. El script comprueba que las identidades contables (fila y columna) cuadren en cada año antes de guardar. Los 12 sectores son agrupaciones propias de las 111 (la clasificación de 12 cambia entre la base 2008 y las demás). El calendario del Monitor mezcla Chile (`app/calendario.py`, que además decide cuándo reintentar el pipeline) y EE.UU. (`app/calendario_eeuu.py`: fechas de la Fed, BLS y BEA copiadas a mano de los calendarios oficiales de 2026; hay que actualizarlas cada año). Los datos de EE.UU. del calendario vienen de FRED (`fetch_fred.py`). Para agregar un indicador, sumarlo a `SERIES` (y a `TEMAS` si va en una tarjeta de la portada) en `exportar_monitor.py`. Los gráficos que combinan varias series o no son series de tiempo (contribuciones del IMACEC, proyecciones, rankings OCDE y por estado de EE.UU.) se definen en `app/monitor_graficos.py` (`GRAFICOS`) y se asignan a una pestaña con `pestana` (un tema de `TEMAS` o una sección de `SECCIONES`).

## Actualizar con un comando

```bash
python actualizar.py
```

(o doble clic en `actualizar.command`). Dispara en GitHub el mismo workflow que corre cada día, espera a que termine, trae el resultado a esta copia y muestra un resumen de los últimos datos y de las revisiones detectadas. Requiere la CLI de GitHub (`brew install gh`, luego `gh auth login`).

## Revisiones de datos

El Banco Central y el INE revisan cifras de meses anteriores. Los gráficos usan siempre el valor vigente (revisado), pero cada vez que una cifra cambia, el valor anterior queda archivado en `data/revisiones.csv` (serie, fecha, valor_anterior, valor_nuevo, detectado_el) y se resume en la sección «Revisiones de datos» del dashboard. Los datos de mercado (IPSA, dólar, etc.) no se registran como revisiones, porque sus cambios intradía no lo son.

## Actualización automática

`.github/workflows/actualizar_datos.yml` corre todos los días y comitea `data/historico.csv` si hay datos nuevos. Para que funcione hay que cargar los secrets del repo en GitHub (Settings → Secrets and variables → Actions):

- `BCCH_USER`
- `BCCH_PASSWORD`

## Estructura

- `data_pipeline/`: scripts que traen datos del BCCh y de mercado (yfinance) y los acumulan en `data/historico.csv`.
- `.github/workflows/`: tarea programada que corre el pipeline solo, sin intervención.
- `app/dashboard.py`: la app Streamlit (gráficos históricos + tile en vivo).

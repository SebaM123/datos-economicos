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

## Actualización automática

`.github/workflows/actualizar_datos.yml` corre todos los días y comitea `data/historico.csv` si hay datos nuevos. Para que funcione hay que cargar los secrets del repo en GitHub (Settings → Secrets and variables → Actions):

- `BCCH_USER`
- `BCCH_PASSWORD`

## Estructura

- `data_pipeline/`: scripts que traen datos del BCCh y de mercado (yfinance) y los acumulan en `data/historico.csv`.
- `.github/workflows/`: tarea programada que corre el pipeline solo, sin intervención.
- `app/dashboard.py`: la app Streamlit (gráficos históricos + tile en vivo).

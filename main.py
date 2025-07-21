import os
import sys
from datetime import datetime
from dotenv import load_dotenv

from src.grid_utils import create_grid
from src.zonal_utils import get_class_percentages_per_grid
from src.map_utils import plot_landcover_comparison

# Cargar variables de entorno
load_dotenv('dot_env_content.txt')

# === PARÁMETROS ===
ONEDRIVE_PATH = os.getenv("ONEDRIVE_PATH")
MAIN_PATH = os.path.join(ONEDRIVE_PATH, "datos")
AOI_PATH = os.path.join(MAIN_PATH, "area_estudio/paramo_altiplano.geojson")  # Cambia esto si tienes otro AOI
GRID_SIZE = 100  # en metros
LOOKBACK_DAYS = 365

# Define dos fechas finales para comparar el último pixel válido
END_DATE_1 = "2025-12-31"
END_DATE_2 = "2025-09-30"

# === DIRECTORIOS ===
OUTPUT_DIR = os.path.join(MAIN_PATH, "[TEST] dynamic_world_latest/output")
GRID_DIR = os.path.join(OUTPUT_DIR, "grid")
IMG_DIR = os.path.join(OUTPUT_DIR, "images")
CSV_DIR = os.path.join(OUTPUT_DIR, "comparison")


def get_quarter_dates(qcode):
    quarter = int(qcode[1])
    year = int(qcode[2:])
    start_month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    end_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
    start_date = datetime(year, start_month, 1)
    if end_month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, end_month + 1, 1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(GRID_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(CSV_DIR, exist_ok=True)

    if not os.path.exists(AOI_PATH):
        print(f"❌ ERROR: El archivo AOI no existe en la ruta especificada: {AOI_PATH}")
        sys.exit(1)

    print("🔑 Autenticando con Google Earth Engine...")
    authenticate_gee()
    print("✅ Autenticado correctamente.")

    print("📐 Verificando grilla...")

    aoi_base = os.path.splitext(os.path.basename(AOI_PATH))[0]
    grid_filename = f"grid_{aoi_base}_{GRID_SIZE}m.geojson"
    grid_path = os.path.join(GRID_DIR, grid_filename)

    if os.path.exists(grid_path):
        print(f"⏭️ Grilla ya existe → {grid_path}. Saltando creación.")
    else:
        print("📐 Creando grilla...")
        grid = create_grid(AOI_PATH, GRID_SIZE)
        grid.to_file(grid_path, driver="GeoJSON")
        print(f"✅ Grilla guardada: {grid_path}")

    # === Descarga de imágenes DW más recientes ===
    tif1 = os.path.join(IMG_DIR, f"dw_lastpixel_{END_DATE_1}.tif")
    tif2 = os.path.join(IMG_DIR, f"dw_lastpixel_{END_DATE_2}.tif")

    if not os.path.exists(tif1):
        print(f"🌍 Descargando imagen para {END_DATE_1}...")
        download_dynamic_world_latest(grid_path, END_DATE_1, LOOKBACK_DAYS, tif1)
    else:
        print(f"⏭️ Imagen ya existe → {tif1}")

    if not os.path.exists(tif2):
        print(f"🌍 Descargando imagen para {END_DATE_2}...")
        download_dynamic_world_latest(grid_path, END_DATE_2, LOOKBACK_DAYS, tif2)
    else:
        print(f"⏭️ Imagen ya existe → {tif2}")

    # === Análisis zonal y comparación ===
    print("📊 Calculando porcentajes por clase para ambas imágenes...")
    grid_gdf = gpd.read_file(grid_path)

    df1 = get_class_percentages_per_grid(grid_gdf, tif1)
    df2 = get_class_percentages_per_grid(grid_gdf, tif2)

    # Comparar
    df_comp = compare_class_percentages(df1, df2, Q1, Q2)
    out_csv = os.path.join(CSV_DIR, f"{aoi_base}_{Q1}_{Q2}.csv")
    df_comp.to_csv(out_csv, index=False)
    print(f"✅ Comparación guardada en: {out_csv}")

    # === Mapa de comparación ===
    plot_landcover_comparison(
        tif1_path=tif1,
        tif2_path=tif2,
        q1=END_DATE_1,
        q2=END_DATE_2,
        grid_path=grid_path,
        output_path=os.path.join(OUTPUT_DIR, "maps", f"{aoi_base}_{Q1}_{Q2}.png")
    )

if __name__ == "__main__":
    main()

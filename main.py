from datetime import datetime
import os
import sys
from dotenv import load_dotenv

from src.grid_utils import create_grid
from src.download_utils import download_dynamic_world, authenticate_gee
from src.zonal_utils import get_class_percentages_per_grid, compare_class_percentages
from src.map_utils import plot_landcover_comparison

# Load environment variables from .env file
load_dotenv('dot_env_content.txt')

import geopandas as gpd

# Parámetros

ONEDRIVE_PATH = os.getenv("ONEDRIVE_PATH")
MAIN_PATH = os.path.join(ONEDRIVE_PATH, "datos")
AOI_PATH = os.path.join(MAIN_PATH, "[TEST] dynamic_world/input/paramo_altiplano.geojson") ## CAMBIAR AQUI POR LA RUTA DEL AOI
Q1 = "Q12024"
Q2 = "Q22024"
GRID_SIZE = 100
OUTPUT_DIR = os.path.join(MAIN_PATH, "[TEST] dynamic_world/output")
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

    # Descargar imágenes
    start1, end1 = get_quarter_dates(Q1)
    start2, end2 = get_quarter_dates(Q2)

    aoi_base = os.path.splitext(os.path.basename(AOI_PATH))[0]
    tif1 = os.path.join(IMG_DIR, f"dynamic_world_{aoi_base}_{Q1}.tif")
    tif2 = os.path.join(IMG_DIR, f"dynamic_world_{aoi_base}_{Q2}.tif")

    if os.path.exists(tif1):
        print(f"⏭️ Imagen {Q1} ya existe → {tif1}. Saltando descarga.")
    else:
        print(f"🌍 Descargando imagen para {Q1} ({start1} a {end1})...")
        download_dynamic_world(grid_path, start1, end1, tif1)
        print(f"✅ Imagen {Q1} descargada: {tif1}")

    if os.path.exists(tif2):
        print(f"⏭️ Imagen {Q2} ya existe → {tif2}. Saltando descarga.")
    else:
        print(f"🌍 Descargando imagen para {Q2} ({start2} a {end2})...")
        download_dynamic_world(grid_path, start2, end2, tif2)
        print(f"✅ Imagen {Q2} descargada: {tif2}")

    # Leer grilla
    grid_gdf = gpd.read_file(grid_path)

    print("📊 Calculando porcentajes por clase para ambas imágenes...")
    df1 = get_class_percentages_per_grid(grid_gdf, tif1)
    df2 = get_class_percentages_per_grid(grid_gdf, tif2)

    # Comparar
    df_comp = compare_class_percentages(df1, df2, Q1, Q2)
    out_csv = os.path.join(CSV_DIR, f"{aoi_base}_{Q1}_{Q2}.csv")
    df_comp.to_csv(out_csv, index=False)
    print(f"✅ Comparación guardada en: {out_csv}")

    plot_landcover_comparison(
        tif1_path=tif1,
        tif2_path=tif2,
        q1=Q1,
        q2=Q2,
        grid_path=grid_path,
        output_path=os.path.join(OUTPUT_DIR, "maps", f"{aoi_base}_{Q1}_{Q2}.png")
    )




if __name__ == "__main__":
    main()

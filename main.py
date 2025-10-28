#!/usr/bin/env python3
import argparse
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import geopandas as gpd

from src.download_utils import authenticate_gee, download_dynamic_world_latest, download_sentinel_rgb_period
from src.grid_utils import create_grid
from src.zonal_utils import get_transition_changes_per_grid, get_semester_dates
from src.map_utils import (
    plot_landcover_comparison,
    plot_sentinel_with_grid,
    get_tiles_from_ee,
    plot_sentinel_interactive_semester,
    plot_dynamic_world_interactive_semester
)
from reporte.render_report import render

# === CARGAR VARIABLES DE ENTORNO ===
load_dotenv("dot_env_content.env")

# === RUTAS ===
INPUTS_PATH = os.getenv("INPUTS_PATH")
AOI_DIR = os.path.join(INPUTS_PATH, "dynamic_world", "area_estudio")
OUTPUTS_BASE = os.path.join(INPUTS_PATH, "dynamic_world", "outputs")
LOGO_PATH = os.path.join(INPUTS_PATH, "gfw/Logo_SDP.jpeg")

# === PARÁMETROS GENERALES ===
GRID_SIZE = 10000  # metros
LOOKBACK_DAYS = 365  # días hacia atrás para ambas colecciones


def process_aoi(aoi_path, date_before, current_date, anio, semestre):
    """Ejecuta el flujo completo para un AOI y devuelve su resumen."""
    aoi_name = os.path.splitext(os.path.basename(aoi_path))[0]
    print(f"\n🌱 Procesando AOI: {aoi_name}")

    # === Directorios de salida ===
    output_dir = os.path.join(OUTPUTS_BASE, aoi_name)
    grid_dir = os.path.join(output_dir, "grilla")
    img_dir = os.path.join(output_dir, "imagenes")
    csv_dir = os.path.join(output_dir, "comparacion")
    map_dir = os.path.join(output_dir, "mapas")
    os.makedirs(grid_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(map_dir, exist_ok=True)

    # === Crear o cargar grilla ===
    grid_filename = f"grid_{aoi_name}_{GRID_SIZE}m.geojson"
    grid_path = os.path.join(grid_dir, grid_filename)
    if os.path.exists(grid_path):
        print(f"⏭️ Grilla ya existe: {grid_path}")
    else:
        print("📐 Creando grilla...")
        grid = create_grid(aoi_path, GRID_SIZE)
        grid.to_file(grid_path, driver="GeoJSON")
        print(f"✅ Grilla guardada: {grid_path}")

    # === Autenticación GEE ===
    print("🔑 Autenticando con Google Earth Engine...")
    authenticate_gee()
    print("✅ Autenticado correctamente.")

    # === Dynamic World ===
    tif_before = os.path.join(img_dir, f"dw_lastpixel_{date_before}.tif")
    tif_current = os.path.join(img_dir, f"dw_lastpixel_{current_date}.tif")

    if not os.path.exists(tif_before):
        print(f"🌍 Descargando imagen DW para {date_before}...")
        download_dynamic_world_latest(aoi_path, date_before, LOOKBACK_DAYS, tif_before)
    else:
        print(f"⏭️ Imagen ya existe: {tif_before}")

    if not os.path.exists(tif_current):
        print(f"🌍 Descargando imagen DW para {current_date}...")
        download_dynamic_world_latest(aoi_path, current_date, LOOKBACK_DAYS, tif_current)
    else:
        print(f"⏭️ Imagen ya existe: {tif_current}")

    # === Cálculo de transiciones ===
    print("📊 Calculando transiciones por clase...")
    grid_gdf = gpd.read_file(grid_path)
    df_trans = get_transition_changes_per_grid(grid_gdf, tif_before=tif_before, tif_current=tif_current)

    csv_trans = os.path.join(csv_dir, f"{aoi_name}_transiciones_{date_before}_a_{current_date}.csv")
    df_trans.to_csv(csv_trans, index=False)
    print(f"✅ Transiciones guardadas en: {csv_trans}")

    # === Mapa de comparación DW ===
    map_path = os.path.join(map_dir, f"{aoi_name}_{date_before}_{current_date}.png")
    print("🗺️ Generando mapa de comparación DW...")
    plot_landcover_comparison(
        tif1_path=tif_before,
        tif2_path=tif_current,
        q1=f"Semestre anterior ({date_before})",
        q2=f"Semestre actual ({current_date})",
        grid_path=grid_path,
        output_path=map_path,
    )

    # === Imagen Sentinel promedio ===
    sentinel_tif = os.path.join(img_dir, f"sentinel_rgb_{date_before}_a_{current_date}.tif")
    if not os.path.exists(sentinel_tif):
        download_sentinel_rgb_period(grid_path, date_before, current_date, sentinel_tif)

    # === Mapa Sentinel + grilla ===
    mapa_s2_path = os.path.join(map_dir, f"{aoi_name}_sentinel_grilla.png")
    plot_sentinel_with_grid(sentinel_tif, grid_path, mapa_s2_path)

    # === Mapas interactivos ===
    print("🛰️ Creando mapas interactivos semestrales...")

    # Sentinel-2
    tiles_sentinel = get_tiles_from_ee(
        aoi_path=aoi_path,
        end_t1=date_before,
        end_t2=current_date,
        dataset="SENTINEL",
        lookback_days=LOOKBACK_DAYS
    )
    sentinel_html = os.path.join(map_dir, f"{aoi_name}_sentinel_semestre.html")
    plot_sentinel_interactive_semester(
        grid_path=grid_path,
        aoi_path=aoi_path,
        output_path=sentinel_html,
        annio=anio,
        semestre=semestre,
        tiles_t1=tiles_sentinel["t1"],
        tiles_t2=tiles_sentinel["t2"]
    )

    # Dynamic World
    tiles_dw = get_tiles_from_ee(
        aoi_path=aoi_path,
        end_t1=date_before,
        end_t2=current_date,
        dataset="DW",
        lookback_days=LOOKBACK_DAYS
    )
    dw_html = os.path.join(map_dir, f"{aoi_name}_dw_semestre.html")
    plot_dynamic_world_interactive_semester(
        grid_path=grid_path,
        aoi_path=aoi_path,
        output_path=dw_html,
        annio=anio,
        semestre=semestre,
        tiles_t1=tiles_dw["t1"],
        tiles_t2=tiles_dw["t2"]
    )

    # === Calcular estadísticas de pérdida ===
    pixeles_perdidos_total = df_trans["n_1_a_otro"].sum()
    hectareas_perdidas_total = round(pixeles_perdidos_total * 0.01, 2)
    fila_max = df_trans.loc[df_trans["n_1_a_otro"].idxmax()]
    grilla_mas_perdida = int(fila_max["grid_id"])
    hectareas_perdidas_max = round(fila_max["n_1_a_otro"] * 0.01, 2)

    # === Diccionario del páramo ===
    return {
        "NOMBRE_PARAMO": aoi_name.replace("_", " ").title(),
        "PERDIDA_BOSQUE_TOTAL": hectareas_perdidas_total,
        "PERDIDA_BOSQUE_GRILLA_1": hectareas_perdidas_max,
        "GRILLA_CON_MAS_PERDIDA": grilla_mas_perdida,
        "TABLA_COMPLETA": os.path.relpath(csv_trans, OUTPUTS_BASE),
        "COMPARACION_COBERTURAS": os.path.relpath(map_path, OUTPUTS_BASE),
        "COMPARACION_S2": os.path.relpath(mapa_s2_path, OUTPUTS_BASE),
        "MAPA_SENTINEL_INTERACTIVO": os.path.relpath(sentinel_html, OUTPUTS_BASE),
        "MAPA_DW_INTERACTIVO": os.path.relpath(dw_html, OUTPUTS_BASE)
    }


# === FLUJO PRINCIPAL ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de análisis Dynamic World por semestre")
    parser.add_argument("--semestre", type=str, required=True, help="Semestre: I o II")
    parser.add_argument("--anio", type=int, required=True, help="Año en formato YYYY")
    args = parser.parse_args()

    CURRENT_DATE, DATE_BEFORE = get_semester_dates(args.semestre, args.anio)

    print("🔍 Buscando archivos de páramos en:", AOI_DIR)
    geojson_files = [
        os.path.join(AOI_DIR, f)
        for f in os.listdir(AOI_DIR)
        if f.startswith("paramo_") and f.endswith(".geojson")
    ]

    if not geojson_files:
        print("❌ No se encontraron archivos de páramos en:", AOI_DIR)
        exit(1)

    print(f"✅ {len(geojson_files)} AOI encontrados:")
    for f in geojson_files:
        print(" -", os.path.basename(f))

    # === Procesar todos los AOI ===
    paramos_list = []
    for aoi_path in geojson_files:
        result = process_aoi(aoi_path, DATE_BEFORE, CURRENT_DATE, args.anio, args.semestre)
        paramos_list.append(result)

    # === Construir JSON final ===
    json_final = {
        "SEMESTRE": args.semestre,
        "ANIO": args.anio,
        "LOGO": LOGO_PATH,
        "PARAMOS": paramos_list,
    }

    json_path = os.path.join(OUTPUTS_BASE, f"reporte_paramos_{args.anio}_{args.semestre}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_final, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON final guardado en: {json_path}")

    # === Renderizar reporte HTML ===
    TPL_PATH = Path("dynamic_world/reporte/report_template.html")
    OUT_PATH = Path(OUTPUTS_BASE) / f"reporte_paramos_{args.anio}_{args.semestre}.html"
    render(TPL_PATH, Path(json_path), OUT_PATH)

    print("✅ Reporte HTML generado:", OUT_PATH)

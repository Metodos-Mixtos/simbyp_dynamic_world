#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from src.config import AOI_DIR, OUTPUTS_BASE, HEADER_IMG1_PATH, HEADER_IMG2_PATH, FOOTER_IMG_PATH, GRID_SIZE, LOOKBACK_DAYS
from src.dw_utils import get_dynamic_world_image, compute_transitions
from src.maps_utils import generate_maps
from src.reports.render_report import render
from src.aux_utils import log, save_json, create_grid
from datetime import datetime
import locale

# Setear locale a español para nombres de meses
try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except:
    locale.setlocale(locale.LC_TIME, "es_CO.UTF-8")
    
def process_aoi(aoi_path, date_before, current_date, anio, mes, out_dir):
    aoi_name = os.path.splitext(os.path.basename(aoi_path))[0]
    log(f"Procesando AOI: {aoi_name}", "info")

    # Crear rutas de las salidas
    paths = {k: os.path.join(out_dir, aoi_name, k) for k in ["grilla", "imagenes", "comparacion", "mapas"]}
    for p in paths.values():
        os.makedirs(p, exist_ok=True)

    # Crear grilla de análisis si no existe
    grid_path = os.path.join(paths["grilla"], f"grid_{aoi_name}_{GRID_SIZE}m.geojson")
    if not os.path.exists(grid_path):
        grid = create_grid(aoi_path, GRID_SIZE)
        grid.to_file(grid_path, driver="GeoJSON")

    # Crear capas de DW y calcular transiciones
    dw_before = get_dynamic_world_image(aoi_path, date_before)
    dw_current = get_dynamic_world_image(aoi_path, current_date)
    df_trans = compute_transitions(dw_before, dw_current, grid_path)
    
    # === Estadísticas agregadas ===
    total_perdida_bosque = df_trans["n_1_a_otro"].sum()
    total_perdida_matorral = df_trans["n_5_a_otro_no1"].sum()

        # Grilla con mayor pérdida de bosque
    if total_perdida_bosque > 0:
        fila_bosque_max = df_trans.loc[df_trans["n_1_a_otro"].idxmax()]
        grilla_max_bosque = int(fila_bosque_max["grid_id"])
        perdida_bosque_max = round(fila_bosque_max["n_1_a_otro"] * 0.01, 2)
    else:
        grilla_max_bosque, perdida_bosque_max = None, 0

        # Grilla con mayor cambio de matorral
    if total_perdida_matorral > 0:
        fila_mat_max = df_trans.loc[df_trans["n_5_a_otro_no1"].idxmax()]
        grilla_max_mat = int(fila_mat_max["grid_id"])
        perdida_mat_max = round(fila_mat_max["n_5_a_otro_no1"] * 0.01, 2)
    else:
        grilla_max_mat, perdida_mat_max = None, 0

    # Guardar transiciones a CSV
    csv_path = os.path.join(paths["comparacion"], f"{aoi_name}_transiciones.csv")
    df_trans.to_csv(csv_path, index=False)

    #sentinel_tif = os.path.join(paths["imagenes"], f"sentinel_rgb_{date_before}_a_{current_date}.tif")
    #if not os.path.exists(sentinel_tif):
        #download_sentinel_rgb_period(grid_path, date_before, current_date, sentinel_tif)

    # Generar mapas
    maps_info = generate_maps(
        aoi_path,
        grid_path,
        paths["mapas"],
        date_before,
        current_date,
        anio,
        month_str,      
        LOOKBACK_DAYS,
        dw_before=dw_before,
        dw_current=dw_current
    )
    
    # Hacer rutas relativas al archivo HTML principal del periodo
    relative_maps = {
        k: os.path.relpath(v, start=out_dir)
        for k, v in maps_info.items()
    }

    # Generar resultado final
    result = {
        "NOMBRE_PARAMO": aoi_name.replace("_", " ").title(),
        "PERDIDA_BOSQUE_PARAMOS": round(total_perdida_bosque * 0.01, 2),
        "GRILLA_CON_MAS_PERDIDA": grilla_max_bosque,
        "PERDIDA_BOSQUE_GRILLA_1": perdida_bosque_max,
        "PERDIDA_MATORRAL_PARAMOS":round(total_perdida_matorral * 0.01, 2),
        "GRILLA_CON_MAS_CAMBIO_5": grilla_max_mat,
        "PERDIDA_MATORRAL_GRILLA_1": perdida_mat_max,
        **relative_maps
    }

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de análisis Dynamic World interanual por mes")
    parser.add_argument("--anio", type=int, required=True, help="Año en formato YYYY (por ejemplo, 2025)")
    parser.add_argument("--mes", type=int, required=True, help="Mes en formato 1–12")
    args = parser.parse_args()
    month_str = datetime(args.anio, args.mes, 1).strftime("%B").capitalize()

    #current_date, date_before = get_semester_dates(args.semestre, args.anio)
    current_date = datetime(args.anio, args.mes, 1).strftime("%Y-%m-%d")
    date_before = datetime(args.anio - 1, args.mes, 1).strftime("%Y-%m-%d")
    
    log(f"📆 Comparando {month_str} {args.anio - 1} ↔ {month_str} {args.anio}", "info")

    period_dir = os.path.join(OUTPUTS_BASE, f"{args.anio}_{args.mes}")
    os.makedirs(period_dir, exist_ok=True)

    geojson_files = [os.path.join(AOI_DIR, f) for f in os.listdir(AOI_DIR) if f.startswith("paramo_")]
    results = [process_aoi(p, date_before, current_date, args.anio, args.mes, period_dir) for p in geojson_files]
    
    # Convertir rutas de imágenes a relativas respecto al HTML
    header_img1_rel = os.path.relpath(HEADER_IMG1_PATH, start=period_dir)
    header_img2_rel = os.path.relpath(HEADER_IMG2_PATH, start=period_dir)
    footer_img_rel = os.path.relpath(FOOTER_IMG_PATH, start=period_dir)

    json_final = {
        "MES": month_str,
        "ANIO": args.anio,
        "HEADER_IMG1": header_img1_rel,
        "HEADER_IMG2": header_img2_rel,
        "FOOTER_IMG": footer_img_rel,
        "PARAMOS": results
    }

    json_path = os.path.join(period_dir, f"reporte_paramos_{args.anio}_{args.mes}.json")
    save_json(json_final, json_path)

    BASE_DIR = Path(__file__).resolve().parent
    tpl_path = BASE_DIR / "src" / "reports" / "report_template.html"

    render(Path(tpl_path), Path(json_path), Path(os.path.join(period_dir, f"reporte_paramos_{args.anio}_{args.mes}.html")))
    log("Reporte HTML generado correctamente.", "success")

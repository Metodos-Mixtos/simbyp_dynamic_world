#!/usr/bin/env python3
import argparse
import os
import shutil
from pathlib import Path
from src.config import AOI_DIR, OUTPUTS_BASE, HEADER_IMG1_PATH, HEADER_IMG2_PATH, FOOTER_IMG_PATH, GRID_SIZE, LOOKBACK_DAYS, USE_GCS, GCS_BUCKET_NAME, GCS_OUTPUTS_BASE, GCS_PREFIX
from src.dw_utils import get_dynamic_world_image, compute_transitions
from src.maps_utils import generate_maps
from src.reports.render_report import render
from src.aux_utils import log, save_json, create_grid
from src.gcs_utils import upload_directory_to_gcs, upload_file_to_gcs, get_public_url, image_to_base64
from datetime import datetime
import locale
import gcsfs

# Setear locale a español para nombres de meses
try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except:
    locale.setlocale(locale.LC_TIME, "es_CO.UTF-8")
    
def process_aoi(aoi_path, date_before, current_date, anio, mes, out_dir, period_name):
    aoi_name = os.path.splitext(os.path.basename(aoi_path))[0]
    log(f"Procesando AOI: {aoi_name}", "info")

    # Crear rutas de las salidas (locales temporales)
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
    
    # Si está habilitado GCS, subir archivos
    if USE_GCS:
        log(f"📤 Subiendo {aoi_name} a GCS...", "info")
        gcs_prefix = f"{GCS_PREFIX}/{period_name}/{aoi_name}"
        local_aoi_dir = os.path.join(out_dir, aoi_name)
        
        # Subir todo el directorio del AOI
        uploaded = upload_directory_to_gcs(local_aoi_dir, GCS_BUCKET_NAME, gcs_prefix)
        
        # Convertir rutas de mapas a URLs públicas
        relative_maps = {}
        for k, local_path in maps_info.items():
            # Calcular blob_name basado en la estructura de archivos
            rel_to_aoi = os.path.relpath(local_path, local_aoi_dir).replace("\\", "/")
            blob_name = f"{gcs_prefix}/{rel_to_aoi}"
            relative_maps[k] = get_public_url(GCS_BUCKET_NAME, blob_name)
    else:
        # Hacer rutas relativas al archivo HTML principal del periodo
        relative_maps = {
            k: os.path.relpath(v, start=out_dir)
            for k, v in maps_info.items()
        }

    # Generar resultado final
    # Remover prefijo "paramo_" y formatear nombre
    nombre_limpio = aoi_name.replace("paramo_", "").replace("_", " ").title()
    result = {
        "NOMBRE_PARAMO": nombre_limpio,
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

    period_name = f"{args.anio}_{args.mes}"
    period_dir = os.path.join(OUTPUTS_BASE, period_name)
    os.makedirs(period_dir, exist_ok=True)

    # Listar archivos GeoJSON desde GCS o local
    if AOI_DIR.startswith("gs://"):
        fs = gcsfs.GCSFileSystem()
        aoi_dir_clean = AOI_DIR.replace("gs://", "")
        all_files = fs.ls(aoi_dir_clean)
        geojson_files = [f"gs://{f}" for f in all_files if f.endswith(".geojson") and "paramo_" in f]
    else:
        geojson_files = [os.path.join(AOI_DIR, f) for f in os.listdir(AOI_DIR) if f.startswith("paramo_")]
    
    results = [process_aoi(p, date_before, current_date, args.anio, args.mes, period_dir, period_name) for p in geojson_files]
    
    # Convertir logos a base64 (funciona tanto para GCS como local)
    log("🖼 Convirtiendo logos a base64...", "info")
    header_img1_b64 = image_to_base64(HEADER_IMG1_PATH)
    header_img2_b64 = image_to_base64(HEADER_IMG2_PATH)
    footer_img_b64 = image_to_base64(FOOTER_IMG_PATH)
    
    # Generar JSON y HTML localmente con logos en base64
    json_final = {
        "MES": month_str,
        "ANIO": args.anio,
        "HEADER_IMG1": header_img1_b64,
        "HEADER_IMG2": header_img2_b64,
        "FOOTER_IMG": footer_img_b64,
        "PARAMOS": results
    }

    json_path = os.path.join(period_dir, f"reporte_paramos_{args.anio}_{args.mes}.json")
    save_json(json_final, json_path)

    BASE_DIR = Path(__file__).resolve().parent
    tpl_path = BASE_DIR / "src" / "reports" / "report_template.html"
    html_path = os.path.join(period_dir, f"reporte_paramos_{args.anio}_{args.mes}.html")

    render(Path(tpl_path), Path(json_path), Path(html_path))
    log("Reporte HTML generado correctamente.", "success")
    
    # Subir reporte final a GCS
    if USE_GCS:
        log("📤 Subiendo reporte final a GCS...", "info")
        json_blob = f"{GCS_PREFIX}/{period_name}/reporte_paramos_{args.anio}_{args.mes}.json"
        html_blob = f"{GCS_PREFIX}/{period_name}/reporte_paramos_{args.anio}_{args.mes}.html"
        
        upload_file_to_gcs(json_path, GCS_BUCKET_NAME, json_blob)
        upload_file_to_gcs(html_path, GCS_BUCKET_NAME, html_blob)
        
        final_url = get_public_url(GCS_BUCKET_NAME, html_blob)
        log(f"✅ Reporte disponible en: {final_url}", "success")
        
        # Limpiar archivos temporales
        log("🧹 Limpiando archivos temporales...", "info")
        try:
            shutil.rmtree(period_dir)
        except PermissionError:
            # En Windows, algunos archivos pueden quedar bloqueados
            log("⚠️ No se pudieron eliminar algunos archivos temporales (archivos en uso)", "warning")
    else:
        log(f"✅ Reporte guardado en: {html_path}", "success")

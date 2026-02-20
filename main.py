#!/usr/bin/env python3
import argparse
import os
import shutil
from pathlib import Path
from src.config import AOI_DIR, OUTPUTS_BASE, HEADER_IMG1_PATH, HEADER_IMG2_PATH, FOOTER_IMG_PATH, GRID_SIZE, LOOKBACK_DAYS, USE_GCS, GCS_BUCKET_NAME, GCS_OUTPUTS_BASE, GCS_PREFIX, get_paramo_geojson
from src.dw_utils import get_dynamic_world_image, compute_transitions
from src.maps_utils import generate_maps
from src.reports.render_report import render
from src.aux_utils import log, save_json, create_grid
from src.gcs_utils import upload_directory_to_gcs, upload_file_to_gcs, get_public_url, image_to_base64
from src.png_map import generar_mapa_png
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


    # Crear estructura de carpetas para cada páramo
    base_dir = os.path.join(out_dir, aoi_name)
    mapas_dir = os.path.join(base_dir, "mapas")
    imagenes_dir = os.path.join(mapas_dir, "imagenes")
    dw_dir = os.path.join(imagenes_dir, "dw")
    sentinel_dir = os.path.join(imagenes_dir, "sentinel")
    for d in [base_dir, mapas_dir, imagenes_dir, dw_dir, sentinel_dir]:
        os.makedirs(d, exist_ok=True)
    paths = {
        "grilla": os.path.join(base_dir, "grilla"),
        "imagenes": imagenes_dir,
        "comparacion": os.path.join(base_dir, "comparacion"),
        "mapas": mapas_dir
    }
    for p in paths.values():
        os.makedirs(p, exist_ok=True)

    # Copiar AOI base local a la carpeta del páramo si no existe (tanto en grilla como en la raíz del páramo)
    from src.config import LOCAL_AOI
    aoi_base_name = os.path.basename(aoi_path)
    aoi_local_path = os.path.join(LOCAL_AOI, aoi_base_name)
    aoi_target_grilla = os.path.join(paths["grilla"], aoi_base_name)
    aoi_target_root = os.path.join(out_dir, aoi_name, aoi_base_name)
    import shutil
    for target in [aoi_target_grilla, aoi_target_root]:
        if not os.path.exists(target) and os.path.exists(aoi_local_path):
            shutil.copy2(aoi_local_path, target)
            log(f"AOI local copiado a: {target}", "info")

    # Crear grilla de análisis si no existe
    grid_path = os.path.join(paths["grilla"], f"grid_{aoi_name}_{GRID_SIZE}m.geojson")
    if not os.path.exists(grid_path):
        grid = create_grid(aoi_path, GRID_SIZE)
        grid.to_file(grid_path, driver="GeoJSON")
    # Si la grilla está vacía, asegúrate de que el AOI base esté en la carpeta raíz y en grilla
    try:
        import geopandas as gpd
        gdf_grid = gpd.read_file(grid_path)
        if gdf_grid.empty:
            log(f"[WARN] Grilla vacía para {aoi_name}. Se usará el polígono del AOI para overlays.", "warning")
    except Exception as e:
        log(f"[ERROR] No se pudo leer la grilla para {aoi_name}: {e}", "error")

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

    # Generar PNGs por grilla y mapas interactivos
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
    # Generar mapas interactivos con overlays PNG (DW y Sentinel) usando la nueva estructura
    try:
        # DW
        generar_mapa_png(
            paramo=aoi_name,
            periodo=current_date,
            tipo="dw",
            grilla_path=Path(grid_path),
            imagenes_dir=Path(paths["mapas"]) / "imagenes",
            output_html=Path(paths["mapas"]) / "dw_mes.html"
        )
        # Sentinel
        generar_mapa_png(
            paramo=aoi_name,
            periodo=current_date,
            tipo="sentinel",
            grilla_path=Path(grid_path),
            imagenes_dir=Path(paths["mapas"]) / "imagenes",
            output_html=Path(paths["mapas"]) / "sentinel_mes.html"
        )
        # Si la grilla está vacía, también intentar generar overlays sobre el AOI base
        if gdf_grid.empty:
            for tipo in ["dw", "sentinel"]:
                for periodo_x, html_name in zip([current_date, f"{int(current_date[:4])-1}-{current_date[5:]}"], ["dw_mes.html", "sentinel_mes.html"]):
                    from pathlib import Path
                    imagenes_dir = Path(paths["mapas"]) / "imagenes"
                    aoi_geojson = Path(paths["grilla"]) / f"{aoi_name}.geojson"
                    if tipo == "dw":
                        img_dir = imagenes_dir / "dw"
                        png_filename = f"dw_aoi_{periodo_x}.png"
                    else:
                        img_dir = imagenes_dir / "sentinel"
                        png_filename = f"sentinel_aoi_{periodo_x}.png"
                    png_path = img_dir / png_filename
                    if not png_path.exists() and aoi_geojson.exists():
                        log(f"[INFO] Falta PNG para AOI {aoi_name} periodo {periodo_x} tipo {tipo}. Debes generarlo manualmente o automatizar la exportación.", "warning")
    except Exception as e:
        log(f"[ERROR] No se pudo generar el mapa interactivo PNG para {aoi_name}: {e}", "error")

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
        "PERDIDA_MATORRAL_PARAMOS": round(total_perdida_matorral * 0.01, 2),
        "GRILLA_CON_MAS_CAMBIO_5": grilla_max_mat,
        "PERDIDA_MATORRAL_GRILLA_1": perdida_mat_max,
        "MAPA_DW_INTERACTIVO": relative_maps.get("MAPA_DW_INTERACTIVO", ""),
        "MAPA_SENTINEL_INTERACTIVO": relative_maps.get("MAPA_SENTINEL_INTERACTIVO", "")
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

    # Limpieza solo del periodo actual antes de procesar
    period_name = f"{args.anio}_{args.mes}"
    period_dir = os.path.join(OUTPUTS_BASE, period_name)
    # Limpieza solo del periodo actual antes de procesar, forzando permisos de escritura
    import stat
    def on_rm_error(func, path, exc_info):
        import os
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            print(f"[WARN] No se pudo borrar {path}: {e}")
    if os.path.exists(period_dir):
        import shutil
        print(f"[INFO] Limpiando carpeta del periodo: {period_dir}")
        shutil.rmtree(period_dir, onerror=on_rm_error)
    os.makedirs(period_dir, exist_ok=True)

    # Listar archivos GeoJSON desde GCS o local
    # Listar nombres base de páramos (sin extensión)
    if AOI_DIR.startswith("gs://"):
        fs = gcsfs.GCSFileSystem()
        aoi_dir_clean = AOI_DIR.replace("gs://", "")
        all_files = fs.ls(aoi_dir_clean)
        paramo_names = [os.path.splitext(os.path.basename(f))[0] for f in all_files if f.endswith(".geojson") and "paramo_" in f]
        geojson_files = [f"gs://{aoi_dir_clean}/{name}.geojson" for name in paramo_names]
    else:
        paramo_names = [os.path.splitext(f)[0] for f in os.listdir(AOI_DIR) if f.startswith("paramo_")]
        geojson_files = [get_paramo_geojson(name) for name in paramo_names]
    
    results = []
    for p in geojson_files:
        try:
            results.append(process_aoi(p, date_before, current_date, args.anio, args.mes, period_dir, period_name))
        except Exception as e:
            log(f"[ERROR] Falló el procesamiento de {p}: {e}", "error")

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

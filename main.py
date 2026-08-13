#!/usr/bin/env python3
import argparse
import os
import shutil
from pathlib import Path
from datetime import datetime
import locale
import pandas as pd

# === CRITICAL: Configure SSL/TLS for paths with special characters ===
# This MUST be done BEFORE importing google.cloud or gcsfs modules
try:
    import certifi
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    os.environ['CURL_CA_BUNDLE'] = certifi.where()
except Exception as e:
    print(f"⚠ Warning: Could not configure SSL certificates: {e}")

from src.config import AOI_DIR, OUTPUTS_BASE, HEADER_IMG1_PATH, HEADER_IMG2_PATH, FOOTER_IMG_PATH, GRID_SIZE, LOOKBACK_DAYS, USE_GCS, GCS_BUCKET_NAME, GCS_OUTPUTS_BASE, GCS_PREFIX, get_paramo_geojson, download_altiplano_aoi_from_gcs
from src.dw_utils import get_dynamic_world_image, compute_transitions, get_alert_grids, generate_coverage_csv
from src.maps_utils import generate_maps
from src.png_map import get_display_grid_id
from src.reports.render_report import render
from src.aux_utils import log, save_json, create_grid
from src.gcs_utils import upload_directory_to_gcs, upload_file_to_gcs, get_public_url, image_to_base64


def download_aois_from_gcs_to_local(aoi_dir_gs, cache_dir):
    """Descarga AOIs paramo_*.geojson desde GCS a una carpeta local temporal."""
    from google.cloud import storage

    aoi_dir_clean = aoi_dir_gs.replace("gs://", "", 1)
    bucket_name, prefix = aoi_dir_clean.split("/", 1)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    client = storage.Client()
    blobs = client.list_blobs(bucket_name, prefix=prefix)

    local_files = []
    for blob in blobs:
        name = os.path.basename(blob.name)
        if not (name.startswith("paramo_") and name.endswith(".geojson")):
            continue

        local_path = cache_dir / name
        blob.download_to_filename(str(local_path))
        local_files.append(str(local_path))

    return sorted(local_files)

# Setear locale a español para nombres de meses
try:
    locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
except:
    locale.setlocale(locale.LC_TIME, "es_CO.UTF-8")
    
def process_aoi(aoi_path, date_before, current_date, anio, mes, out_dir, period_name, custom_message=None):
    aoi_name = os.path.splitext(os.path.basename(aoi_path))[0]
    log(f"Procesando AOI: {aoi_name}", "info")

    gcs_prefix = f"{GCS_PREFIX}/{period_name}/{aoi_name}"
    image_base_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{gcs_prefix}/mapas/imagenes" if USE_GCS else None


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

    # Guardar transiciones a CSV
    csv_path = os.path.join(paths["comparacion"], f"{aoi_name}_transiciones.csv")
    df_trans.to_csv(csv_path, index=False)
    
    # Generar CSV de coberturas (clases DW en t1 y t2, índices de Sentinel)
    csv_coverage_path = os.path.join(paths["comparacion"], f"{aoi_name}_coberturas.csv")
    df_coverage = pd.DataFrame()
    try:
        df_coverage = generate_coverage_csv(dw_before, dw_current, grid_path, date_before, current_date, csv_coverage_path)
    except Exception as e:
        log(f"⚠️ Error generando CSV de coberturas para {aoi_name}: {e}", "warning")

    # === Estadísticas agregadas ===
    # 1 píxel DW = 10m x 10m = 100 m2 = 0.01 ha
    total_perdida_bosque = float(df_trans["n_1_a_otro"].sum()) if not df_trans.empty else 0.0
    total_perdida_matorral = float(df_trans["n_5_a_otro_no1"].sum()) if not df_trans.empty else 0.0
    total_perdida_bosque_ha = round(total_perdida_bosque * 0.01, 2)
    total_perdida_matorral_ha = round(total_perdida_matorral * 0.01, 2)

    # Grilla con mayor área de transición (hectáreas)
    if not df_trans.empty and total_perdida_bosque > 0:
        fila_bosque_max = df_trans.loc[df_trans["n_1_a_otro"].idxmax()]
        grid_id_bosque = int(fila_bosque_max["grid_id"])
        grilla_max_bosque = get_display_grid_id(grid_id_bosque, aoi_name)
        perdida_bosque_max = round(float(fila_bosque_max["n_1_a_otro"]) * 0.01, 2)
    else:
        grilla_max_bosque, perdida_bosque_max = None, 0.0

    if not df_trans.empty and total_perdida_matorral > 0:
        fila_mat_max = df_trans.loc[df_trans["n_5_a_otro_no1"].idxmax()]
        grid_id_mat = int(fila_mat_max["grid_id"])
        grilla_max_mat = get_display_grid_id(grid_id_mat, aoi_name)
        perdida_mat_max = round(float(fila_mat_max["n_5_a_otro_no1"]) * 0.01, 2)
    else:
        grilla_max_mat, perdida_mat_max = None, 0.0

    def _pp_direction(pp_value):
        if pp_value > 0:
            return "aumento"
        if pp_value < 0:
            return "disminución"
        return "sin cambio"

    def _pp_grid_metric(class_num, use_abs_max=False):
        col = f"pp_class_{class_num}"
        if df_coverage.empty or "grid_id" not in df_coverage.columns or col not in df_coverage.columns:
            return None, 0.0, "sin cambio", 0.0

        pp_series = pd.to_numeric(df_coverage[col], errors="coerce").fillna(0.0)
        if pp_series.empty:
            return None, 0.0, "sin cambio", 0.0

        target_idx = pp_series.abs().idxmax() if use_abs_max else pp_series.idxmin()
        pp_value = float(pp_series.loc[target_idx])
        grid_id = int(df_coverage.loc[target_idx, "grid_id"])
        grid_display = get_display_grid_id(grid_id, aoi_name)

        return grid_display, round(abs(pp_value), 2), _pp_direction(pp_value), round(pp_value, 2)

    is_altiplano = "altiplano" in aoi_name.lower()

    if is_altiplano:
        grid_pp_bosque, pp_bosque_abs, pp_bosque_dir, pp_bosque_raw = _pp_grid_metric(1, use_abs_max=True)
        grid_pp_mat, pp_mat_abs, pp_mat_dir, pp_mat_raw = _pp_grid_metric(5, use_abs_max=True)

        resumen_bosque_pp_txt = (
            f"La grilla con mayor cambio de bosque fue la {grid_pp_bosque}, con un {pp_bosque_dir} "
            f"de {pp_bosque_abs} p.p."
            if grid_pp_bosque is not None
            else "No fue posible calcular pp_class_1 para este páramo en el periodo analizado."
        )

        resumen_matorral_pp_txt = (
            f"La grilla con mayor cambio de arbustos y matorrales fue la {grid_pp_mat}, con un {pp_mat_dir} "
            f"de {pp_mat_abs} p.p."
            if grid_pp_mat is not None
            else "No fue posible calcular pp_class_5 para este páramo en el periodo analizado."
        )
    else:
        grid_pp_bosque, pp_bosque_abs, pp_bosque_dir, pp_bosque_raw = _pp_grid_metric(1, use_abs_max=False)
        grid_pp_mat, pp_mat_abs, pp_mat_dir, pp_mat_raw = _pp_grid_metric(5, use_abs_max=False)

        if grid_pp_bosque is not None and pp_bosque_raw < 0:
            resumen_bosque_pp_txt = (
                f"La grilla con mayor pérdida de bosque fue la {grid_pp_bosque}, "
                f"con una disminución de {pp_bosque_abs} p.p."
            )
        elif grid_pp_bosque is not None:
            resumen_bosque_pp_txt = (
                f"No se observaron pérdidas netas en pp_class_1 para este páramo. "
                f"El valor mínimo se presentó en la grilla {grid_pp_bosque} con {pp_bosque_raw} p.p."
            )
        else:
            resumen_bosque_pp_txt = "No fue posible calcular pp_class_1 para este páramo en el periodo analizado."

        if grid_pp_mat is not None and pp_mat_raw < 0:
            resumen_matorral_pp_txt = (
                f"La grilla con mayor pérdida de arbustos y matorrales fue la {grid_pp_mat}, "
                f"con una disminución de {pp_mat_abs} p.p."
            )
        elif grid_pp_mat is not None:
            resumen_matorral_pp_txt = (
                f"No se observaron pérdidas netas en pp_class_5 para este páramo. "
                f"El valor mínimo se presentó en la grilla {grid_pp_mat} con {pp_mat_raw} p.p."
            )
        else:
            resumen_matorral_pp_txt = "No fue posible calcular pp_class_5 para este páramo en el periodo analizado."

    resumen_bosque_ha_txt = (
        f"En {month_str} de {anio}, {total_perdida_bosque_ha} hectáreas del páramo {aoi_name.replace('paramo_', '').replace('_', ' ').title()}, "
        "que previamente estaban clasificadas como bosque, cambiaron de cobertura."
    )
    resumen_matorral_ha_txt = (
        f"Por otro lado, {total_perdida_matorral_ha} hectáreas de áreas clasificadas como arbustos y matorrales "
        "cambiaron a otras coberturas del suelo distintas a la categoría de árboles. "
        "Cabe recordar que esta clase corresponde a la vegetación típica de los páramos, como los frailejones "
        "(Murad, 2024)."
    )

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
        dw_current=dw_current,
        df_transitions=df_trans,
        aoi_name=aoi_name,  # Pasar nombre del AOI para lógica de Altiplano
        image_base_url=image_base_url
    )
    
    # === Seleccionar grillas para alertar (enfoque híbrido) ===
    alert_grids_df, alert_grid_ids = get_alert_grids(df_trans, aoi_name)
    alert_grid_count = int(maps_info.get("ALERT_GRID_COUNT", len(alert_grid_ids or [])))
    mensaje = custom_message or "Para este periodo no se detectaron alertas bajo esta metodología."
    
    # Los mapas interactivos ya se generan dentro de generate_maps() con los overlays PNG

    # Si está habilitado GCS, subir archivos
    if USE_GCS:
        log(f"📤 Subiendo {aoi_name} a GCS...", "info")
        local_aoi_dir = os.path.join(out_dir, aoi_name)
        
        # Subir todo el directorio del AOI
        uploaded = upload_directory_to_gcs(local_aoi_dir, GCS_BUCKET_NAME, gcs_prefix)
        
        # Convertir rutas de mapas a URLs públicas
        relative_maps = {}
        for k, local_path in maps_info.items():
            if not isinstance(local_path, (str, Path)):
                continue
            # Calcular blob_name basado en la estructura de archivos
            rel_to_aoi = os.path.relpath(local_path, local_aoi_dir).replace("\\", "/")
            blob_name = f"{gcs_prefix}/{rel_to_aoi}"
            relative_maps[k] = get_public_url(GCS_BUCKET_NAME, blob_name)
        table_url = get_public_url(
            GCS_BUCKET_NAME,
            f"{gcs_prefix}/comparacion/{aoi_name}_coberturas.csv"
        )
    else:
        # Hacer rutas relativas al archivo HTML principal del periodo
        relative_maps = {
            k: os.path.relpath(v, start=out_dir)
            for k, v in maps_info.items()
            if isinstance(v, (str, Path))
        }
        table_url = os.path.relpath(csv_coverage_path, start=out_dir)

    # Generar resultado final
    # Remover prefijo "paramo_" y formatear nombre
    nombre_limpio = aoi_name.replace("paramo_", "").replace("_", " ").title()
    result = {
        "NOMBRE_PARAMO": nombre_limpio,
        "PERDIDA_BOSQUE_PARAMOS": total_perdida_bosque_ha,
        "GRILLA_CON_MAS_PERDIDA": grilla_max_bosque,
        "PERDIDA_BOSQUE_GRILLA_1": perdida_bosque_max,
        "PERDIDA_MATORRAL_PARAMOS": total_perdida_matorral_ha,
        "GRILLA_CON_MAS_CAMBIO_5": grilla_max_mat,
        "PERDIDA_MATORRAL_GRILLA_1": perdida_mat_max,
        "RESUMEN_BOSQUE_HA_TXT": resumen_bosque_ha_txt,
        "RESUMEN_BOSQUE_PP_TXT": resumen_bosque_pp_txt,
        "RESUMEN_MATORRAL_HA_TXT": resumen_matorral_ha_txt,
        "RESUMEN_MATORRAL_PP_TXT": resumen_matorral_pp_txt,
        "TABLA_COMPLETA": table_url,
        "ALERTA_SIN_GRILLAS": [{"MENSAJE_ALERTA": mensaje}] if alert_grid_count == 0 else [],
        "MOSTRAR_MAPA": [{"MAPA_COMBINADO_INTERACTIVO": relative_maps.get("MAPA_COMBINADO_INTERACTIVO", "")}] if alert_grid_count > 0 else [],
        "MAPA_COMBINADO_INTERACTIVO": relative_maps.get("MAPA_COMBINADO_INTERACTIVO", "")
    }

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de análisis Dynamic World interanual por mes")
    parser.add_argument("--anio", type=int, required=False, default=None, help="Año en formato YYYY (por ejemplo, 2025). Si no se especifica, usa el mes anterior al actual.")
    parser.add_argument("--mes", type=int, required=False, default=None, help="Mes en formato 1–12. Si no se especifica, usa el mes anterior al actual.")
    args = parser.parse_args()
    
    # Si no se especifican año y mes, calcular el mes anterior automáticamente
    if args.anio is None or args.mes is None:
        from datetime import timedelta
        today = datetime.now()
        first_of_current_month = today.replace(day=1)
        last_month = first_of_current_month - timedelta(days=1)
        anio = last_month.year
        mes = last_month.month
        log(f"⚠️ No se especificaron --anio y --mes. Usando mes anterior: {mes}/{anio}", "warning")
    else:
        anio = args.anio
        mes = args.mes
    
    month_str = datetime(anio, mes, 1).strftime("%B").capitalize()

    #current_date, date_before = get_semester_dates(args.semestre, args.anio)
    current_date = datetime(anio, mes, 1).strftime("%Y-%m-%d")
    date_before = datetime(anio - 1, mes, 1).strftime("%Y-%m-%d")
    
    log(f"📆 Comparando {month_str} {anio - 1} ↔ {month_str} {anio}", "info")

    # Limpieza solo del periodo actual antes de procesar
    period_name = f"{anio}_{mes}"
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

    # Descargar AOI de Altiplano desde GCS y guardarlo en la estructura local
    try:
        log("📥 Descargando AOI Altiplano desde GCS...", "info")
        download_altiplano_aoi_from_gcs(OUTPUTS_BASE, anio, mes)
    except Exception as e:
        log(f"[WARN] No se pudo descargar AOI Altiplano: {e}", "warning")
        log("⏭️ Continuando sin Altiplano...", "warning")

    # Listar AOIs priorizando archivos locales para evitar lecturas remotas con gcsfs/pyogrio en Windows.
    geojson_files = []
    local_aoi_candidates = [
        Path.cwd() / "AOIs",
        Path(__file__).resolve().parent / "AOIs",
        Path(__file__).resolve().parent.parent / "AOIs",
    ]

    local_aoi_dir = None
    for candidate in local_aoi_candidates:
        if candidate.exists() and any(candidate.glob("paramo_*.geojson")):
            local_aoi_dir = candidate
            break

    if local_aoi_dir is not None:
        geojson_files = sorted(str(p) for p in local_aoi_dir.glob("paramo_*.geojson"))
        log(f"📁 AOIs locales detectados: {local_aoi_dir}", "info")
    elif AOI_DIR.startswith("gs://"):
        # Fallback: descargar AOIs desde GCS a local para evitar lecturas directas gs:// con pyogrio.
        aoi_cache_dir = os.path.join(period_dir, "_aoi_cache")
        geojson_files = download_aois_from_gcs_to_local(AOI_DIR, aoi_cache_dir)
        if geojson_files:
            log(f"⚠️ AOIs locales no encontrados. AOIs descargados desde GCS a {aoi_cache_dir}", "warning")
        else:
            log("[ERROR] No se encontraron AOIs paramo_*.geojson en GCS.", "error")
    else:
        paramo_names = [os.path.splitext(f)[0] for f in os.listdir(AOI_DIR) if f.startswith("paramo_")]
        geojson_files = [get_paramo_geojson(name) for name in paramo_names]
    
    results = []
    for p in geojson_files:
        try:
            results.append(process_aoi(p, date_before, current_date, anio, mes, period_dir, period_name))
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
        "ANIO": anio,
        "HEADER_IMG1": header_img1_b64,
        "HEADER_IMG2": header_img2_b64,
        "FOOTER_IMG": footer_img_b64,
        "PARAMOS": results
    }

    json_path = os.path.join(period_dir, f"reporte_paramos_{anio}_{mes}.json")
    save_json(json_final, json_path)

    BASE_DIR = Path(__file__).resolve().parent
    tpl_path = BASE_DIR / "src" / "reports" / "report_template.html"
    html_path = os.path.join(period_dir, f"reporte_paramos_{anio}_{mes}.html")

    render(Path(tpl_path), Path(json_path), Path(html_path))
    log("Reporte HTML generado correctamente.", "success")
    
    # Subir reporte final a GCS
    if USE_GCS:
        log("📤 Subiendo reporte final a GCS...", "info")
        json_blob = f"{GCS_PREFIX}/{period_name}/reporte_paramos_{anio}_{mes}.json"
        html_blob = f"{GCS_PREFIX}/{period_name}/reporte_paramos_{anio}_{mes}.html"
        
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

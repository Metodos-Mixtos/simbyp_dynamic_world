"""
Pipeline de generación de mapas interactivos Folium con overlays PNG.
Genera PNGs de DW y Sentinel con threshold inteligente y HTMLs interactivos.
"""

import geemap
from src.aux_utils import log
import ee
import geopandas as gpd
import folium
import os
import pandas as pd
from pathlib import Path
import json
from src.config import PROJECT_ID
from PIL import Image
import numpy as np

def make_nas_transparent(png_path, image_type='sentinel'):
    """Hace NAs transparentes en imágenes PNG"""
    try:
        with Image.open(png_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            data = np.array(img)
            mask = (data[:,:,0] == 0) & (data[:,:,1] == 0) & (data[:,:,2] == 0)
            data[mask, 3] = 0
            result_img = Image.fromarray(data, 'RGBA')
            result_img.save(png_path)
    except Exception as e:
        log(f"Error transparencia en {png_path}: {e}", "warning")

def generate_maps(aoi_path, grid_path, map_dir, date_before, current_date, anio, mes, lookback_days, dw_before, dw_current, df_transitions=None, aoi_name=None):
    """
    Pipeline COMPLETO:
    1. Genera PNGs de DW y Sentinel con threshold 15%
    2. Genera HTMLs interactivos (dw_mes.html, sentinel_mes.html)
    
    Estructura en map_dir:
    ├── imagenes/
    │   ├── dw/
    │   └── sentinel/
    ├── dw_mes.html
    └── sentinel_mes.html
    """
    import shapely
    from src.png_map import generar_mapa_png
    
    log("="*70, "info")
    log(f"GENERANDO MAPAS: {aoi_name}", "info")
    log("="*70, "info")
    
    try:
        grid_gdf = gpd.read_file(grid_path).to_crs(epsg=4326)
        log(f"Grilla: {len(grid_gdf)} grids", "info")
    except Exception as e:
        log(f"ERROR grilla: {e}", "error")
        return {}
    
    from src.dw_utils import authenticate_gee
    authenticate_gee()
    
    # Crear carpetas
    dw_dir = Path(map_dir) / 'imagenes' / 'dw'
    sentinel_dir = Path(map_dir) / 'imagenes' / 'sentinel'
    dw_dir.mkdir(parents=True, exist_ok=True)
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    
    # Determinar qué grillas procesar (threshold 15%)
    threshold_pct = 15.0
    grids_to_process = set()
    
    if aoi_name and "altiplano" in aoi_name.lower():
        grids_to_process = set(grid_gdf["grid_id"].tolist())
        log(f"Altiplano: TODAS {len(grid_gdf)} grillas", "info")
    elif df_transitions is not None and not df_transitions.empty:
        mask = (df_transitions["pct_1_a_otro_clase1"] >= threshold_pct) | (df_transitions["pct_5_a_otro_no1_clase5"] >= threshold_pct)
        grids_to_process = set(df_transitions[mask]["grid_id"].tolist())
        log(f"Filtro >15%: {len(grids_to_process)}/{len(grid_gdf)} grillas", "info")
    else:
        grids_to_process = set(grid_gdf["grid_id"].tolist())
        log(f"Sin filtro: TODAS {len(grids_to_process)} grillas", "warning")
    
    # === PASO 1: GENERAR PNGs ===
    log("\n[1/3] Generando PNGs...", "info")
    png_count_dw = 0
    png_count_sentinel = 0
    
    for _, row in grid_gdf.iterrows():
        grid_id = row.get("grid_id", _)
        if grid_id not in grids_to_process:
            continue
        
        geom = row.geometry
        if geom.is_empty or geom.geom_type not in ["Polygon", "MultiPolygon"]:
            continue
        
        if geom.geom_type == "MultiPolygon":
            geom = shapely.ops.unary_union([p for p in geom.geoms if not p.is_empty])
        
        gdf_tmp = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        ee_geom = geemap.geopandas_to_ee(gdf_tmp).geometry()
        
        # DW T1 y T2
        for png_file, date_str, img_source in [
            (dw_dir / f"dw_grid_{grid_id}_{date_before}.png", date_before, dw_before),
            (dw_dir / f"dw_grid_{grid_id}_{current_date}.png", current_date, dw_current)
        ]:
            if not png_file.exists():
                try:
                    vis_params = {"min": 0, "max": 8, "palette": ["#419BDF", "#397D49", "#88B053", "#7A87C6", "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"]}
                    dw_img = img_source.clip(ee_geom).visualize(**vis_params)
                    geemap.download_ee_image(image=dw_img, filename=str(png_file), region=ee_geom, scale=10, crs="EPSG:4326", dtype="uint8")
                    if png_file.exists() and png_file.stat().st_size > 1000:
                        Image.open(png_file).verify()
                        make_nas_transparent(str(png_file), 'dw')
                        png_count_dw += 1
                    else:
                        png_file.unlink(missing_ok=True)
                except Exception as e:
                    pass
            else:
                png_count_dw += 1
        
        # Sentinel T1 y T2
        for png_file, date_str in [
            (sentinel_dir / f"sentinel_grid_{grid_id}_{date_before}.png", date_before),
            (sentinel_dir / f"sentinel_grid_{grid_id}_{current_date}.png", current_date)
        ]:
            if not png_file.exists():
                try:
                    date_start = ee.Date(date_str).advance(-lookback_days, "day")
                    date_end = ee.Date(date_str).advance(1, "day")
                    col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                        .filterDate(date_start, date_end) \
                        .filterBounds(ee_geom) \
                        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)) \
                        .select(["B4", "B3", "B2"])
                    if col.size().getInfo() > 0:
                        img = col.median().clip(ee_geom)
                        # Aplicar visualización para RGB natural: escalar uint16 a uint8
                        # Sentinel-2 SR: valores típicos 0-3000, escalamos a 0-255
                        vis_params = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]}
                        img_viz = img.visualize(**vis_params)
                        geemap.download_ee_image(image=img_viz, filename=str(png_file), region=ee_geom, scale=10, crs="EPSG:4326", dtype="uint8")
                        if png_file.exists() and png_file.stat().st_size > 1000:
                            Image.open(png_file).verify()
                            make_nas_transparent(str(png_file), 'sentinel')
                            png_count_sentinel += 1
                        else:
                            png_file.unlink(missing_ok=True)
                except Exception as e:
                    pass
            else:
                png_count_sentinel += 1
    
    log(f"PNGs: DW={png_count_dw}, Sentinel={png_count_sentinel}", "success")
    
    # === PASO 2: GENERAR MAPAS INTERACTIVOS ===
    log("\n[2/3] Generando HTMLs...", "info")
    
    alert_grid_ids = None
    if df_transitions is not None and not df_transitions.empty:
        mask = (df_transitions["pct_1_a_otro_clase1"] >= threshold_pct) | (df_transitions["pct_5_a_otro_no1_clase5"] >= threshold_pct)
        alert_grid_ids = df_transitions[mask]["grid_id"].tolist()
    
    for tipo, output_file in [("dw", "dw_mes.html"), ("sentinel", "sentinel_mes.html")]:
        try:
            log(f"  Intentando generar {output_file}...", "info")
            generar_mapa_png(
                paramo=aoi_name if aoi_name else "paramo",
                periodo=current_date,
                tipo=tipo,
                grilla_path=Path(grid_path),
                imagenes_dir=Path(map_dir) / "imagenes",
                output_html=Path(map_dir) / output_file,
                alert_grid_ids=alert_grid_ids
            )
            log(f"  OK: {output_file}", "success")
        except Exception as e:
            log(f"  ERROR {output_file}: {str(e)[:200]}", "error")
            import traceback
            tb = traceback.format_exc()
            log(f"  Traceback: {tb[:500]}", "error")

    
    log("="*70 + "\n", "info")
    
    return {
        "MAPA_SENTINEL_INTERACTIVO": str(Path(map_dir) / "sentinel_mes.html"),
        "MAPA_DW_INTERACTIVO": str(Path(map_dir) / "dw_mes.html"),
        "IMG_SENTINEL_PNG_DIR": str(sentinel_dir),
        "IMG_DW_PNG_DIR": str(dw_dir)
    }

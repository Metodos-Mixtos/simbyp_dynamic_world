import geopandas as gpd
import pandas as pd
import ee
import geemap
from shapely.ops import unary_union
from src.aux_utils import log
from src.config import LOOKBACK_DAYS, PROJECT_ID, ALERT_MIN_THRESHOLD_PCT, ALERT_TOP_N_GRIDS, ALERT_COMBINE_METRICS

def authenticate_gee():
    try:
        ee.Initialize(project=PROJECT_ID)
        log("Autenticado con Earth Engine.", "success")
    except Exception:
        log("Requiere autenticación manual...", "warning")
        ee.Authenticate()
        ee.Initialize(project=PROJECT_ID)
        log("Autenticación completada.", "success")

def get_dynamic_world_image(aoi_path, end_date, lookback_days=LOOKBACK_DAYS):
    authenticate_gee()
    gdf = gpd.read_file(aoi_path)
    minx, miny, maxx, maxy = gdf.total_bounds
    bbox = ee.Geometry.BBox(minx, miny, maxx, maxy)

    collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(ee.Date(end_date).advance(-lookback_days, "day"), ee.Date(end_date))
        .filterBounds(bbox)
        .select("label")
        .sort("system:time_start", False)
        .sort("system:index")
    )

    image = collection.mosaic().clip(bbox)
    log(f"Imagen DW cargada para {end_date}", "success")
    return image

def compute_transitions(dw_before, dw_current, grid_path):
    """
    Calcula, por celda de grilla, los cambios:
      - 1 -> cualquier clase distinta de 1
      - 5 -> cualquier clase distinta de 1 y 5

    Devuelve un DataFrame con:
      grid_id, n_validos,
      n_1_a_otro, n_5_a_otro_no1,
      pct_1_a_otro_clase1, pct_5_a_otro_no1_clase5
    """

    # === Cargar grilla y asegurar CRS ===
    grid_gdf = gpd.read_file(grid_path)
    grid_gdf = grid_gdf.to_crs(epsg=4326)
    results = []

    # === Preparar imágenes de cambio ===
    change_1 = dw_before.eq(1).And(dw_current.neq(1)).rename("change_1")
    change_5 = dw_before.eq(5).And(dw_current.neq(1)).And(dw_current.neq(5)).rename("change_5")
    class1_mask = dw_before.eq(1).rename("class1")
    class5_mask = dw_before.eq(5).rename("class5")
    valid_mask = dw_before.gte(0).And(dw_current.gte(0)).rename("valid")

    img_all = (
        change_1
        .addBands(change_5)
        .addBands(class1_mask)
        .addBands(class5_mask)
        .addBands(valid_mask)
    )

    # === Iterar sobre cada celda de la grilla ===
    for _, row in grid_gdf.iterrows():
        geom = row.geometry
        if geom.is_empty:
            continue
        if geom.geom_type == "MultiPolygon":
            geom = unary_union([p for p in geom.geoms if not p.is_empty])

        ee_geom = ee.Geometry(geom.__geo_interface__)

        try:
            # Validar si hay píxeles dentro de la celda
            count_valid = dw_before.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=ee_geom,
                scale=10,
                maxPixels=1e13
            ).getInfo()

            if not count_valid:
                log(f"⚠️ Grid {row.get('grid_id', '?')} sin píxeles válidos (fuera del área DW).", "warning")
                continue

            # Reducir regiones (sumar píxeles)
            stats = img_all.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=ee_geom,
                scale=10,
                maxPixels=1e13
            ).getInfo() or {}

            # Extraer valores por nombre de banda
            n_1_a_otro = stats.get("change_1", 0)
            n_5_a_otro_no1 = stats.get("change_5", 0)
            n_class1_before = stats.get("class1", 0)
            n_class5_before = stats.get("class5", 0)
            n_valid = stats.get("valid", 0)

            # Porcentajes relativos solo a las clases de origen
            pct_1_to_any_of_class1 = 100 * n_1_a_otro / n_class1_before if n_class1_before else 0
            pct_5_to_not1_of_class5 = 100 * n_5_a_otro_no1 / n_class5_before if n_class5_before else 0

        except Exception as e:
            log(f"⚠️ Error en grid {row.get('grid_id', '?')}: {e}", "warning")
            n_valid = n_1_a_otro = n_5_a_otro_no1 = 0
            pct_1_to_any_of_class1 = pct_5_to_not1_of_class5 = 0

        results.append({
            "grid_id": row.get("grid_id", _),
            "n_validos": n_valid,
            "n_1_a_otro": n_1_a_otro,
            "pct_1_a_otro_clase1": pct_1_to_any_of_class1,
            "n_5_a_otro_no1": n_5_a_otro_no1,
            "pct_5_a_otro_no1_clase5": pct_5_to_not1_of_class5
        })

    df = pd.DataFrame(results)
    log(f"✅ Transiciones calculadas: {len(df)} celdas procesadas.", "success")
    return df

def get_alert_grids(df_transitions, aoi_name, min_threshold=None, top_n=None, combine_metrics=None):
    """
    Filtra grillas para alertar basado en enfoque híbrido:
    - Selecciona los top N grillas que superen el umbral mínimo de cambio
    - Siempre retorna todas las grillas para 'paramo_altiplano' (caso especial)
    
    Args:
        df_transitions: DataFrame con columnas pct_1_a_otro_clase1 y pct_5_a_otro_no1_clase5
        aoi_name: nombre del AOI (ej: 'paramo_chingaza')
        min_threshold: porcentaje mínimo (ej: 15.0%). Si None, usa config
        top_n: número de top grillas a retornar (ej: 5). Si None, usa config
        combine_metrics: si True, combina ambas métricas. Si None, usa config
    
    Returns:
        pd.DataFrame: grillas seleccionadas (subset del df original)
        list: grid_ids de las grillas alertadas
    """
    min_threshold = min_threshold or ALERT_MIN_THRESHOLD_PCT
    top_n = top_n or ALERT_TOP_N_GRIDS
    combine_metrics = combine_metrics if combine_metrics is not None else ALERT_COMBINE_METRICS
    
    # Caso especial: Altiplano siempre alertar todas las grillas
    if "altiplano" in aoi_name.lower():
        log(f"📍 {aoi_name}: Generando mapas para TODAS las grillas (caso especial Altiplano)", "info")
        return df_transitions, df_transitions["grid_id"].tolist()
    
    # Para otros páramos: enfoque híbrido
    if df_transitions.empty:
        log(f"⚠️ {aoi_name}: Sin datos de transiciones", "warning")
        return pd.DataFrame(), []
    
    # Combinar métricas en un score único
    if combine_metrics:
        # Usar el máximo de ambas métricas como indicador de severidad
        df_transitions["alert_score"] = df_transitions[["pct_1_a_otro_clase1", "pct_5_a_otro_no1_clase5"]].max(axis=1)
    else:
        # Usar solo cambio de bosques
        df_transitions["alert_score"] = df_transitions["pct_1_a_otro_clase1"]
    
    # Filtrar por umbral mínimo
    df_above_threshold = df_transitions[df_transitions["alert_score"] >= min_threshold].copy()
    
    if df_above_threshold.empty:
        log(f"⚠️ {aoi_name}: No hay grillas por encima del umbral {min_threshold}%", "warning")
        # Si no hay grillas sobre el umbral, retornar vacío (no alertar)
        return pd.DataFrame(), []
    
    # Seleccionar top N sobre el umbral
    alert_grids = df_above_threshold.nlargest(top_n, "alert_score")
    alert_grid_ids = alert_grids["grid_id"].tolist()
    
    log(
        f"🚨 {aoi_name}: {len(alert_grids)} grillas alertadas (top {len(alert_grids)}/{top_n} > {min_threshold}%)\n"
        f"   Grillas: {alert_grid_ids}",
        "warning"
    )
    
    return alert_grids, alert_grid_ids
    authenticate_gee()
    gdf = gpd.read_file(aoi_path)
    minx, miny, maxx, maxy = gdf.total_bounds
    bbox = ee.Geometry.BBox(minx, miny, maxx, maxy)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start_date, end_date)
        .filterBounds(bbox)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .select(["B4", "B3", "B2"])
    )

    image = collection.median().clip(bbox)
    log(f"Descargando Sentinel-2 RGB {start_date}–{end_date}", "info")

    geemap.download_ee_image(
        image=image, filename=output_tif,
        region=bbox, scale=10, crs="EPSG:4326", dtype="uint16"
    )
    log(f"Imagen Sentinel-2 guardada en {output_tif}", "success")

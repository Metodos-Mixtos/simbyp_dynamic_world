import geopandas as gpd
import pandas as pd
import ee
import geemap
from shapely.ops import unary_union
from src.aux_utils import log
from src.config import LOOKBACK_DAYS, PROJECT_ID

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

def download_sentinel_rgb_period(aoi_path, start_date, end_date, output_tif):
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

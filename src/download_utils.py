import geopandas as gpd
import ee
import geemap
from datetime import datetime, timedelta
import os

def authenticate_gee():
    try:
        ee.Initialize(project='bosques-bogota-416214')
    except Exception:
        ee.Authenticate()
        ee.Initialize(project='bosques-bogota-416214')

def download_dynamic_world_latest(gdf_path: str, end_date: str, lookback_days: int, output_tif_path: str):
    authenticate_gee()

    # Calcular fecha de inicio
    end = ee.Date(end_date)
    start = end.advance(-lookback_days, "day")

    # Leer AOI desde la grilla
    gdf = gpd.read_file(gdf_path)

    # 🟩 SIMPLIFICAR: usar bounding box en lugar de geometría detallada
    minx, miny, maxx, maxy = gdf.total_bounds
    bbox = ee.Geometry.BBox(minx, miny, maxx, maxy)

    # Cargar colección DW
    collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterDate(start, end)
        .filterBounds(bbox)
        .select("label")
        .sort("system:time_start", False)
        .sort("system:index")
    )

    # Tomar el valor más reciente por píxel
    image = collection.mosaic().clip(bbox)

    print(
        f"🌍 Descargando imagen más reciente hasta {end_date} "
        f"(lookback {lookback_days} días) → {output_tif_path}"
    )

    geemap.download_ee_image(
        image=image,
        filename=output_tif_path,
        region=bbox,
        scale=10,
        crs="EPSG:4326",
        dtype="uint8",
    )

    if not os.path.exists(output_tif_path):
        raise RuntimeError(f"❌ Error: No se pudo guardar el archivo: {output_tif_path}")
    else:
        print(f"✅ Archivo guardado correctamente: {output_tif_path}")

def download_sentinel_rgb_period(gdf_path: str, start_date: str, end_date: str, output_tif_path: str):
    """
    Descarga una imagen Sentinel-2 RGB (B4, B3, B2) promedio para el periodo indicado.
    Usa la bounding box del GeoDataFrame para reducir tamaño del payload.
    """
    authenticate_gee()

    # Leer AOI desde la grilla
    gdf = gpd.read_file(gdf_path)
    minx, miny, maxx, maxy = gdf.total_bounds
    bbox = ee.Geometry.BBox(minx, miny, maxx, maxy)

    # Filtrar colección Sentinel-2 SR
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start_date, end_date)
        .filterBounds(bbox)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .select(["B4", "B3", "B2"])
    )

    # Promediar imágenes y recortar al área
    image = collection.median().clip(bbox)

    print(f"🛰️ Descargando imagen Sentinel-2 RGB para {start_date} a {end_date} → {output_tif_path}")

    geemap.download_ee_image(
        image=image,
        filename=output_tif_path,
        region=bbox,
        scale=10,
        crs="EPSG:4326",
        dtype="uint16"
    )

    if not os.path.exists(output_tif_path):
        raise RuntimeError(f"❌ Error: No se pudo guardar la imagen: {output_tif_path}")
    else:
        print(f"✅ Imagen Sentinel-2 guardada correctamente: {output_tif_path}")


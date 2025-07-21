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

def download_dynamic_world(grid_path: str, start_date: str, end_date: str, output_tif_path: str):
    authenticate_gee()

    # Leer grilla y crear geometría total
    grid = gpd.read_file(grid_path)
    aoi = grid.unary_union
    gdf = gpd.GeoDataFrame(geometry=[aoi], crs=grid.crs)
    aoi_ee = geemap.geopandas_to_ee(gdf)
    geometry = aoi_ee.geometry()

    # Preparar colección
    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1") \
        .filterDate(start_date, end_date) \
        .filterBounds(geometry)

    image = collection.select('label').mode().clip(geometry)

    print(f"🌍 Descargando imagen de {start_date} a {end_date} → {output_tif_path}")
    geemap.download_ee_image(
        image=image,
        filename=output_tif_path,
        region=geometry,
        scale=10,
        crs="EPSG:4326"
    )

    if not os.path.exists(output_tif_path):
        raise RuntimeError(f"❌ Error: No se pudo guardar el archivo: {output_tif_path}")
    else:
        print(f"✅ Archivo guardado correctamente: {output_tif_path}")



def download_dynamic_world_latest(grid_path: str, end_date: str, lookback_days: int, output_tif_path: str):
    authenticate_gee()

    # Calcular fecha de inicio
    end = ee.Date(end_date)
    start = end.advance(-lookback_days, 'day')

    # Leer AOI desde la grilla
    grid = gpd.read_file(grid_path)
    aoi = grid.unary_union
    gdf = gpd.GeoDataFrame(geometry=[aoi], crs=grid.crs)
    aoi_ee = geemap.geopandas_to_ee(gdf)
    geometry = aoi_ee.geometry()

    # Cargar colección DW
    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1") \
        .filterDate(start, end) \
        .filterBounds(geometry) \
        .select('label') \
        .sort('system:time_start', False).sort('system:index')

    # Tomar el valor más reciente por píxel
    image = collection.mosaic().clip(geometry)

    print(f"🌍 Descargando imagen más reciente hasta {end_date} (lookback {lookback_days} días) → {output_tif_path}")
    geemap.download_ee_image(
        image=image,
        filename=output_tif_path,
        region=geometry,
        scale=10,
        crs="EPSG:4326",
        dtype="uint8"
    )

    if not os.path.exists(output_tif_path):
        raise RuntimeError(f"❌ Error: No se pudo guardar el archivo: {output_tif_path}")
    else:
        print(f"✅ Archivo guardado correctamente: {output_tif_path}")

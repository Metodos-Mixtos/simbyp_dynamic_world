import geopandas as gpd
import ee
import geemap
from datetime import datetime
import os

def authenticate_gee():
    try:
        ee.Initialize(project='ee-monitoreo-bosques')
    except Exception:
        ee.Authenticate()
        ee.Initialize(project='ee-monitoreo-bosques')

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

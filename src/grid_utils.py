import geopandas as gpd
from shapely.geometry import box
import math

def create_grid(aoi_path: str, grid_size: int) -> gpd.GeoDataFrame:
    aoi = gpd.read_file(aoi_path)
    aoi = aoi.to_crs(epsg=3857)
    
    aoi_union = aoi.union_all()

    minx, miny, maxx, maxy = aoi.total_bounds
    cols = list(range(int(math.floor(minx)), int(math.ceil(maxx)), grid_size))
    rows = list(range(int(math.floor(miny)), int(math.ceil(maxy)), grid_size))
    grid_cells = []

    # Crear las celdas de la grilla
    grid_cells = [box(x, y, x + grid_size, y + grid_size) for x in cols for y in rows]
    grid = gpd.GeoDataFrame(geometry=grid_cells, crs="EPSG:3857")

    # Filtrar solo las celdas que se intersectan con el AOI
    grid = gpd.sjoin(grid, gpd.GeoDataFrame(geometry=[aoi_union], crs="EPSG:3857"),how="inner", predicate="intersects").drop(columns="index_right")

    # Cortar exactamente cada celda con el AOI
    grid["geometry"] = grid.geometry.intersection(aoi_union)


    grid["grid_id"] = range(1, len(grid) + 1)
    grid = grid.to_crs(epsg=4326)
    return grid

import geopandas as gpd
from shapely.geometry import box
import math

def create_grid(aoi_path: str, grid_size: int) -> gpd.GeoDataFrame:
    aoi = gpd.read_file(aoi_path)
    aoi = aoi.to_crs(epsg=3857)

    minx, miny, maxx, maxy = aoi.total_bounds
    cols = list(range(int(math.floor(minx)), int(math.ceil(maxx)), grid_size))
    rows = list(range(int(math.floor(miny)), int(math.ceil(maxy)), grid_size))
    grid_cells = []

    for x in cols:
        for y in rows:
            cell = box(x, y, x + grid_size, y + grid_size)
            grid_cells.append(cell)

    grid = gpd.GeoDataFrame(geometry=grid_cells, crs=aoi.crs)
    grid = gpd.overlay(grid, aoi, how='intersection')
    grid["grid_id"] = range(1, len(grid) + 1)
    grid = grid.to_crs(epsg=4326)
    return grid

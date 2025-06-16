import geopandas as gpd
import rasterio
from rasterstats import zonal_stats
import pandas as pd
import numpy as np

def get_class_percentages_per_grid(grid_gdf, raster_path, class_values=range(9)):
    """Calcula el porcentaje real de cada clase en cada celda, basado en conteo real de píxeles."""
    zs = zonal_stats(
        grid_gdf,
        raster_path,
        stats="count",
        categorical=True,
        category_map={c: f"class_{c}" for c in class_values},
        geojson_out=True,
        nodata=-9999
    )

    records = []

    for feature in zs:
        props = feature["properties"]
        grid_id = props["grid_id"]
        # total de píxeles reales válidos en esta celda
        count_total = sum(props.get(f"class_{c}", 0) for c in class_values)

        for c in class_values:
            count = props.get(f"class_{c}", 0)
            pct = (count / count_total) * 100 if count_total > 0 else 0
            records.append({"grid_id": grid_id, "class": c, "percent": pct})

    return pd.DataFrame(records)


def compare_class_percentages(df1, df2, q1, q2):
    """Une dos dataframes de porcentajes y calcula la diferencia."""
    df1 = df1.rename(columns={"percent": f"percent_{q1}"})
    df2 = df2.rename(columns={"percent": f"percent_{q2}"})

    merged = df1.merge(df2, on=["grid_id", "class"], how="outer").fillna(0)
    merged["change_pct"] = merged[f"percent_{q2}"] - merged[f"percent_{q1}"]

    return merged

import geopandas as gpd
import rasterio
from rasterstats import zonal_stats
import pandas as pd
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping

def get_semester_dates(semestre: str, anio: str):
    """
    Retorna las fechas de inicio y fin del análisis para un semestre dado.
    semestre: "I" o "II"
    anio: por ejemplo "2025"
    """
    semestre = semestre.upper().strip()
    if semestre == "I":
        date_before = f"{int(anio)-1}-12-31"
        current_date = f"{anio}-06-30"
    elif semestre == "II":
        date_before = f"{anio}-06-30"
        current_date = f"{anio}-12-31"
    else:
        raise ValueError("Semestre inválido. Usa 'I' o 'II'.")
    return current_date, date_before

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

def get_transition_changes_per_grid(
    grid_gdf: gpd.GeoDataFrame,
    tif_before: str,
    tif_current: str,
    nodata_values: tuple = (255, -9999)
) -> pd.DataFrame:
    """
    Calcula, por celda de grilla, los cambios:
      - 1 -> cualquier clase distinta de 1
      - 5 -> cualquier clase distinta de 1
    
    Devuelve conteos y porcentajes tanto sobre el total de píxeles válidos
    como sobre el tamaño de la clase origen en t_before.

    Columns:
      grid_id
      n_validos
      n_1_a_otro, pct_1_a_otro_grid, pct_1_a_otro_clase1,
      n_5_a_otro_no1, pct_5_a_otro_no1_grid, pct_5_a_otro_no1_clase5
    """
    # Abrir rasters una sola vez
    with rasterio.open(tif_before) as src1, rasterio.open(tif_current) as src2:
        # Chequeo básico: mismas dimensiones/proyección (asumido en tu flujo)
        if src1.crs != src2.crs:
            raise ValueError("CRS de los rasters no coincide.")
        if src1.transform != src2.transform or src1.width != src2.width or src1.height != src2.height:
            # No es estrictamente obligatorio, pero es lo más seguro
            # Si no coinciden exactamente, se podría reprojectar o reamostrar.
            raise ValueError("Geometría/transform de los rasters no coincide.")

        # Asegurar que la grilla esté en el CRS del raster
        grid = grid_gdf.to_crs(src1.crs)

        records = []
        for _, row in grid.iterrows():
            gid = row["grid_id"]
            geom = [mapping(row.geometry)]

            # Recortar ambos rasters a la celda
            out1, _ = mask(src1, geom, crop=True, filled=True)
            out2, _ = mask(src2, geom, crop=True, filled=True)

            a1 = out1[0]
            a2 = out2[0]

            # Construir máscara de válidos
            valid = np.ones_like(a1, dtype=bool)
            for nd in nodata_values:
                valid &= (a1 != nd) & (a2 != nd)
            # También invalidar pixeles fuera (si ever llegan como <0)
            valid &= (a1 >= 0) & (a2 >= 0)

            n_valid = int(valid.sum())
            if n_valid == 0:
                records.append({
                    "grid_id": gid,
                    "n_validos": 0,
                    "n_1_a_otro": 0,
                    "pct_1_a_otro_grid": 0.0,
                    "pct_1_a_otro_clase1": 0.0,
                    "n_5_a_otro_no1": 0,
                    "pct_5_a_otro_no1_grid": 0.0,
                    "pct_5_a_otro_no1_clase5": 0.0
                })
                continue

            a1v = a1[valid]
            a2v = a2[valid]

            # Tamaños de clases origen en t_before
            n_class1_before = int((a1v == 1).sum())
            n_class5_before = int((a1v == 5).sum())

            # 1 -> cualquier ≠ 1
            n_1_to_any = int(((a1v == 1) & (a2v != 1)).sum())

            # 5 -> cualquier ≠ 1
            n_5_to_not1 = int(((a1v == 5) & (a2v != 1) & (a2v != 5)).sum())

            # Porcentajes sobre la grilla
            pct_1_to_any_grid = 100.0 * n_1_to_any / n_valid
            pct_5_to_not1_grid = 100.0 * n_5_to_not1 / n_valid

            # Porcentajes sobre la clase origen
            pct_1_to_any_of_class1 = 100.0 * n_1_to_any / n_class1_before if n_class1_before > 0 else 0.0
            pct_5_to_not1_of_class5 = 100.0 * n_5_to_not1 / n_class5_before if n_class5_before > 0 else 0.0

            records.append({
                "grid_id": gid,
                "n_validos": n_valid,
                "n_1_a_otro": n_1_to_any,
                "pct_1_a_otro_grid": pct_1_to_any_grid,
                "pct_1_a_otro_clase1": pct_1_to_any_of_class1,
                "n_5_a_otro_no1": n_5_to_not1,
                "pct_5_a_otro_no1_grid": pct_5_to_not1_grid,
                "pct_5_a_otro_no1_clase5": pct_5_to_not1_of_class5
            })

    return pd.DataFrame.from_records(records)

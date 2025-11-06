from src.aux_utils import log
import ee
import geopandas as gpd
import folium
import os
import pandas as pd
import json
from src.config import PROJECT_ID

def get_tile_from_image(image, vis_params=None):
    """
    Devuelve el URL del tile (mapa dinámico) a partir de una ee.Image ya cargada.
    Evita volver a consultar la colección de Earth Engine.
    """
    if vis_params is None:
        vis_params = {
            "min": 0,
            "max": 8,
            "palette": [
                "#419BDF", "#397D49", "#88B053", "#7A87C6",
                "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"
            ]
        }
    return image.getMapId(vis_params)["tile_fetcher"].url_format

def get_tiles_from_ee(
    aoi_path: str,
    end_t1: str,
    end_t2: str,
    dataset: str = "SENTINEL",
    lookback_days: int = 365
):
    """
    Devuelve URLs de tiles (T1 y T2) desde Google Earth Engine para Sentinel o Dynamic World.
    Ambos usan lookback_days para tomar la imagen más reciente antes de cada fecha final.
    """
    ee.Initialize(project=PROJECT_ID)

    aoi = gpd.read_file(aoi_path)
    minx, miny, maxx, maxy = aoi.total_bounds
    geom = ee.Geometry.BBox(minx, miny, maxx, maxy)

    if dataset == "SENTINEL":
        col_id = "COPERNICUS/S2_SR_HARMONIZED"
        vis = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"], "gamma": 1.1}
        sel = ["B4", "B3", "B2"]

        def get_tile_url(end):
            end_ee = ee.Date(end)
            start_ee = end_ee.advance(-lookback_days, "day")

            collection = (
                ee.ImageCollection(col_id)
                .filterDate(start_ee, end_ee)
                .filterBounds(geom)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                .select(sel)
                .sort("system:time_start", False)
                .sort("system:index")
            )

            # Tomar el mosaico más limpio del período
            image = collection.mosaic().clip(geom)
            return image.getMapId(vis)["tile_fetcher"].url_format

    elif dataset == "DW":
        col_id = "GOOGLE/DYNAMICWORLD/V1"
        vis = {
            "min": 0,
            "max": 8,
            "palette": [
                "#419BDF", "#397D49", "#88B053", "#7A87C6",
                "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"
            ]
        }
        sel = ["label"]

        def get_tile_url(end):
            end_ee = ee.Date(end)
            start_ee = end_ee.advance(-lookback_days, "day")

            collection = (
                ee.ImageCollection(col_id)
                .filterDate(start_ee, end_ee)
                .filterBounds(geom)
                .select(sel)
                .sort("system:time_start", False)
                .sort("system:index")
            )

            image = collection.mosaic().clip(geom)
            return image.getMapId(vis)["tile_fetcher"].url_format

    else:
        raise ValueError("dataset debe ser 'SENTINEL' o 'DW'")

    return {
        "t1": get_tile_url(end_t1),
        "t2": get_tile_url(end_t2)
    }

def plot_sentinel_interactive(
    grid_path: str,
    aoi_path: str,
    output_path: str,
    annio: int,
    mes: str,
    tiles_t1=None,
    tiles_t2=None
):
    """
    Mapa interactivo con:
    - Basemap CartoDB Positron
    - Sentinel-2 T1 y T2
    - Grilla y AOI en rojo
    - Números de grilla
    """

    def sanitize_gdf(gdf):
        for c in gdf.columns:
            if pd.api.types.is_datetime64_any_dtype(gdf[c]):
                gdf[c] = gdf[c].astype(str)
        return gdf

    aoi = gpd.read_file(aoi_path).to_crs(epsg=4326)
    centroid = aoi.geometry.unary_union.centroid
    lat, lon = centroid.y, centroid.x

    # Crear mapa base centrado temporalmente
    m = folium.Map(tiles="CartoDB positron")

    # Ajustar límites al AOI automáticamente
    minx, miny, maxx, maxy = aoi.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]])

    # === Sentinel overlays ===
    if tiles_t1:
        folium.TileLayer(
            tiles=tiles_t1,
            name=f"Imagen de Sentinel-2 para {mes} de {str(int(annio)-1)}",
            attr="Sentinel-2 EE Mosaic",
            overlay=True,
            show=True
        ).add_to(m)

    if tiles_t2:
        folium.TileLayer(
            tiles=tiles_t2,
            name=f"Imagen de Sentinel-2 para {mes} de {annio}",
            attr="Sentinel-2 EE Mosaic",
            overlay=True,
            show=False
        ).add_to(m)

    # === Capa de grilla (roja) ===
    if os.path.exists(grid_path):
        grid = sanitize_gdf(gpd.read_file(grid_path).to_crs(epsg=4326))
        folium.GeoJson(
            json.loads(grid.to_json()),
            name="Grilla de análisis",
            style_function=lambda x: {"color": "red", "weight": 0.6, "fillOpacity": 0},
            show=True
        ).add_to(m)

        # Agregar números de grilla
        for _, row in grid.iterrows():
            centroid = row.geometry.centroid
            grid_id = row.get("grid_id", "")
            folium.map.Marker(
                [centroid.y, centroid.x],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10pt;color:red">{grid_id}</div>'
                )
            ).add_to(m)

    # === AOI (borde rojo) ===
    folium.GeoJson(
        json.loads(aoi.to_json()),
        name="Área de estudio",
        style_function=lambda x: {"color": "red", "weight": 1.2, "fillOpacity": 0},
        show=True
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(output_path)
    
def plot_dynamic_world_interactive(
    grid_path: str,
    aoi_path: str,
    output_path: str,
    annio: int,
    mes: str,
    tiles_t1=None,
    tiles_t2=None
):
    """
    Crea un mapa interactivo con:
    - Basemap CartoDB Positron
    - Dynamic World T1 (mes anterior) y T2 (mes actual)
    - Grilla vectorial y AOI en negro
    - Etiquetas de número de grilla
    - Leyenda de clases DW
    """

    dw_classes = [
        ("Agua", "#419BDF"),
        ("Árboles", "#397D49"),
        ("Pastizales", "#88B053"),
        ("Vegetación inundada", "#7A87C6"),
        ("Cultivos", "#E49635"),
        ("Arbustos y matorrales", "#DFC35A"),
        ("Área construida", "#C4281B"),
        ("Suelo desnudo", "#A59B8F"),
        ("Nieve y hielo", "#B39FE1")
    ]

    def sanitize_gdf(gdf):
        for c in gdf.columns:
            if pd.api.types.is_datetime64_any_dtype(gdf[c]):
                gdf[c] = gdf[c].astype(str)
        return gdf

    # === AOI ===
    aoi = gpd.read_file(aoi_path).to_crs(epsg=4326)
    centroid = aoi.geometry.unary_union.centroid
    lat, lon = centroid.y, centroid.x

    # Crear mapa base centrado temporalmente
    m = folium.Map(tiles="CartoDB positron")

    # Ajustar límites al AOI automáticamente
    minx, miny, maxx, maxy = aoi.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]])

    # === Dynamic World overlays ===
    if tiles_t1:
        folium.TileLayer(
            tiles=tiles_t1,
            name=f"Cobertura del suelo en {mes} de {str(int(annio)-1)}",
            attr="Dynamic World EE Mosaic",
            overlay=True,
            show=True
        ).add_to(m)

    if tiles_t2:
        folium.TileLayer(
            tiles=tiles_t2,
            name=f"Cobertura del suelo en {mes} de {annio}",
            attr="Dynamic World EE Mosaic",
            overlay=True,
            show=False
        ).add_to(m)

    # === Capa de grilla ===
    if os.path.exists(grid_path):
        grid = sanitize_gdf(gpd.read_file(grid_path).to_crs(epsg=4326))
        folium.GeoJson(
            json.loads(grid.to_json()),
            name="Grilla de análisis",
            style_function=lambda x: {"color": "black", "weight": 0.6, "fillOpacity": 0},
            show=True
        ).add_to(m)

        # Agregar números de grilla
        for _, row in grid.iterrows():
            centroid = row.geometry.centroid
            grid_id = row.get("grid_id", "")
            folium.map.Marker(
                [centroid.y, centroid.x],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10pt;color:black">{grid_id}</div>'
                )
            ).add_to(m)

    # === AOI (borde negro) ===
    folium.GeoJson(
        json.loads(aoi.to_json()),
        name="Área de estudio",
        style_function=lambda x: {"color": "black", "weight": 1.2, "fillOpacity": 0},
        show=True
    ).add_to(m)

    # === Leyenda ===
    legend_html = """
    <div style='position: fixed; bottom: 10px; left: 10px; z-index:9999; background-color:white;
                padding:10px; border:2px solid grey; border-radius:5px; font-size:12px'>
        <b>Leyenda</b><br>
    """
    for label, color in dw_classes:
        legend_html += f"<i style='background:{color};width:15px;height:15px;float:left;margin-right:5px'></i>{label}<br>"
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(output_path)

def generate_maps(aoi_path, grid_path, map_dir, date_before, current_date, anio, mes, lookback_days, dw_before, dw_current):
    """
    Genera mapas interactivos de Sentinel y Dynamic World.
    Si se proporcionan dw_before y dw_current, los reutiliza en lugar de reconstruirlos desde GEE.
    """
    log("Generando mapas interactivos...", "info")

    # Sentinel siempre se obtiene desde EE
    tiles_s2 = get_tiles_from_ee(
        aoi_path=aoi_path,
        end_t1=date_before, end_t2=current_date,
        dataset="SENTINEL", lookback_days=lookback_days
    )
    plot_sentinel_interactive(
        grid_path=grid_path, aoi_path=aoi_path,
        output_path=f"{map_dir}/sentinel_mes.html",
        annio=anio, mes=mes,
        tiles_t1=tiles_s2["t1"], tiles_t2=tiles_s2["t2"]
    )

    # Dynamic World
    tiles_dw = {
        "t1": get_tile_from_image(dw_before),
        "t2": get_tile_from_image(dw_current)
    }

    plot_dynamic_world_interactive(
        grid_path=grid_path, aoi_path=aoi_path,
        output_path=f"{map_dir}/dw_mes.html",
        annio=anio, mes=mes,
        tiles_t1=tiles_dw["t1"], tiles_t2=tiles_dw["t2"]
    )

    log("Mapas interactivos listos.", "success")
    return {
        "MAPA_SENTINEL_INTERACTIVO": f"{map_dir}/sentinel_mes.html",
        "MAPA_DW_INTERACTIVO": f"{map_dir}/dw_mes.html"
    }

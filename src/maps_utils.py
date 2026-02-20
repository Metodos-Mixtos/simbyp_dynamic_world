import geemap
from src.aux_utils import log
import ee
import geopandas as gpd
import folium
import os
import pandas as pd
from pathlib import Path
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
    tiles_t2=None,
    png_t1=None,
    png_t2=None,
    bounds=None
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
    # Si hay PNGs y bounds, usar ImageOverlay; si no, usar TileLayer (retrocompatibilidad)
    if png_t1 and bounds:
        folium.raster_layers.ImageOverlay(
            name=f"Sentinel-2 PNG {mes} {str(int(annio)-1)}",
            image=png_t1,
            bounds=bounds,
            opacity=0.8,
            interactive=True,
            cross_origin=False,
            zindex=1,
            show=True
        ).add_to(m)
    elif tiles_t1:
        folium.TileLayer(
            tiles=tiles_t1,
            name=f"Imagen de Sentinel-2 para {mes} de {str(int(annio)-1)}",
            attr="Sentinel-2 EE Mosaic",
            overlay=True,
            show=True
        ).add_to(m)

    if png_t2 and bounds:
        folium.raster_layers.ImageOverlay(
            name=f"Sentinel-2 PNG {mes} {annio}",
            image=png_t2,
            bounds=bounds,
            opacity=0.8,
            interactive=True,
            cross_origin=False,
            zindex=2,
            show=False
        ).add_to(m)
    elif tiles_t2:
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
    tiles_t2=None,
    png_t1=None,
    png_t2=None,
    bounds=None
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
    if png_t1 and bounds:
        folium.raster_layers.ImageOverlay(
            name=f"DW PNG {mes} {str(int(annio)-1)}",
            image=png_t1,
            bounds=bounds,
            opacity=0.8,
            interactive=True,
            cross_origin=False,
            zindex=1,
            show=True
        ).add_to(m)
    elif tiles_t1:
        folium.TileLayer(
            tiles=tiles_t1,
            name=f"Cobertura del suelo en {mes} de {str(int(annio)-1)}",
            attr="Dynamic World EE Mosaic",
            overlay=True,
            show=True
        ).add_to(m)

    if png_t2 and bounds:
        folium.raster_layers.ImageOverlay(
            name=f"DW PNG {mes} {annio}",
            image=png_t2,
            bounds=bounds,
            opacity=0.8,
            interactive=True,
            cross_origin=False,
            zindex=2,
            show=False
        ).add_to(m)
    elif tiles_t2:
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
    # === Exportar PNGs por celda de grilla para ambos periodos ===
    import shapely
    grid_gdf = gpd.read_file(grid_path).to_crs(epsg=4326)
    from src.dw_utils import authenticate_gee
    authenticate_gee()
    # Crear carpetas para imágenes
    dw_dir = Path(map_dir) / 'imagenes' / 'dw'
    sentinel_dir = Path(map_dir) / 'imagenes' / 'sentinel'
    dw_dir.mkdir(parents=True, exist_ok=True)
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    for _, row in grid_gdf.iterrows():
        grid_id = row.get("grid_id", _)
        geom = row.geometry
        if geom.is_empty:
            continue
        if geom.geom_type == "MultiPolygon":
            geom = shapely.ops.unary_union([p for p in geom.geoms if not p.is_empty])
        gdf_tmp = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        ee_geom = geemap.geopandas_to_ee(gdf_tmp).geometry()
        import os
        from PIL import Image
        # Sentinel periodo anterior (t1)
        sent_t1_png = sentinel_dir / f"sentinel_grid_{grid_id}_{date_before}.png"
        if not sent_t1_png.exists():
            try:
                col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                    .filterDate(date_before, date_before) \
                    .filterBounds(ee_geom) \
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)) \
                    .select(["B4", "B3", "B2"])
                img = col.median().clip(ee_geom)
                mask = img.mask().reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=ee_geom,
                    scale=10,
                    maxPixels=1e8
                ).getInfo()
                has_data = any([v for v in mask.values() if v is not None and v > 0])
                if not has_data:
                    log(f"Sentinel celda {grid_id} T1 sin datos, no se exporta PNG", "warning")
                else:
                    geemap.download_ee_image(
                        image=img,
                        filename=str(sent_t1_png),
                        region=ee_geom,
                        scale=10,
                        crs="EPSG:4326",
                        dtype="uint16"
                    )
                    if sent_t1_png.exists() and sent_t1_png.stat().st_size > 100:
                        try:
                            with Image.open(sent_t1_png) as im:
                                im.verify()
                            log(f"Sentinel celda {grid_id} T1 PNG guardada", "success")
                        except Exception as e:
                            log(f"Sentinel celda {grid_id} T1 PNG corrupta: {e}", "error")
                            sent_t1_png.unlink()
                    else:
                        log(f"Sentinel celda {grid_id} T1 PNG vacía, se elimina", "warning")
                        if sent_t1_png.exists():
                            sent_t1_png.unlink()
            except Exception as e:
                log(f"Error Sentinel celda {grid_id} T1: {e}", "error")
        # Sentinel periodo actual (t2)
        sent_t2_png = sentinel_dir / f"sentinel_grid_{grid_id}_{current_date}.png"
        if not sent_t2_png.exists():
            try:
                col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                    .filterDate(current_date, current_date) \
                    .filterBounds(ee_geom) \
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)) \
                    .select(["B4", "B3", "B2"])
                img = col.median().clip(ee_geom)
                mask = img.mask().reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=ee_geom,
                    scale=10,
                    maxPixels=1e8
                ).getInfo()
                has_data = any([v for v in mask.values() if v is not None and v > 0])
                if not has_data:
                    log(f"Sentinel celda {grid_id} T2 sin datos, no se exporta PNG", "warning")
                else:
                    geemap.download_ee_image(
                        image=img,
                        filename=str(sent_t2_png),
                        region=ee_geom,
                        scale=10,
                        crs="EPSG:4326",
                        dtype="uint16"
                    )
                    if sent_t2_png.exists() and sent_t2_png.stat().st_size > 100:
                        try:
                            with Image.open(sent_t2_png) as im:
                                im.verify()
                            log(f"Sentinel celda {grid_id} T2 PNG guardada", "success")
                        except Exception as e:
                            log(f"Sentinel celda {grid_id} T2 PNG corrupta: {e}", "error")
                            sent_t2_png.unlink()
                    else:
                        log(f"Sentinel celda {grid_id} T2 PNG vacía, se elimina", "warning")
                        if sent_t2_png.exists():
                            sent_t2_png.unlink()
            except Exception as e:
                log(f"Error Sentinel celda {grid_id} T2: {e}", "error")
        # Dynamic World periodo anterior (t1)
        dw_t1_png = dw_dir / f"dw_grid_{grid_id}_{date_before}.png"
        if not dw_t1_png.exists():
            try:
                vis_params = {
                    "min": 0,
                    "max": 8,
                    "palette": [
                        "#419BDF", "#397D49", "#88B053", "#7A87C6",
                        "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"
                    ]
                }
                dw_img = dw_before.clip(ee_geom)
                mask = dw_img.mask().reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=ee_geom,
                    scale=10,
                    maxPixels=1e8
                ).getInfo()
                has_data = any([v for v in mask.values() if v is not None and v > 0])
                if not has_data:
                    log(f"DW celda {grid_id} T1 sin datos, no se exporta PNG", "warning")
                else:
                    dw_t1 = dw_img.visualize(**vis_params)
                    geemap.download_ee_image(
                        image=dw_t1,
                        filename=str(dw_t1_png),
                        region=ee_geom,
                        scale=10,
                        crs="EPSG:4326",
                        dtype="uint8"
                    )
                    if dw_t1_png.exists() and dw_t1_png.stat().st_size > 100:
                        try:
                            with Image.open(dw_t1_png) as im:
                                im.verify()
                            log(f"DW celda {grid_id} T1 PNG guardada", "success")
                        except Exception as e:
                            log(f"DW celda {grid_id} T1 PNG corrupta: {e}", "error")
                            dw_t1_png.unlink()
                    else:
                        log(f"DW celda {grid_id} T1 PNG vacía, se elimina", "warning")
                        if dw_t1_png.exists():
                            dw_t1_png.unlink()
            except Exception as e:
                log(f"Error DW celda {grid_id} T1: {e}", "error")
        # Dynamic World periodo actual (t2)
        dw_t2_png = dw_dir / f"dw_grid_{grid_id}_{current_date}.png"
        if not dw_t2_png.exists():
            try:
                vis_params = {
                    "min": 0,
                    "max": 8,
                    "palette": [
                        "#419BDF", "#397D49", "#88B053", "#7A87C6",
                        "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"
                    ]
                }
                dw_img = dw_current.clip(ee_geom)
                mask = dw_img.mask().reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=ee_geom,
                    scale=10,
                    maxPixels=1e8
                ).getInfo()
                has_data = any([v for v in mask.values() if v is not None and v > 0])
                if not has_data:
                    log(f"DW celda {grid_id} T2 sin datos, no se exporta PNG", "warning")
                else:
                    dw_t2 = dw_img.visualize(**vis_params)
                    geemap.download_ee_image(
                        image=dw_t2,
                        filename=str(dw_t2_png),
                        region=ee_geom,
                        scale=10,
                        crs="EPSG:4326",
                        dtype="uint8"
                    )
                    if dw_t2_png.exists() and dw_t2_png.stat().st_size > 100:
                        try:
                            with Image.open(dw_t2_png) as im:
                                im.verify()
                            log(f"DW celda {grid_id} T2 PNG guardada", "success")
                        except Exception as e:
                            log(f"DW celda {grid_id} T2 PNG corrupta: {e}", "error")
                            dw_t2_png.unlink()
                    else:
                        log(f"DW celda {grid_id} T2 PNG vacía, se elimina", "warning")
                        if dw_t2_png.exists():
                            dw_t2_png.unlink()
            except Exception as e:
                log(f"Error DW celda {grid_id} T2: {e}", "error")

    """
    Genera mapas interactivos y exporta imágenes PNG de Sentinel y Dynamic World.
    Devuelve rutas de HTML y PNG.
    """
    log("Generando mapas interactivos y PNG...", "info")

    # Obtener bounds del AOI
    aoi = gpd.read_file(aoi_path).to_crs(epsg=4326)
    minx, miny, maxx, maxy = aoi.total_bounds
    bounds = [[miny, minx], [maxy, maxx]]

    # Mapas interactivos usando overlays por grilla (se generan con png_map.py)
    # Aquí solo devolvemos las rutas esperadas para el reporte
    mapas_dir = Path(map_dir)
    log("Mapas interactivos y PNG listos.", "success")
    return {
        "MAPA_SENTINEL_INTERACTIVO": str(mapas_dir / "sentinel_mes.html"),
        "MAPA_DW_INTERACTIVO": str(mapas_dir / "dw_mes.html"),
        "IMG_SENTINEL_PNG_DIR": str(mapas_dir / "imagenes" / "sentinel"),
        "IMG_DW_PNG_DIR": str(mapas_dir / "imagenes" / "dw")
    }

import os
import rasterio
import rioxarray
import ee
from rasterio.mask import mask
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import mapping
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import xarray as xr
import matplotlib.pyplot as plt
from rasterio.plot import show
import geopandas as gpd
import folium
import json
import pandas as pd

def plot_landcover_comparison(tif1_path, tif2_path, q1, q2, grid_path, output_path):
    # Colores y etiquetas DW
    dw_colors = [
        "#419BDF", "#397D49", "#88B053", "#7A87C6",
        "#E49635", "#DFC35A", "#C4281B", "#A59B8F", "#B39FE1"
    ]
    class_labels = [
        "Agua", "Árboles", "Pastizales", "Vegetación inundada", "Cultivos",
        "Arbustos y matorrales", "Área construida", "Suelo desnudo", "Nieve y hielo"
    ]
    cmap = ListedColormap(dw_colors)

    # Leer AOI
    aoi = gpd.read_file(grid_path)

    # Función para recortar y preparar cada tif
    def prepare_tif(tif_path):
        with rasterio.open(tif_path) as src:
            aoi_proj = aoi.to_crs(src.crs)
            out_image, out_transform = mask(src,[mapping(aoi_proj.unary_union)], crop=True, filled=True, nodata=255)
            crs = src.crs
        da = xr.DataArray(out_image[0], dims=("y", "x"))
        da = da.where(da != 255)
        da.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)
        da.rio.write_crs(crs, inplace=True)
        da.rio.write_transform(out_transform, inplace=True)
        return da

    # Recortar ambos
    da1 = prepare_tif(tif1_path)
    da2 = prepare_tif(tif2_path)

    # Crear figura con dos subplots verticales
    fig, axs = plt.subplots(1, 2, figsize=(14, 7), facecolor="none", constrained_layout=True)

    for ax, da, quarter in zip(axs, [da1, da2], [q1, q2]):
        ax.imshow(
            da.values,
            cmap=cmap,
            vmin=0,
            vmax=8,
            extent=da.rio.bounds(),
            interpolation="nearest"
        )
        ax.set_title(f"{quarter}", fontsize=16)
        ax.axis("off")

    #ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)

    # Agregar leyenda
    legend_elements = [Patch(facecolor=color, label=label) for color, label in zip(dw_colors, class_labels)]
    fig.legend(handles=legend_elements, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=4, fontsize=14, frameon=False)

    # Guardar
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout(rect=[0, 0.1, 1, 1]) 
    plt.savefig(output_path, dpi=150, bbox_inches="tight", transparent=True, pad_inches=0)
    plt.close()

    print(f"🖼️ Mapa comparativo guardado en: {output_path}")

def plot_sentinel_with_grid(tif_path: str, grid_path: str, output_path: str):
    """
    Plotea una imagen Sentinel-2 RGB junto con la grilla en color rojo.
    Guarda el resultado como PNG.
    """
    print(f"🗺️ Generando mapa Sentinel-2 + grilla → {output_path}")

    # Leer raster y grilla
    with rasterio.open(tif_path) as src:
        img = src.read([1, 2, 3])
        bounds = src.bounds
        crs = src.crs

    grid = gpd.read_file(grid_path).to_crs(crs)

    # Crear figura
    fig, ax = plt.subplots(figsize=(10, 10))
    show(img, transform=src.transform, ax=ax)
    grid.boundary.plot(ax=ax, color="red", linewidth=0.8, label="Grilla")

    # Mejorar estilo
    ax.legend(loc="lower right")
    ax.set_title("Imagen Sentinel-2 y grilla de análisis", fontsize=14)
    ax.set_axis_off()

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", transparent=False)
    plt.close()

    print(f"✅ Mapa guardado en: {output_path}")

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
    ee.Initialize(project="bosques-bogota-416214")

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
            )

            # Tomar el mosaico más limpio del período
            image = collection.median().clip(geom)
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


def plot_sentinel_interactive_semester(
    grid_path: str,
    aoi_path: str,
    output_path: str,
    annio: int,
    semestre: str,
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
            name=f"Sentinel-2 T1 (Semestre anterior)",
            attr="Sentinel-2 EE Median (semestre anterior)",
            overlay=True,
            show=False
        ).add_to(m)

    if tiles_t2:
        folium.TileLayer(
            tiles=tiles_t2,
            name=f"Sentinel-2 T2 (Semestre {semestre}, {annio})",
            attr="Sentinel-2 EE Median (semestre actual)",
            overlay=True,
            show=True
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
    print(f"✅ Mapa interactivo Sentinel-2 guardado en: {output_path}")


def plot_dynamic_world_interactive_semester(
    grid_path: str,
    aoi_path: str,
    output_path: str,
    annio: int,
    semestre: str,
    tiles_t1=None,
    tiles_t2=None
):
    """
    Crea un mapa interactivo con:
    - Basemap CartoDB Positron
    - Dynamic World T1 (semestre anterior) y T2 (semestre actual)
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
            name=f"Dynamic World T1 (Semestre anterior, {annio})",
            attr="Dynamic World EE Último mosaico semestre anterior",
            overlay=True,
            show=False
        ).add_to(m)

    if tiles_t2:
        folium.TileLayer(
            tiles=tiles_t2,
            name=f"Dynamic World T2 (Semestre {semestre}, {annio})",
            attr="Dynamic World EE Último mosaico semestre actual",
            overlay=True,
            show=True
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
        <b>Clases Dynamic World</b><br>
    """
    for label, color in dw_classes:
        legend_html += f"<i style='background:{color};width:15px;height:15px;float:left;margin-right:5px'></i>{label}<br>"
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(output_path)
    print(f"✅ Mapa interactivo Dynamic World guardado en: {output_path}")

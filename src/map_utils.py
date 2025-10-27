import os
import rasterio
import contextily as ctx
from rasterio.mask import mask
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import mapping
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import xarray as xr
import rioxarray

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

import matplotlib.pyplot as plt
import rasterio
from rasterio.plot import show
import geopandas as gpd

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


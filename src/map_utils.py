import os
import rasterio
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
        "Water", "Trees", "Grass", "Flooded vegetation", "Crops",
        "Shrub & scrub", "Built", "Bare ground", "Snow & ice"
    ]
    cmap = ListedColormap(dw_colors)

    # Leer AOI
    aoi = gpd.read_file(grid_path)

    # Helper para recortar y preparar cada tif
    def prepare_tif(tif_path):
        with rasterio.open(tif_path) as src:
            aoi_proj = aoi.to_crs(src.crs)
            out_image, out_transform = mask(src, [mapping(aoi_proj.unary_union)], crop=True)
            crs = src.crs
        da = xr.DataArray(out_image[0], dims=("y", "x"))
        da.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)
        da.rio.write_crs(crs, inplace=True)
        da.rio.write_transform(out_transform, inplace=True)
        return da

    # Recortar ambos
    da1 = prepare_tif(tif1_path)
    da2 = prepare_tif(tif2_path)

    # Crear figura con dos subplots verticales
    fig, axs = plt.subplots(2, 1, figsize=(10, 13))

    for ax, da, quarter in zip(axs, [da1, da2], [q1, q2]):
        ax.imshow(
            da.values,
            cmap=cmap,
            vmin=0,
            vmax=8,
            extent=da.rio.bounds(),
            interpolation="nearest"
        )
        ax.set_title(f"Land cover classification ({quarter})", fontsize=13)
        ax.axis("off")

    # Agregar leyenda
    legend_elements = [Patch(facecolor=color, label=label) for color, label in zip(dw_colors, class_labels)]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3, fontsize=9, frameon=False)

    # Guardar
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"🖼️ Mapa comparativo guardado en: {output_path}")

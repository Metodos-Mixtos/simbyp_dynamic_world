"""
Script para generar mapas interactivos Folium con overlays PNG de grilla (DW y Sentinel) para cualquier páramo y periodo.
Genera grupos de capas para periodo anterior y actual, y controles dinámicos.
"""

import folium
import geopandas as gpd
from pathlib import Path
import os
from typing import Optional

def add_png_overlays(m, grid_gdf, mapas_dir, periodo, tipo, group_name):
    """Agrega overlays PNG de un tipo (dw/sentinel) y periodo (anterior/actual) a un FeatureGroup."""
    fg = folium.FeatureGroup(name=group_name, show=False)
    for idx, row in grid_gdf.iterrows():
        grid_id = row.get('grid_id', idx)
        # Carpeta de imágenes según tipo
        if tipo == 'dw':
            img_dir = mapas_dir / 'dw'
            png_filename = f"dw_grid_{grid_id}_{periodo}.png"
        elif tipo == 'sentinel':
            img_dir = mapas_dir / 'sentinel'
            png_filename = f"sentinel_grid_{grid_id}_{periodo}.png"
        else:
            continue
        png_path = img_dir / png_filename
        # Usar ruta relativa al HTML generado si es local, o absoluta si está en GCS
        try:
            output_html_dir = Path(m.location).parent if hasattr(m, 'location') else Path.cwd()
        except Exception:
            output_html_dir = Path.cwd()
        if png_path.exists():
            # Si el HTML está en la misma raíz que temp_data, usar ruta relativa
            try:
                rel_path = os.path.relpath(png_path, start=output_html_dir).replace('\\', '/')
            except Exception:
                rel_path = str(png_path)
            bounds = list(row.geometry.bounds)
            folium.raster_layers.ImageOverlay(
                name=f"{tipo.upper()} Grid {grid_id} {periodo}",
                image=rel_path,
                bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                opacity=0.8,
                interactive=True,
                cross_origin=False,
                zindex=1,
                show=False
            ).add_to(fg)
        else:
            print(f"[WARN] PNG no encontrado para grid {grid_id} periodo {periodo}: {png_path}")
    fg.add_to(m)
    return fg

def generar_mapa_png(paramo: str, periodo: str, tipo: str, grilla_path: Optional[str]=None, imagenes_dir: Optional[str]=None, output_html: Optional[str]=None):

    """
    Genera un mapa Folium con overlays PNG para un páramo, periodo y tipo (dw/sentinel).
    - paramo: nombre del páramo (ej: 'paramo_chingaza')
    - periodo: string periodo actual (ej: '2025-12-01')
    - tipo: 'dw' o 'sentinel'
    - grilla_path: ruta al geojson de la grilla
    - imagenes_dir: carpeta con subcarpetas dw/ y sentinel/ con los PNGs
    - output_html: ruta de salida del HTML
    """
    BASE = Path(__file__).parent.parent
    if not grilla_path:
        grilla_path = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'grilla' / f'grid_{paramo}_10000m.geojson'
    if not imagenes_dir:
        imagenes_dir = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'mapas' / 'imagenes'
    if not output_html:
        output_html = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'mapas' / f'{tipo}_mes.html'

    grid_gdf = gpd.read_file(grilla_path).to_crs(epsg=4326)
    if grid_gdf.empty:
        print(f"[WARN] La grilla para {paramo} está vacía: {grilla_path}")
        # Intentar usar el polígono del AOI
        # Buscar shape del AOI en la carpeta del páramo
        aoi_path = Path(grilla_path).parent.parent / f"{paramo}.geojson"
        if not aoi_path.exists():
            print(f"[ERROR] No se encontró el shape del AOI para {paramo}: {aoi_path}")
            return
        aoi_gdf = gpd.read_file(aoi_path).to_crs(epsg=4326)
        if aoi_gdf.empty:
            print(f"[ERROR] El shape del AOI para {paramo} está vacío: {aoi_path}")
            return
        centroid = aoi_gdf.unary_union.centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=10, tiles="CartoDB positron")
        # Overlay: buscar PNG por nombre especial
        for periodo_x, label in zip([periodo, f"{int(periodo[:4])-1}-{periodo[5:]}"] , [f"Cobertura {tipo.upper()} periodo actual", f"Cobertura {tipo.upper()} periodo anterior"]):
            if tipo == 'dw':
                img_dir = imagenes_dir / 'dw'
                png_filename = f"dw_aoi_{periodo_x}.png"
            elif tipo == 'sentinel':
                img_dir = imagenes_dir / 'sentinel'
                png_filename = f"sentinel_aoi_{periodo_x}.png"
            else:
                continue
            png_path = img_dir / png_filename
            try:
                rel_path = os.path.relpath(png_path, start=Path(output_html).parent).replace('\\', '/')
            except Exception:
                rel_path = str(png_path)
            bounds = list(aoi_gdf.unary_union.bounds)
            if png_path.exists():
                folium.raster_layers.ImageOverlay(
                    name=f"{tipo.upper()} AOI {periodo_x}",
                    image=rel_path,
                    bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                    opacity=0.8,
                    interactive=True,
                    cross_origin=False,
                    zindex=1,
                    show=False
                ).add_to(m)
            else:
                print(f"[WARN] PNG no encontrado para AOI {paramo} periodo {periodo_x}: {png_path}")
        folium.GeoJson(
            aoi_gdf,
            name="AOI",
            style_function=lambda x: {"color": "black", "weight": 1.2, "fillOpacity": 0}
        ).add_to(m)
        folium.LayerControl(collapsed=False).add_to(m)
        m.save(str(output_html))
        print(f"Mapa guardado en: {output_html}")
        print("\nPara visualizar correctamente las imágenes, ejecuta en la raíz del proyecto:")
        print("\n    python -m http.server\n")
        print("Luego abre en tu navegador:")
        print(f"    http://localhost:8000/{output_html.relative_to(BASE).as_posix()}\n")
        print(f"[INFO] El páramo {paramo} no tiene grilla, se usó el polígono del AOI para el overlay.")
        return
    centroid = grid_gdf.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=10, tiles="CartoDB positron")
    # Grupos de overlays para periodo anterior y actual
    periodo_actual = periodo
    periodo_anterior = f"{int(periodo[:4])-1}-{periodo[5:]}"
    fg_actual = add_png_overlays(m, grid_gdf, imagenes_dir, periodo_actual, tipo, f"Cobertura {tipo.upper()} periodo actual")
    fg_anterior = add_png_overlays(m, grid_gdf, imagenes_dir, periodo_anterior, tipo, f"Cobertura {tipo.upper()} periodo anterior")
    # Grilla
    folium.GeoJson(
        grid_gdf,
        name="Grilla",
        style_function=lambda x: {"color": "black", "weight": 0.6, "fillOpacity": 0}
    ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))
    print(f"Mapa guardado en: {output_html}")
    print("\nPara visualizar correctamente las imágenes, ejecuta en la raíz del proyecto:")
    print("\n    python -m http.server\n")
    print("Luego abre en tu navegador:")
    print(f"    http://localhost:8000/{output_html.relative_to(BASE).as_posix()}\n")
    if len(grid_gdf) == 1:
        print(f"[INFO] El páramo {paramo} solo tiene una grilla. Verifica que la imagen PNG se haya generado correctamente.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Genera mapa Folium con overlays PNG de grilla para un páramo y periodo.")
    parser.add_argument("--paramo", required=True, help="Nombre del páramo (ej: paramo_chingaza)")
    parser.add_argument("--periodo", required=True, help="Periodo actual (ej: 2025-12-01)")
    parser.add_argument("--tipo", required=True, choices=["dw", "sentinel"], help="Tipo de imagen: dw o sentinel")
    parser.add_argument("--grilla_path", help="Ruta al geojson de la grilla")
    parser.add_argument("--mapas_dir", help="Directorio de los PNGs")
    parser.add_argument("--output_html", help="Ruta de salida del HTML")
    args = parser.parse_args()
    generar_mapa_png(args.paramo, args.periodo, args.tipo, args.grilla_path, args.mapas_dir, args.output_html)

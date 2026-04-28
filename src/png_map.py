"""
Script para generar mapas interactivos Folium con overlays PNG de grilla (DW y Sentinel) para cualquier páramo y periodo.
Genera grupos de capas para periodo anterior y actual, y controles dinámicos.
Integra procesamiento de PNGs (transparencia, conversión RGBA) y remapeo de grid_ids para Altiplano (0 → 1).
"""

import folium
import geopandas as gpd
from pathlib import Path
import os
from typing import Optional
from datetime import datetime
from PIL import Image


# ============================================================================
# FUNCIONES DE PROCESAMIENTO DE PNGs
# ============================================================================

def fix_png(img_path, paramo=None):
    """
    Convierte PNG a RGBA y hace transparentes los píxeles negros (solo para DW).
    
    Args:
        img_path: Ruta al archivo PNG
        paramo: Nombre del páramo (para detectar si es DW o Sentinel por la ruta)
    """
    try:
        img_path = Path(img_path)
        
        # Detectar tipo de imagen (DW vs Sentinel) por la ruta
        img_str = str(img_path).lower()
        is_dw = 'dw_grid' in img_str or '/dw/' in img_str or '\\dw\\' in img_str
        is_sentinel = 'sentinel_grid' in img_str or '/sentinel/' in img_str or '\\sentinel\\' in img_str
        
        with Image.open(img_path) as im:
            im = im.convert('RGBA')
            
            # Solo hacer transparentes los negros para DW, no para Sentinel
            if is_dw:
                datas = im.getdata()
                newData = []
                for item in datas:
                    # Si el pixel es negro puro (0,0,0), lo hacemos transparente
                    if item[0] == 0 and item[1] == 0 and item[2] == 0:
                        newData.append((0, 0, 0, 0))
                    else:
                        newData.append(item)
                im.putdata(newData)
            
            im.save(img_path, format='PNG')
        print(f"[OK] PNG procesado: {img_path}")
        return True
    except Exception as e:
        print(f"[ERROR] {img_path}: {e}")
        return False


def fix_all_pngs(mapas_dir):
    """
    Procesa recursivamente todos los PNGs en un directorio.
    Convierte a RGBA y hace transparentes los negros (para DW).
    
    Args:
        mapas_dir: Ruta al directorio que contiene las subcarpetas imagenes/dw y imagenes/sentinel
    """
    mapas_path = Path(mapas_dir).resolve()
    
    if not mapas_path.exists():
        print(f"[WARN] Directorio no encontrado: {mapas_dir}")
        return 0
    
    png_files = list(mapas_path.rglob('*.png'))
    if not png_files:
        print(f"[INFO] No se encontraron PNG en {mapas_dir}")
        return 0
    
    print(f"\n[INFO] Procesando {len(png_files)} PNG(s) en {mapas_path}...")
    processed_count = 0
    
    for png in png_files:
        if fix_png(png):
            processed_count += 1
    
    print(f"[OK] Procesamiento completado: {processed_count}/{len(png_files)} PNGs corregidos.\n")
    return processed_count


# ============================================================================
# FUNCIONES DE REMAPEO DE GRID_ID (Altiplano: 0 → 1)
# ============================================================================

def get_display_grid_id(grid_id, paramo):
    """
    Obtiene el ID de grilla para mostrar/procesar.
    Para Altiplano, remapea 0 → 1 (es el único caso especial).
    
    Args:
        grid_id: ID original de la grilla
        paramo: Nombre del páramo
    
    Returns:
        grid_id remapeado si es Altiplano y grid_id == 0, sino el original
    """
    if paramo and 'altiplano' in paramo.lower() and grid_id == 0:
        return 1
    return grid_id


def get_file_grid_id(grid_id, paramo):
    """
    Obtiene el ID de la grilla para nombres de archivo PNG.
    Para Altiplano: 0 → 1
    Para otros: sin cambio
    """
    return get_display_grid_id(grid_id, paramo)

def format_periodo_label(periodo: str, tipo: str) -> str:
    """
    Convierte periodo en formato legible.
    Ej: '2024-12-01' -> 'Imagen de Sentinel-2 para Diciembre de 2024'
    """
    try:
        date_obj = datetime.strptime(periodo, '%Y-%m-%d')
        mes_nombres = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        mes = mes_nombres.get(date_obj.month, "Mes")
        año = date_obj.year
        tipo_label = "Dynamic World" if tipo == "dw" else "Sentinel-2"
        return f"Imagen de {tipo_label} para {mes} de {año}"
    except:
        return f"Imágenes {tipo.upper()} para {periodo}"

def add_dw_legend(m):
    """
    Agrega leyenda de categorías Dynamic World al mapa.
    """
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 10px; width: 240px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:13px; padding: 10px; border-radius: 5px;
                font-family: Arial, sans-serif;">
    <p style="margin: 0; font-weight: bold; margin-bottom: 10px; color: #333;">
        Leyenda
    </p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#419BDF; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Agua</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#397d49; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Árboles</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#88b053; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Pastizales</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#7a87c6; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Vegetación inundada</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#e49635; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Cultivos</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#dfc35a; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Arbustos y matorrales</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#c4281b; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Área construida</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#a59b8f; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px;"></i>Suelo desnudo</p>
    <p style="margin: 5px 0; color: #333;"><i style="background:#b39fe1; width:15px; height:15px; display:inline-block; border-radius:2px; margin-right:5px; border: 1px solid #999;"></i>Nieve y hielo</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))

def add_grid_labels(m, grid_gdf, paramo=None):
    """
    Agrega etiquetas con números de grilla en el centro de cada polígono.
    Para Altiplano, remapea grid_id 0 → 1 en la visualización.
    
    Args:
        m: mapa Folium
        grid_gdf: GeoDataFrame con las grillas
        paramo: Nombre del páramo (para remapeo de Altiplano)
    """
    for idx, row in grid_gdf.iterrows():
        grid_id = row.get('grid_id', idx)
        # Remapear grid_id si es Altiplano (0 → 1)
        display_grid_id = get_display_grid_id(grid_id, paramo)
        centroid = row.geometry.centroid
        
        # Crear un marcador con texto (sin ícono, solo texto)
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=folium.DivIcon(html=f'''
                <div style="font-size: 14px; font-weight: bold; color: #000;
                           font-family: Arial, sans-serif;
                           text-align: center;">
                    {display_grid_id}
                </div>
            ''')
        ).add_to(m)


from datetime import datetime

def add_png_overlays(m, grid_gdf, mapas_dir, periodo, tipo, group_name, paramo=None, alert_grid_ids=None, html_parent_path=None, opacity=1.0):
    """
    Agrega overlays PNG SOLO para grillas alertadas a un mapa Folium.
    Usa rutas RELATIVAS para que funcione tanto localmente como en GCS.
    
    Args:
        m: mapa Folium
        grid_gdf: GeoDataFrame con todas las grillas
        mapas_dir: Path al directorio de imágenes
        periodo: string del periodo
        tipo: 'dw' o 'sentinel'
        group_name: nombre del grupo de capas
        paramo: nombre del páramo (para remapeo de grid_id en Altiplano)
        alert_grid_ids: lista de grid_ids alerted (SOLO mostrar PNGs para estos)
        html_parent_path: ruta padre donde se guardará el HTML (para rutas relativas)
        opacity: opacidad del overlay (0.0 a 1.0, default 0.75)
    """
    fg = folium.FeatureGroup(name=group_name, show=True)
    png_count = 0
    missing_count = 0
    
    # Convertir a Path absoluta
    mapas_dir = Path(mapas_dir).resolve()
    html_parent_path = Path(html_parent_path).resolve() if html_parent_path else mapas_dir.parent
    
    # Filtrar solo grillas alertadas si se especifican
    if alert_grid_ids and len(alert_grid_ids) > 0:
        grids_to_show = grid_gdf[grid_gdf["grid_id"].isin(alert_grid_ids)]
    else:
        grids_to_show = grid_gdf
    
    for idx, row in grids_to_show.iterrows():
        grid_id = row.get('grid_id', idx)
        # Remapear grid_id si es Altiplano (0 → 1)
        file_grid_id = get_file_grid_id(grid_id, paramo)
        display_grid_id = get_display_grid_id(grid_id, paramo)
        
        # Carpeta de imágenes según tipo
        if tipo == 'dw':
            img_dir = mapas_dir / 'dw'
            png_filename = f"dw_grid_{file_grid_id}_{periodo}.png"
        elif tipo == 'sentinel':
            img_dir = mapas_dir / 'sentinel'
            png_filename = f"sentinel_grid_{file_grid_id}_{periodo}.png"
        else:
            continue
        
        png_path = img_dir / png_filename
        
        if png_path.exists():
            # Obtener bounds del geometry (minx, miny, maxx, maxy)
            bounds_tuple = row.geometry.bounds
            bounds = [[bounds_tuple[1], bounds_tuple[0]], [bounds_tuple[3], bounds_tuple[2]]]
            
            # IMPORTANTE: Usar ruta ABSOLUTA para que Folium pueda acceder al archivo
            # Al renderizar en el navegador, las rutas relativas funcionarán correctamente
            png_path_absolute = str(png_path.resolve())
            
            folium.raster_layers.ImageOverlay(
                name=f"PNG Grid {display_grid_id}",
                image=png_path_absolute,  # Ruta absoluta para que Folium encuentre el archivo
                bounds=bounds,
                opacity=opacity,
                interactive=True,
                cross_origin=False,
                alt=f"{tipo}_grid_{display_grid_id}_{periodo}",
                show=True
            ).add_to(fg)
            png_count += 1
        else:
            missing_count += 1
    
    print(f"[INFO] {tipo.upper()} {group_name}: {png_count} PNGs añadidos para {len(grids_to_show)} grillas alerted")
    fg.add_to(m)
    return fg

def generar_mapa_png(paramo: str, periodo: str, tipo: str, grilla_path: Optional[str]=None, imagenes_dir: Optional[str]=None, output_html: Optional[str]=None, alert_grid_ids: Optional[list]=None):

    """
    Genera un mapa Folium con overlays PNG para un páramo, periodo y tipo (dw/sentinel).
    - paramo: nombre del páramo (ej: 'paramo_chingaza')
    - periodo: string periodo actual (ej: '2025-12-01')
    - tipo: 'dw' o 'sentinel'
    - grilla_path: ruta al geojson de la grilla
    - imagenes_dir: carpeta con subcarpetas dw/ y sentinel/ con los PNGs
    - output_html: ruta de salida del HTML
    - alert_grid_ids: lista de grid_ids a mostrar. Si None, muestra todos
    """
    BASE = Path(__file__).parent.parent
    if not grilla_path:
        grilla_path = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'grilla' / f'grid_{paramo}_10000m.geojson'
    if not imagenes_dir:
        imagenes_dir = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'mapas' / 'imagenes'
    if not output_html:
        output_html = BASE / f'outputs/{periodo[:4]}_{int(periodo[5:7]):02d}/' / paramo / 'mapas' / f'{tipo}_mes.html'

    # Convertir a Path absolutas para evitar problemas de rutas relativas
    grilla_path = Path(grilla_path).resolve()
    imagenes_dir = Path(imagenes_dir).resolve()
    output_html = Path(output_html).resolve()

    grid_gdf = gpd.read_file(grilla_path).to_crs(epsg=4326)
    if grid_gdf.empty:
        print(f"[WARN] La grilla para {paramo} está vacía: {grilla_path}")
        # Intentar usar el polígono del AOI
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
        
        periodo_actual = periodo
        periodo_anterior = f"{int(periodo[:4])-1}-{periodo[5:]}"
        
        # Crear FeatureGroup para Área de análisis (altiplano)
        fg_area = folium.FeatureGroup(name="Área de análisis", show=True)
        
        # Agregar límite del AOI
        folium.GeoJson(
            aoi_gdf,
            style_function=lambda x: {
                "color": "darkblue", 
                "weight": 2.5, 
                "fillOpacity": 0
            },
            popup=f"AOI: {paramo}"
        ).add_to(fg_area)
        
        fg_area.add_to(m)
        
        # Agregar overlays PNG para los 2 períodos (PRIMERO anterior como base, LUEGO actual encima)
        for periodo_x, label, opacity_val in zip(
            [periodo_anterior, periodo_actual], 
            [format_periodo_label(periodo_anterior, tipo), format_periodo_label(periodo_actual, tipo)],
            [1.0, 0.75]
        ):
            if tipo == 'dw':
                img_dir = imagenes_dir / 'dw'
                png_filename = f"dw_grid_1_{periodo_x}.png"
            elif tipo == 'sentinel':
                img_dir = imagenes_dir / 'sentinel'
                png_filename = f"sentinel_grid_1_{periodo_x}.png"
            else:
                continue
            
            png_path = img_dir / png_filename
            bounds = list(aoi_gdf.unary_union.bounds)
            
            if png_path.exists():
                fg = folium.FeatureGroup(name=label, show=True)
                
                # Usar ruta ABSOLUTA para que Folium pueda acceder al archivo
                png_path_absolute = str(png_path.resolve())
                
                folium.raster_layers.ImageOverlay(
                    name=label,
                    image=png_path_absolute,
                    bounds=[[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                    opacity=opacity_val,
                    interactive=True,
                    cross_origin=False,
                    show=True
                ).add_to(fg)
                fg.add_to(m)
            else:
                print(f"[WARN] PNG no encontrado para AOI {paramo} periodo {periodo_x}: {png_path}")
        
        # Agregar leyenda si es Dynamic World
        if tipo == 'dw':
            add_dw_legend(m)
        
        folium.LayerControl(collapsed=False).add_to(m)
        m.save(str(output_html))
        print(f"Mapa guardado en: {output_html}")
        print("\nPara visualizar correctamente las imágenes, ejecuta en la raíz del proyecto:")
        print("\n    python -m http.server\n")
        print("Luego abre en tu navegador:")
        print(f"    http://localhost:8000/{output_html.relative_to(BASE).as_posix()}\n")
        print(f"[INFO] El páramo {paramo} solo tiene una grilla (AOI). Verifica que la imagen PNG se haya generado correctamente.")
        return
    centroid = grid_gdf.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=10, tiles="CartoDB positron")
    
    # Períodos
    periodo_actual = periodo
    periodo_anterior = f"{int(periodo[:4])-1}-{periodo[5:]}"
    
    # Pasar ruta del HTML para rutas relativas correctas
    html_parent = Path(output_html).parent
    
    # PRIMERO: Crear FeatureGroup para la GRILLA (todo en un botón)
    fg_grilla = folium.FeatureGroup(name="Grilla de análisis", show=True)
    
    # Agregar límites de grilla al FeatureGroup
    if alert_grid_ids is not None and len(alert_grid_ids) > 0:
        for idx, row in grid_gdf.iterrows():
            grid_id = row.get('grid_id', idx)
            is_alerted = grid_id in alert_grid_ids
            
            color = "red" if is_alerted else "black"
            weight = 2.5 if is_alerted else 1.5
            
            folium.GeoJson(
                gpd.GeoDataFrame([row], crs="EPSG:4326"),
                style_function=lambda x, c=color, w=weight: {
                    "color": c, 
                    "weight": w, 
                    "fillOpacity": 0.01 if c == "red" else 0.02,
                    "fillColor": c if c == "red" else "black"
                },
                popup=f"Grid {grid_id}" + (" - ALERTA" if is_alerted else "")
            ).add_to(fg_grilla)
    else:
        # Mostrar todas las grillas normalmente
        for idx, row in grid_gdf.iterrows():
            grid_id = row.get('grid_id', idx)
            folium.GeoJson(
                gpd.GeoDataFrame([row], crs="EPSG:4326"),
                style_function=lambda x: {
                    "color": "black", 
                    "weight": 1.5, 
                    "fillOpacity": 0.02,
                    "fillColor": "black"
                },
                popup=f"Grid {grid_id}"
            ).add_to(fg_grilla)
    
    # Agregar FeatureGroup de grilla al mapa
    fg_grilla.add_to(m)
    
    # SEGUNDO: Agregar AOI polygon si existe (como FeatureGroup en Layer Control)
    aoi_path = Path(grilla_path).parent.parent / f"{paramo}.geojson"
    if aoi_path.exists():
        try:
            aoi_gdf = gpd.read_file(aoi_path).to_crs(epsg=4326)
            if not aoi_gdf.empty:
                fg_aoi = folium.FeatureGroup(name="Polígono de estudio (AOI)", show=True)
                folium.GeoJson(
                    aoi_gdf,
                    style_function=lambda x: {
                        "color": "darkblue", 
                        "weight": 2.5, 
                        "fillOpacity": 0
                    },
                    popup=f"AOI: {paramo}"
                ).add_to(fg_aoi)
                fg_aoi.add_to(m)
        except Exception as e:
            pass
    
    # TERCERO: Agregar PNG overlays (PRIMERO anterior como base, LUEGO actual encima)
    # Período anterior con opacity 1.0 (100%) como capa base
    fg_anterior = add_png_overlays(
        m, grid_gdf, imagenes_dir, periodo_anterior, tipo, 
        format_periodo_label(periodo_anterior, tipo),
        paramo=paramo,
        alert_grid_ids=alert_grid_ids,
        html_parent_path=html_parent,
        opacity=1.0
    )
    # Período actual con opacity 0.75 (75%) encima del anterior
    fg_actual = add_png_overlays(
        m, grid_gdf, imagenes_dir, periodo_actual, tipo, 
        format_periodo_label(periodo_actual, tipo),
        paramo=paramo,
        alert_grid_ids=alert_grid_ids,
        html_parent_path=html_parent,
        opacity=1.0
    )
    
    # CUARTO: Agregar leyenda si es Dynamic World
    if tipo == 'dw':
        add_dw_legend(m)
    
    # QUINTO: Agregar números de grillas (con remapeo para Altiplano)
    add_grid_labels(m, grid_gdf, paramo=paramo)
    
    # SEXTO: Si es altiplano, hacer zoom automático al polígono
    # SÉPTIMO: Aplicar fit_bounds FINAL para Altiplano (después de agregar todos los elementos)
    # Esto asegura que sea la última operación antes de guardar
    if paramo and 'altiplano' in paramo.lower():
        try:
            bounds = grid_gdf.total_bounds
            m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(0.1, 0.1))
            print(f"[DEBUG] ✓ Zoom final de Altiplano aplicado antes de guardar")
        except Exception as e:
            print(f"[DEBUG] Error aplicando zoom final: {e}")
    
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))
    print(f"Mapa guardado en: {output_html}")
    
    # OCTAVO: Procesar todos los PNGs (convertir a RGBA, hacer transparentes negros para DW)
    mapas_parent = Path(output_html).parent
    fix_all_pngs(mapas_parent)
    
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

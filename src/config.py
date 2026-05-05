import os
from pathlib import Path
from .secrets_utils import load_secrets

# === Paths base (hardcoded - not sensitive) ===
INPUTS_PATH = "gs://material-estatico-sdp/SIMBYP_DATA"
GCS_OUTPUTS_BASE = "gs://reportes-simbyp"

# === Derived paths ===
AOI_DIR = f"{INPUTS_PATH}/area_estudio/dynamic_world"
LOCAL_AOI = os.path.join(os.getcwd(), "AOIs")
HEADER_IMG1_PATH = f"{INPUTS_PATH}/SDP Logos/asi_4.png"
HEADER_IMG2_PATH = f"{INPUTS_PATH}/SDP Logos/bogota_4.png"
FOOTER_IMG_PATH = f"{INPUTS_PATH}/SDP Logos/secre_5.png"

# === Cloud Storage ===
GCS_BUCKET_NAME = GCS_OUTPUTS_BASE.replace("gs://", "")
GCS_PREFIX = "dynamic_world"  # Carpeta dentro del bucket
USE_GCS = True  # Cambiar a False para guardar localmente

# === Outputs locales (temporal) ===
OUTPUTS_BASE = os.path.join(os.getcwd(), "temp_data")

# === Load secrets (only sensitive data) ===
# Cargar configuración con fallback (igual que GFW):
# 1. Variables de entorno (Cloud Run mounts) - FASTEST
# 2. .env file (desarrollo local)
# 3. Secret Manager API (fallback)
secrets = load_secrets()
PROJECT_ID = secrets["GCP_PROJECT"]
EE_SERVICE_ACCOUNT_KEY = secrets.get("EE_SERVICE_ACCOUNT_KEY")

print(f"✓ Configuración cargada - Proyecto: {PROJECT_ID}")

# === Parámetros globales ===
GRID_SIZE = 10000  # metros
LOOKBACK_DAYS = 365

# === Configuración de alertas por cambios de cobertura ===
# Enfoque híbrido: seleccionar los TOP N grillas que superen el umbral mínimo
ALERT_THRESHOLD_PP = 10.5 # Umbral en puntos porcentuales para alertas (clase 1: árboles, clase 5: arbustos/matorrales), este umbral se fija después de analizar la distribución de cambios en las grillas durante 2025 y sacar el valor que corresponde al que el 90 % de las observaciones (cambios negativos observados en las categorías de interés (pp_class1 y pp_class5)) tienen disminuciones menores a 10.5. Esto asegura que solo se alerten las grillas con cambios significativos y atípicos. 
ALERT_TOP_N_GRIDS = 5  # Cuántas grillas alertar como máximo (ej: top 5)
ALERT_COMBINE_METRICS = True  # Si es True, combina pct_1_a_otro_clase1 y pct_5_a_otro_no1_clase5
# Special case: Altiplano siempre genera mapas (solo tiene 1 grilla)

# AOI_DIR ya está bien definido como carpeta
# Para obtener el path de cada geojson de páramo:
def get_paramo_geojson(paramo_name):
    """Devuelve el path absoluto al geojson de un páramo dado su nombre base (ej: 'paramo_chingaza')."""
    return os.path.join(AOI_DIR, f"{paramo_name}.geojson")


def download_altiplano_aoi_from_gcs(output_dir: str, year: int, month: int) -> str:
    """
    Descarga el AOI de Altiplano desde GCS y lo guarda como grid virtual.
    
    Descargar desde: gs://material-estatico-sdp/SIMBYP_DATA/area_estudio/dynamic_world/paramo_altiplano.geojson
    Guardar en: {output_dir}/{year}_{month:02d}/paramo_altiplano/grilla/grid_paramo_altiplano_10000m.geojson
    
    Args:
        output_dir: Directorio base de outputs (ej: '/path/to/temp_data')
        year: Año (ej: 2025)
        month: Mes (ej: 12)
    
    Returns:
        str: Ruta al archivo guardado
    """
    from google.cloud import storage
    import json
    import geopandas as gpd
    
    # Construir rutas
    gcs_aoi_path = f"{AOI_DIR}/paramo_altiplano.geojson"
    output_path = Path(output_dir) / f"{year}_{month:02d}" / "paramo_altiplano" / "grilla" / "grid_paramo_altiplano_10000m.geojson"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Parsear ruta GCS (gs://bucket/path)
        gcs_parts = gcs_aoi_path.replace("gs://", "").split("/", 1)
        bucket_name = gcs_parts[0]
        blob_path = gcs_parts[1] if len(gcs_parts) > 1 else ""
        
        # Descargar desde GCS
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        aoi_data = json.loads(blob.download_as_string())
        
        # Convertir a GeoDataFrame con ID de grid
        gdf = gpd.GeoDataFrame.from_features(aoi_data['features'])
        gdf['id'] = 0  # Grid ID único para Altiplano
        gdf['grid_id'] = 0
        
        # Guardar como GeoJSON
        gdf.to_file(output_path, driver='GeoJSON')
        
        print(f"✓ AOI Altiplano descargado desde GCS: {gcs_aoi_path}")
        print(f"✓ Guardado en: {output_path}")
        print(f"  Geometría: {gdf.geometry.type.iloc[0] if len(gdf) > 0 else 'N/A'}")
        print(f"  Área: {gdf.geometry.area.sum() / 1e6:.0f} km²")
        
        return str(output_path)
        
    except Exception as e:
        print(f"✗ Error descargando AOI Altiplano desde GCS: {e}")
        print("Alternativa: Crear grilla virtual dummy...")
        return create_dummy_altiplano_grid(output_path)


def create_dummy_altiplano_grid(output_path) -> str:
    """
    Crea una grilla virtual dummy si no se puede descargar de GCS.
    Usa bounds aproximados del Páramo de Altiplano.
    
    Coords aproximadas (WGS84):
    - Lat: 4.8 - 5.3°N
    - Lon: -73.0 - -72.5°W
    
    Args:
        output_path: Ruta donde guardar el GeoJSON
        
    Returns:
        str: Ruta al archivo guardado
    """
    import geopandas as gpd
    from shapely.geometry import box
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Bounds aproximados (minx, miny, maxx, maxy)
    # Altiplano: centro ~5.05°N, 72.75°W
    bounds = (-72.95, 4.8, -72.45, 5.3)
    
    geom = box(*bounds)
    
    gdf = gpd.GeoDataFrame(
        {
            'id': [0],
            'grid_id': [0],
            'name': ['paramo_altiplano_aoi'],
            'tipo': ['aoi_virtual']
        },
        geometry=[geom],
        crs='EPSG:4326'
    )
    
    gdf.to_file(output_path, driver='GeoJSON')
    print(f"✓ Grilla virtual dummy creada en: {output_path}")
    print(f"  Bounds: {bounds}")
    print(f"  Nota: Estos son bounds aproximados. Reemplazar con datos reales cuando estén disponibles.")
    
    return str(output_path)

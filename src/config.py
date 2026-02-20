import os
from pathlib import Path
from dotenv import load_dotenv

# Buscar .env en la raíz del proyecto
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

# === Paths base ===
INPUTS_PATH = os.getenv("INPUTS_PATH")
AOI_DIR = f"{INPUTS_PATH}/area_estudio/dynamic_world"
LOCAL_AOI = os.path.join(os.getcwd(), "AOIs")
HEADER_IMG1_PATH = f"{INPUTS_PATH}/SDP Logos/asi_4.png"
HEADER_IMG2_PATH = f"{INPUTS_PATH}/SDP Logos/bogota_4.png"
FOOTER_IMG_PATH = f"{INPUTS_PATH}/SDP Logos/secre_5.png"

# === Cloud Storage ===
GCS_OUTPUTS_BASE = os.getenv("OUTPUTS_BASE_PATH", "gs://reportes-simbyp")
GCS_BUCKET_NAME = GCS_OUTPUTS_BASE.replace("gs://", "")
GCS_PREFIX = "dynamic_world"  # Carpeta dentro del bucket
USE_GCS = True  # Cambiar a False para guardar localmente

# === Outputs locales (temporal) ===
OUTPUTS_BASE = os.path.join(os.getcwd(), "temp_data")

# === Parámetros globales ===
GRID_SIZE = 10000  # metros
LOOKBACK_DAYS = 365
PROJECT_ID = os.getenv("GCP_PROJECT")

# AOI_DIR ya está bien definido como carpeta
# Para obtener el path de cada geojson de páramo:
def get_paramo_geojson(paramo_name):
    """Devuelve el path absoluto al geojson de un páramo dado su nombre base (ej: 'paramo_chingaza')."""
    return os.path.join(AOI_DIR, f"{paramo_name}.geojson")

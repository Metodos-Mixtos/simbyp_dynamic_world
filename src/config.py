import os
from pathlib import Path
from dotenv import load_dotenv

# Buscar .env en la raíz del proyecto (3 niveles arriba: src -> dynamic_world -> bosques-bog -> raíz)
env_path = Path(__file__).parent.parent.parent.parent / "dot_env_content.env"
load_dotenv(env_path)

# === Paths base ===
INPUTS_PATH = os.getenv("INPUTS_PATH")
AOI_DIR = os.path.join(INPUTS_PATH, "area_estudio", "dynamic_world")
OUTPUTS_BASE = os.path.join(INPUTS_PATH, "dynamic_world", "outputs")
HEADER_IMG1_PATH = os.path.join(INPUTS_PATH, "area_estudio", "asi_4.png")
HEADER_IMG2_PATH = os.path.join(INPUTS_PATH, "area_estudio", "bogota_4.png")
FOOTER_IMG_PATH = os.path.join(INPUTS_PATH, "area_estudio", "secre_5.png")

# === Parámetros globales ===
GRID_SIZE = 10000  # metros
LOOKBACK_DAYS = 365
PROJECT_ID = os.getenv("GCP_PROJECT")

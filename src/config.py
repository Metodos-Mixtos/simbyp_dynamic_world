import os
from dotenv import load_dotenv

load_dotenv("dot_env_content.env")

# === Paths base ===
INPUTS_PATH = os.getenv("INPUTS_PATH")
AOI_DIR = os.path.join(INPUTS_PATH, "dynamic_world", "area_estudio")
OUTPUTS_BASE = os.path.join(INPUTS_PATH, "dynamic_world", "outputs")
LOGO_PATH = os.path.join(INPUTS_PATH, "Logo_SDP.jpeg")

# === Parámetros globales ===
GRID_SIZE = 10000  # metros
LOOKBACK_DAYS = 365
PROJECT_ID = os.getenv("GCP_PROJECT")

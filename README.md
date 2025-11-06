# Módulo de Monitoreo de Coberturas de Páramos – SDP

## Descripción general
Este módulo permite analizar los cambios interanuales en las coberturas de la tierra en áreas de páramo, utilizando datos de **Dynamic World (Google Earth Engine)** y **Sentinel-2**.  
Genera estadísticas de cambio por grilla, mapas interactivos (Folium) y un reporte técnico automatizado en formato HTML.

## Requisitos del sistema
- Python 3.9 o superior  
- Cuenta y autenticación activa en **Google Earth Engine**  
- Entorno virtual recomendado (`venv` o `conda`)

## Instalación
```bash
git clone <url_del_repositorio>
cd dynamic_world
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración del entorno
El módulo requiere un archivo `.env` con las siguientes variables:
```
PROJECT_ID=nombre_del_proyecto_gee
INPUTS_BASE=/ruta/a/inputs
OUTPUTS_BASE=/ruta/a/outputs
AOI_DIR=/ruta/a/aoi
```

## Estructura del proyecto
```
dynamic_world/
│
├── src/
│   ├── aux_utils.py
│   ├── config.py
│   ├── dw_utils.py
│   ├── maps_utils.py
│   ├── reports/
│   │   ├── render_report.py
│   │   └── report_template.html
│
├── outputs/
│   └── {anio_mes}/
│
├── inputs/
│   └── AOIs GeoJSON
│
└── main.py
```

## Ejecución del módulo
Ejemplo de ejecución para julio de 2025:
```bash
python3 dynamic_world/main.py --anio 2025 --mes 7
```

El proceso realizará automáticamente:
1. Lectura de las AOIs definidas en `AOI_DIR`.
2. Descarga del mosaico Dynamic World más reciente (últimos 365 días).
3. Cálculo de transiciones por grilla (bosque→otro uso, matorral→otro uso).
4. Generación de mapas interactivos Sentinel-2 y Dynamic World.
5. Creación del archivo `reporte_paramos_{anio}_{mes}.html`.

## Salidas generadas
Cada ejecución produce una estructura como esta:
```
outputs/
└── 2025_7/
    ├── paramo_chingaza/
    │   ├── comparacion/
    │   │   └── paramo_chingaza_transiciones.csv
    │   ├── mapas/
    │   │   ├── sentinel_semestre.html
    │   │   └── dw_semestre.html
    │   └── grilla/
    │       └── grid_paramo_chingaza_10000m.geojson
    ├── reporte_paramos_2025_7.json
    └── reporte_paramos_2025_7.html
```

## Ejemplo de salida
El reporte final (`reporte_paramos_2025_7.html`) incluye:
- Un resumen cuantitativo del cambio de cobertura boscosa y de matorrales.
- Mapas interactivos Dynamic World y Sentinel-2 del periodo comparado.
- Indicadores agregados y por grilla.
- Comentarios automáticos sobre pérdida o ganancia de cobertura.


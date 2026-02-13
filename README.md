# Módulo de Monitoreo de Coberturas de Páramos – SDP

## Descripción general
Este módulo permite analizar los cambios interanuales en las coberturas de la tierra en áreas de páramo, utilizando datos de **Dynamic World (Google Earth Engine)** y **Sentinel-2**.  
Genera estadísticas de cambio por grilla, mapas interactivos (Folium) y un reporte técnico automatizado en formato HTML.

## Requisitos del sistema
- Python 3.8 o superior  
- Cuenta y autenticación activa en **Google Earth Engine**  
- Entorno virtual recomendado (`venv`)

## Instalación

**⚠️ IMPORTANTE:** Este módulo NO tiene su propio `requirements.txt`. Todas las dependencias se instalan desde la raíz del repositorio.

```bash
# Desde la raíz del repositorio (bosques-bog/)
pip install -r requirements.txt
earthengine authenticate
```

Ver [../INSTALLATION_GUIDE.md](../INSTALLATION_GUIDE.md) para instrucciones completas.

## Configuración del entorno
El módulo requiere un archivo `.env` con las siguientes variables:
```
GCP_PROJECT=nombre_del_proyecto_gee
INPUTS_PATH=gs://material-estatico-sdp/SIMBYP_DATA
OUTPUTS_BASE_PATH=gs://reportes-simbyp
GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/service-account.json
```

## Sistema de almacenamiento en Google Cloud Storage

Este módulo está configurado para guardar automáticamente todos los outputs en **Google Cloud Storage (GCS)**:

### Configuración
- Los outputs se generan localmente en `temp_outputs/` y se suben automáticamente a GCS
- Una vez subidos, los archivos temporales se eliminan automáticamente
- El bucket de destino se configura en la variable de entorno `OUTPUTS_BASE_PATH`
- Para deshabilitar GCS y guardar localmente, cambia `USE_GCS = False` en [config.py](src/config.py)

### Estructura en GCS
```
gs://reportes-simbyp/
└── dynamic_world/
    └── {anio}_{mes}/
        ├── paramo_chingaza/
        │   ├── grilla/
        │   │   └── grid_paramo_chingaza_10000m.geojson
        │   ├── comparacion/
        │   │   └── paramo_chingaza_transiciones.csv
        │   └── mapas/
        │       ├── sentinel_mes.html
        │       └── dw_mes.html
        ├── reporte_paramos_{anio}_{mes}.json
        └── reporte_paramos_{anio}_{mes}.html (URL pública)
```

### URLs públicas
Los reportes HTML finales son accesibles a través de URLs públicas:
```
https://storage.googleapis.com/reportes-simbyp/dynamic_world/{anio}_{mes}/reporte_paramos_{anio}_{mes}.html
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

### Con GCS habilitado (por defecto)
Los archivos se suben automáticamente a Google Cloud Storage y los archivos temporales locales se eliminan. La URL del reporte final se muestra en consola.

### Con GCS deshabilitado
Cada ejecución produce una estructura local como esta:
```
temp_outputs/
└── 2025_7/
    ├── paramo_chingaza/
    │   ├── comparacion/
    │   │   └── paramo_chingaza_transiciones.csv
    │   ├── mapas/
    │   │   ├── sentinel_mes.html
    │   │   └── dw_mes.html
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


# Módulo de Monitoreo de Coberturas de Páramos – SDP

## Descripción general
Este módulo permite analizar los cambios interanuales en las coberturas de la tierra en áreas de páramo, utilizando datos de **Dynamic World (Google Earth Engine)** y **Sentinel-2**.  
Genera estadísticas de cambio por grilla, mapas interactivos (Folium) y un reporte técnico automatizado en formato HTML.

## Requisitos del sistema
- Python 3.8 o superior  
- Cuenta y autenticación activa en **Google Earth Engine**  
- Entorno virtual recomendado (`venv`)

## Instalación

Este módulo usa su propio `requirements.txt` ubicado en la raíz del repositorio.

```bash
# Desde la raíz del repositorio (simbyp_dynamic_world/)
pip install -r requirements.txt
earthengine authenticate
```


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

## Estructura en GCS
```
gs://reportes-simbyp/
└── dynamic_world/
    └── {anio}_{mes}/
        ├── paramo_chingaza/
        │   ├── grilla/
        │   │   └── grid_paramo_chingaza_10000m.geojson
        │   ├── comparacion/
        │   │   ├── paramo_chingaza_transiciones.csv
        │   │   └── paramo_chingaza_coberturas.csv
        │   └── mapas/
        │       ├── sentinel_mes.html
        │       ├── dw_mes.html
        │       └── imagenes/
        │           ├── dw/
        │           │   └── dw_grid_{id}_{fecha}.png
        │           └── sentinel/
        │               └── sentinel_grid_{id}_{fecha}.png
        ├── reporte_paramos_{anio}_{mes}.json
        └── reporte_paramos_{anio}_{mes}.html (URL pública)
```

### URLs públicas
Los reportes HTML finales son accesibles a través de URLs públicas:
```
https://storage.googleapis.com/reportes-simbyp/dynamic_world/{anio}_{mes}/reporte_paramos_{anio}_{mes}.html
```

## Sistema de alertas por coberturas

El módulo utiliza un sistema inteligente de detección de alertas basado en cambios de cobertura:

### Parámetros configurables
En [config.py](src/config.py) se define:
```python
ALERT_THRESHOLD_PP = 1  # Umbral en puntos porcentuales para alertas
```

### Criterios de alerta
Se generan alertas (imágenes PNG de grilla y visualización) cuando:

1. **Pérdida de árboles (Clase 1 - Trees)**:
   - La cobertura de árboles disminuye más de `ALERT_THRESHOLD_PP` puntos porcentuales
   - Ejemplo: Si clase 1 pasa de 30% a 28%, con umbral de 1p.p., se genera alerta

2. **Pérdida de arbustos/matorrales (Clase 5 - Shrub & Scrub)**:
   - La cobertura de arbustos disminuye más de `ALERT_THRESHOLD_PP` puntos porcentuales
   - **Y** el aumento de árboles NO compensa esa pérdida
   - Esto evita alertar por transiciones naturales arbustos y matorrales a árboles 
   - Ejemplo exitoso: Clase 5 -10pp, Clase 1 +3pp → Hay alerta (pérdida neta de 7pp)
   - Ejemplo sin alerta: Clase 5 -10pp, Clase 1 +10pp → No hay alerta

3. **Caso especial - Altiplano**:
   - Siempre genera mapas para todas las grillas independientemente del umbral

### Salidas del sistema de alertas
- **CSV de coberturas**: Distribución completa de todas las clases (0-8) en t1 y t2
- **Imágenes PNG**: Solo para grillas que cumplen criterios de alerta
- **Mapas interactivos**: Grillas alertadas resaltadas en rojo
- **CSV de transiciones**: Matriz de cambios entre clases específicas

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
python3 main.py --anio 2025 --mes 7
```

El proceso realizará automáticamente:
1. Lectura de las AOIs definidas en `AOI_DIR` (desde GCS o local).
2. Descarga del mosaico Dynamic World para los dos períodos (mes actual y año anterior).
3. Creación de grilla de análisis (10km × 10km) para cada páramo.
4. **Cálculo de transiciones** por grilla (píxeles que cambian entre clases específicas).
5. **Cálculo de coberturas** por grilla (distribución completa de todas las clases 0-8).
6. **Evaluación de alertas** según umbrales configurables en `ALERT_THRESHOLD_PP`.
7. **Generación de imágenes PNG** para grillas alertadas (Dynamic World y Sentinel-2).
8. **Generación de mapas interactivos** con overlays PNG y grillas alertadas resaltadas.
9. Creación del archivo `reporte_paramos_{anio}_{mes}.html`.
10. Subida automática a GCS (si `USE_GCS = True`).

## Salidas generadas

### Con GCS habilitado (por defecto)
Los archivos se suben automáticamente a Google Cloud Storage y los archivos temporales locales se eliminan. La URL del reporte final se muestra en consola.

### Con GCS deshabilitado
Cada ejecución produce una estructura local como esta:
```
temp_data/
└── 2025_7/
    ├── paramo_chingaza/
    │   ├── comparacion/
    │   │   ├── paramo_chingaza_transiciones.csv
    │   │   └── paramo_chingaza_coberturas.csv
    │   ├── mapas/
    │   │   ├── sentinel_mes.html
    │   │   ├── dw_mes.html
    │   │   └── imagenes/
    │   │       ├── dw/
    │   │       │   ├── dw_grid_1_2024-07-01.png
    │   │       │   ├── dw_grid_1_2025-07-01.png
    │   │       │   └── ...
    │   │       └── sentinel/
    │   │           ├── sentinel_grid_1_2024-07-01.png
    │   │           ├── sentinel_grid_1_2025-07-01.png
    │   │           └── ...
    │   └── grilla/
    │       └── grid_paramo_chingaza_10000m.geojson
    ├── reporte_paramos_2025_7.json
    └── reporte_paramos_2025_7.html
```

### Archivos CSV generados

#### 1. Transiciones (`{paramo}_transiciones.csv`)
Contiene cambios específicos de píxeles entre clases:
- `grid_id`: Identificador de la grilla
- `n_validos`: Total de píxeles válidos
- `n_1_a_otro`: Píxeles que eran clase 1 (árboles) y cambiaron
- `n_5_a_otro_no1`: Píxeles que eran clase 5 (arbustos) y cambiaron (excepto a clase 1)
- `pct_1_a_otro_clase1`: Porcentaje de cambio de clase 1
- `pct_5_a_otro_no1_clase5`: Porcentaje de cambio de clase 5

#### 2. Coberturas (`{paramo}_coberturas.csv`)
Distribución completa de todas las clases Dynamic World (0-8):
- `grid_id`: Identificador de la grilla
- `class_0_t1_pct` ... `class_8_t1_pct`: Porcentajes en período 1
- `class_0_t2_pct` ... `class_8_t2_pct`: Porcentajes en período 2
- `pp_class_0` ... `pp_class_8`: Cambio en puntos porcentuales (t2 - t1)
- `sum_t1`, `sum_t2`: Suma de verificación (debe ser ~100%)

### Mapas interactivos Folium

Los mapas HTML generados incluyen:
- **Capas base**: Mapa CartoDB Positron
- **Grilla de análisis**: Contornos negros (grillas normales) y rojos (grillas alertadas)
- **Polígono AOI**: Contorno azul del área de estudio
- **Imágenes superpuestas**:
  - Período anterior (año previo): Opacidad 100% (base)
  - Período actual (año actual): Opacidad 100% (superpuesto)
- **Números de grilla**: Marcadores con ID para identificación
- **Leyenda Dynamic World**: Clasificación de coberturas (solo en mapas DW)
- **Control de capas**: Toggle para activar/desactivar cada elemento

Las imágenes PNG solo se generan para grillas que cumplen los criterios de alerta.

## Ejemplo de salida
El reporte final (`reporte_paramos_2025_7.html`) incluye:
- **Resumen cuantitativo** de cambios de cobertura de árboles y arbustos/matorrales por páramo
- **Mapas interactivos** Dynamic World y Sentinel-2 con:
  - Comparación visual entre períodos (año anterior como base, año actual superpuesto)
  - Grillas alertadas resaltadas en rojo
  - Imágenes de alta resolución solo para áreas con cambios significativos
- **Indicadores agregados** por páramo:
  - Hectáreas de pérdida de árboles (clase 1)
  - Hectáreas de pérdida de arbustos (clase 5)
  - Grilla con mayor cambio identificada
- **Comentarios automáticos** sobre tendencias de pérdida o ganancia de cobertura
- **Logos y encabezado** institucional (SDP Bogotá)

### Clases de cobertura Dynamic World

| Clase | Color | Descripción |
|-------|-------|-------------|
| 0 | #419bdf | Water (Agua) |
| 1 | #397d49 | Trees (Árboles) |
| 2 | #88b053 | Grass (Pasto) |
| 3 | #7a87c6 | Flooded Vegetation (Vegetación inundada) |
| 4 | #e49635 | Crops (Cultivos) |
| 5 | #dfc35a | Shrub & Scrub (Arbustos y matorrales) |
| 6 | #c4281b | Built (Construido) |
| 7 | #a59b8f | Bare (Suelo desnudo) |
| 8 | #b39fe1 | Snow & Ice (Nieve y hielo) |

## Configuración avanzada

### Ajustar umbrales de alerta
Edita en [config.py](src/config.py):
```python
ALERT_THRESHOLD_PP = 5  # Es posible cambiar el umbral modificando el número de esta variable 
```

### Cambiar período de lookback
```python
LOOKBACK_DAYS = 365  # Días hacia atrás para mosaico (default: 1 año)
```

### Desactivar GCS
```python
USE_GCS = False  # Guardar solo localmente
```

### Tamaño de grilla
```python
GRID_SIZE = 10000  # Default: 10km × 10km (sin embargo, es posible cambiar el tamaño de la grilla, por ejemplo, a 5000 para 5km × 5km)
```


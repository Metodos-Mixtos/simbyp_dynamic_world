# Dynamic World Land Cover Analysis

Este repositorio permite generar mapas de clasificación de cobertura terrestre utilizando datos de Dynamic World (Google Earth Engine) para dos trimestres dados y una geometría definida por el usuario.


## Uso

Cambiar este path en .env a la ruta de OneDrive

ONE_DRIVE_PATH = "/Users/javierguerra/Library/CloudStorage/OneDrive-SharedLibraries-VestigiumMétodosMixtosAplicadosSAS/MMC - General - SDP - Monitoreo de Bosques" 

### 1. Ejecutar el pipeline completo:
```bash
python dynamic_world/main.py
```
Esto realiza:
- Autenticación con GEE
- Creación de grilla sobre AOI
- Descarga de imágenes de Dynamic World para dos trimestres
- Cálculo de estadísticas por celda y comparación
- Generación de mapas comparativos y por trimestre

### 2. Visualizar mapas
Los mapas se guardan como `.png` en `data/output/maps/`.




from pathlib import Path
from PIL import Image
import os

def fix_png(img_path):
    try:
        with Image.open(img_path) as im:
            im = im.convert('RGBA')
            datas = im.getdata()
            newData = []
            for item in datas:
                # Si el pixel es negro puro, lo hacemos transparente
                if item[0] == 0 and item[1] == 0 and item[2] == 0:
                    newData.append((0, 0, 0, 0))
                else:
                    newData.append(item)
            im.putdata(newData)
            im.save(img_path, format='PNG')
        print(f"[OK] PNG corregido: {img_path}")
    except Exception as e:
        print(f"[ERROR] {img_path}: {e}")

# Buscar todos los PNGs en temp_data/*/*/mapas/**/*.png
temp_data = Path(__file__).parent.parent / 'temp_data'
for periodo in temp_data.iterdir():
    if periodo.is_dir():
        for paramo in periodo.iterdir():
            mapas = paramo / 'mapas'
            if mapas.exists():
                for png in mapas.rglob('*.png'):
                    fix_png(png)

print("\nListo. Todos los PNGs han sido corregidos (RGBA y fondo negro transparente).")

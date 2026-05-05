#!/usr/bin/env python3
"""
Wrapper para ejecutar main.py con parámetros automáticos.
Ejecuta el análisis para el mes anterior al actual.
Ejemplo: Si hoy es 5 de Mayo 2025, analiza Abril 2025.
"""

import subprocess
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta

def get_previous_month():
    """
    Retorna año y mes del mes anterior al actual.
    
    Returns:
        tuple: (año, mes)
    """
    today = datetime.now()
    previous_month = today - relativedelta(months=1)
    return previous_month.year, previous_month.month

def main():
    """Ejecuta main.py con parámetros automáticos."""
    year, month = get_previous_month()
    
    print(f"🗓️  Ejecutando análisis para {month}/{year}")
    print(f"   Fecha actual: {datetime.now().strftime('%d/%m/%Y')}")
    print("-" * 60)
    
    # Ejecutar main.py con los parámetros calculados
    cmd = ["python", "main.py", "--anio", str(year), "--mes", str(month)]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar main.py: {e}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

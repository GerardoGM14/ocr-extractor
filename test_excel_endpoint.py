"""
Script de prueba para el endpoint de Excel
Ejecutar: python test_excel_endpoint.py
"""

import requests
import json
from pathlib import Path

# Configuración
BASE_URL = "http://localhost:8000"
EMAIL = "tu_email@autorizado.com"  # Cambiar por un email autorizado
YEAR = 2025
MONTH = "Noviembre"

def test_excel_endpoint():
    """Prueba el endpoint de Excel paso a paso."""
    
    print("=" * 60)
    print("PRUEBA DEL ENDPOINT DE EXCEL")
    print("=" * 60)
    print()
    
    # Paso 1: Listar archivos procesados para obtener un request_id
    print("1. Obteniendo lista de archivos procesados...")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/processed-files?limit=5")
        response.raise_for_status()
        data = response.json()
        
        if not data.get("files"):
            print("   ⚠ No hay archivos procesados. Necesitas procesar un PDF primero.")
            print()
            print("   Para procesar un PDF:")
            print("   1. Sube un PDF con: POST /api/v1/upload-pdf")
            print("   2. Procesa con: POST /api/v1/process-pdf")
            print("   3. Obtén el request_id de la respuesta")
            return
        
        # Mostrar archivos disponibles
        print(f"   ✓ Encontrados {len(data['files'])} archivos procesados")
        print()
        print("   Archivos disponibles:")
        for i, file_info in enumerate(data['files'][:5], 1):
            request_id = file_info.get("request_id", "N/A")
            filename = file_info.get("filename", "N/A")
            excel_url = file_info.get("excel_download_url", "N/A")
            print(f"   {i}. {filename}")
            print(f"      request_id: {request_id}")
            print(f"      excel_download_url: {excel_url}")
            print()
        
        # Usar el primer archivo para la prueba
        first_file = data['files'][0]
        request_id = first_file.get("request_id")
        excel_url = first_file.get("excel_download_url")
        
        if not request_id:
            print("   ✗ No se encontró request_id en los archivos")
            return
        
        print(f"   Usando request_id: {request_id}")
        print()
        
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Paso 2: Probar endpoint de export-excel
    print("2. Probando GET /api/v1/export-excel/{request_id}...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/export-excel/{request_id}",
            allow_redirects=False  # No seguir redirecciones para ver el código
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 302:
            # Redirección (esperado)
            redirect_url = response.headers.get("Location", "")
            print(f"   ✓ Redirección exitosa a: {redirect_url}")
            print()
            
            # Paso 3: Seguir la redirección y descargar el Excel
            print("3. Descargando Excel desde /public/{filename}...")
            full_url = f"{BASE_URL}{redirect_url}"
            excel_response = requests.get(full_url)
            
            if excel_response.status_code == 200:
                # Guardar el Excel
                excel_filename = redirect_url.split("/")[-1]
                output_path = Path("test_download") / excel_filename
                output_path.parent.mkdir(exist_ok=True)
                
                with open(output_path, "wb") as f:
                    f.write(excel_response.content)
                
                print(f"   ✓ Excel descargado exitosamente: {output_path}")
                print(f"   Tamaño: {len(excel_response.content)} bytes")
            else:
                print(f"   ✗ Error descargando Excel: {excel_response.status_code}")
                print(f"   Respuesta: {excel_response.text[:200]}")
        
        elif response.status_code == 200:
            # Respuesta directa (también válido)
            print("   ✓ Excel recibido directamente")
            excel_filename = f"excel_{request_id[:8]}.xlsx"
            output_path = Path("test_download") / excel_filename
            output_path.parent.mkdir(exist_ok=True)
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            print(f"   ✓ Excel guardado en: {output_path}")
            print(f"   Tamaño: {len(response.content)} bytes")
        
        else:
            print(f"   ✗ Error: {response.status_code}")
            print(f"   Respuesta: {response.text[:500]}")
    
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Error: {e}")
    
    print()
    print("=" * 60)
    print("PRUEBA COMPLETADA")
    print("=" * 60)

if __name__ == "__main__":
    test_excel_endpoint()


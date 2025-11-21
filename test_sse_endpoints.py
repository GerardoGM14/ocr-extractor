"""
Script de prueba para endpoints SSE (Server-Sent Events)

Uso:
    # Probar endpoint unitario
    python test_sse_endpoints.py --request-id abc123
    
    # Probar endpoint batch (periodo)
    python test_sse_endpoints.py --periodo-id 2025-11-onshore
    
    # Probar ambos
    python test_sse_endpoints.py --request-id abc123 --periodo-id 2025-11-onshore
"""

import argparse
import requests
import json
import sys
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8000"  # Cambiar si tu servidor está en otro puerto


def test_unitario_sse(request_id: str):
    """Prueba el endpoint SSE unitario."""
    print(f"\n{'='*60}")
    print(f"Probando SSE Unitario - Request ID: {request_id}")
    print(f"{'='*60}\n")
    
    url = f"{BASE_URL}/api/v1/process-status-stream/{request_id}"
    
    print(f"URL: {url}")
    print(f"Conectando...\n")
    
    try:
        response = requests.get(url, stream=True, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            print(f"Respuesta: {response.text}")
            return
        
        print("✅ Conexión establecida. Recibiendo eventos...\n")
        print("-" * 60)
        
        event_count = 0
        start_time = datetime.now()
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                
                # Parsear formato SSE
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remover "data: "
                    try:
                        data = json.loads(data_str)
                        event_count += 1
                        
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] Evento #{event_count}")
                        print(f"  Status: {data.get('status', 'N/A')}")
                        print(f"  Progress: {data.get('progress', 0)}%")
                        print(f"  Message: {data.get('message', 'N/A')}")
                        
                        if data.get('pages_processed'):
                            print(f"  Pages: {data.get('pages_processed')}")
                        
                        if data.get('error'):
                            print(f"  ❌ Error: {data.get('error')}")
                        
                        if data.get('download_url'):
                            print(f"  📥 Download: {data.get('download_url')}")
                        
                        if data.get('finished'):
                            print(f"\n✅ Procesamiento finalizado!")
                            break
                        
                        if data.get('status') in ['completed', 'failed']:
                            print(f"\n✅ Stream cerrado (status: {data.get('status')})")
                            break
                            
                    except json.JSONDecodeError:
                        print(f"⚠️  No se pudo parsear JSON: {data_str}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"Total eventos recibidos: {event_count}")
        print(f"Tiempo transcurrido: {elapsed:.2f} segundos")
        print(f"{'='*60}\n")
        
    except requests.exceptions.Timeout:
        print("❌ Timeout: La conexión se cerró después de 60 segundos")
    except requests.exceptions.ConnectionError:
        print(f"❌ Error de conexión: ¿Está el servidor corriendo en {BASE_URL}?")
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")


def test_batch_sse(periodo_id: str):
    """Prueba el endpoint SSE batch (por periodo)."""
    print(f"\n{'='*60}")
    print(f"Probando SSE Batch - Periodo ID: {periodo_id}")
    print(f"{'='*60}\n")
    
    url = f"{BASE_URL}/api/v1/periodos/{periodo_id}/process-status-stream"
    
    print(f"URL: {url}")
    print(f"Conectando...\n")
    
    try:
        response = requests.get(url, stream=True, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            print(f"Respuesta: {response.text}")
            return
        
        print("✅ Conexión establecida. Recibiendo eventos...\n")
        print("-" * 60)
        
        event_count = 0
        start_time = datetime.now()
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                
                # Parsear formato SSE
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remover "data: "
                    try:
                        data = json.loads(data_str)
                        event_count += 1
                        
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] Evento #{event_count}")
                        print(f"  Periodo: {data.get('periodo_id', 'N/A')}")
                        print(f"  Total Jobs: {data.get('total_jobs', 0)}")
                        print(f"  ✅ Completados: {data.get('completed', 0)}")
                        print(f"  🔄 Procesando: {data.get('processing', 0)}")
                        print(f"  ⏳ En cola: {data.get('queued', 0)}")
                        print(f"  ❌ Fallidos: {data.get('failed', 0)}")
                        
                        if data.get('jobs'):
                            print(f"\n  Jobs individuales:")
                            for job in data.get('jobs', []):
                                status_emoji = {
                                    'completed': '✅',
                                    'processing': '🔄',
                                    'queued': '⏳',
                                    'failed': '❌',
                                    'not_found': '⚠️'
                                }.get(job.get('status'), '❓')
                                
                                print(f"    {status_emoji} {job.get('request_id', 'N/A')[:8]}... "
                                      f"| {job.get('status', 'N/A')} | "
                                      f"{job.get('progress', 0)}% | "
                                      f"{job.get('message', 'N/A')[:50]}")
                        
                        if data.get('error'):
                            print(f"  ❌ Error: {data.get('error')}")
                        
                        if data.get('finished'):
                            print(f"\n✅ Todos los jobs del periodo han terminado!")
                            break
                            
                    except json.JSONDecodeError:
                        print(f"⚠️  No se pudo parsear JSON: {data_str}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"Total eventos recibidos: {event_count}")
        print(f"Tiempo transcurrido: {elapsed:.2f} segundos")
        print(f"{'='*60}\n")
        
    except requests.exceptions.Timeout:
        print("❌ Timeout: La conexión se cerró después de 60 segundos")
    except requests.exceptions.ConnectionError:
        print(f"❌ Error de conexión: ¿Está el servidor corriendo en {BASE_URL}?")
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")


def list_available_request_ids():
    """Lista request_ids disponibles para probar."""
    print("\n📋 Obteniendo request_ids disponibles...\n")
    
    try:
        # Intentar obtener de processed files
        url = f"{BASE_URL}/api/v1/processed-files"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            files = data.get('files', [])
            
            if files:
                print("Request IDs disponibles (de processed-files):")
                for i, file_info in enumerate(files[:10], 1):  # Mostrar solo los primeros 10
                    req_id = file_info.get('request_id', 'N/A')
                    status = file_info.get('status', 'N/A')
                    print(f"  {i}. {req_id} (status: {status})")
                
                if len(files) > 10:
                    print(f"  ... y {len(files) - 10} más")
                
                return [f.get('request_id') for f in files if f.get('request_id')]
        
        print("⚠️  No se encontraron request_ids. Prueba procesando un PDF primero.")
        return []
        
    except Exception as e:
        print(f"⚠️  Error obteniendo request_ids: {e}")
        return []


def list_available_periodos():
    """Lista periodos disponibles para probar."""
    print("\n📋 Obteniendo periodos disponibles...\n")
    
    try:
        url = f"{BASE_URL}/api/v1/periodos?limit=10"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            periodos = data.get('periodos', [])
            
            if periodos:
                print("Periodos disponibles:")
                for i, periodo in enumerate(periodos, 1):
                    periodo_id = periodo.get('periodo_id', 'N/A')
                    estado = periodo.get('estado', 'N/A')
                    registros = periodo.get('registros', 0)
                    print(f"  {i}. {periodo_id} (estado: {estado}, registros: {registros})")
                
                return [p.get('periodo_id') for p in periodos if p.get('periodo_id')]
        
        print("⚠️  No se encontraron periodos. Crea un periodo primero.")
        return []
        
    except Exception as e:
        print(f"⚠️  Error obteniendo periodos: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Prueba endpoints SSE (Server-Sent Events)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Probar con un request_id específico
  python test_sse_endpoints.py --request-id abc123-def456-ghi789
  
  # Probar con un periodo_id
  python test_sse_endpoints.py --periodo-id 2025-11-onshore
  
  # Listar request_ids disponibles
  python test_sse_endpoints.py --list-request-ids
  
  # Listar periodos disponibles
  python test_sse_endpoints.py --list-periodos
  
  # Probar ambos
  python test_sse_endpoints.py --request-id abc123 --periodo-id 2025-11-onshore
        """
    )
    
    parser.add_argument(
        '--request-id',
        type=str,
        help='Request ID para probar endpoint unitario'
    )
    
    parser.add_argument(
        '--periodo-id',
        type=str,
        help='Periodo ID para probar endpoint batch'
    )
    
    parser.add_argument(
        '--list-request-ids',
        action='store_true',
        help='Listar request_ids disponibles'
    )
    
    parser.add_argument(
        '--list-periodos',
        action='store_true',
        help='Listar periodos disponibles'
    )
    
    parser.add_argument(
        '--base-url',
        type=str,
        default='http://localhost:8000',
        help='URL base del servidor (default: http://localhost:8000)'
    )
    
    args = parser.parse_args()
    
    # Actualizar BASE_URL si se proporciona
    global BASE_URL
    BASE_URL = args.base_url
    
    # Listar opciones si se solicita
    if args.list_request_ids:
        list_available_request_ids()
        return
    
    if args.list_periodos:
        list_available_periodos()
        return
    
    # Probar endpoints
    if not args.request_id and not args.periodo_id:
        print("❌ Debes proporcionar --request-id o --periodo-id")
        print("\n💡 Usa --list-request-ids o --list-periodos para ver opciones disponibles")
        parser.print_help()
        return
    
    if args.request_id:
        test_unitario_sse(args.request_id)
    
    if args.periodo_id:
        test_batch_sse(args.periodo_id)


if __name__ == "__main__":
    main()



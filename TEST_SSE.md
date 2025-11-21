# Guía de Pruebas para Endpoints SSE

## 🚀 Opciones para Probar

### Opción 1: Script Python (Recomendado)

He creado un script de prueba completo: `test_sse_endpoints.py`

#### Uso básico:

```bash
# 1. Probar endpoint unitario (por request_id)
python test_sse_endpoints.py --request-id abc123-def456-ghi789

# 2. Probar endpoint batch (por periodo_id)
python test_sse_endpoints.py --periodo-id 2025-11-onshore

# 3. Listar request_ids disponibles
python test_sse_endpoints.py --list-request-ids

# 4. Listar periodos disponibles
python test_sse_endpoints.py --list-periodos

# 5. Si tu servidor está en otro puerto/IP
python test_sse_endpoints.py --request-id abc123 --base-url http://192.168.0.63:8000
```

#### Ejemplo de salida:

```
============================================================
Probando SSE Unitario - Request ID: abc123-def456-ghi789
============================================================

URL: http://localhost:8000/api/v1/process-status-stream/abc123-def456-ghi789
Conectando...

✅ Conexión establecida. Recibiendo eventos...

------------------------------------------------------------

[14:30:15] Evento #1
  Status: queued
  Progress: 0%
  Message: Esperando en cola de procesamiento...

[14:30:16] Evento #2
  Status: processing
  Progress: 10%
  Message: Procesando PDF con OCR...

[14:30:20] Evento #3
  Status: processing
  Progress: 45%
  Message: Procesando página 3 de 7...
  Pages: 3

[14:30:25] Evento #4
  Status: completed
  Progress: 100%
  Message: Procesamiento completado: 7 páginas
  Pages: 7
  📥 Download: /public/file.zip

✅ Stream cerrado (status: completed)
```

---

### Opción 2: Usando `curl` (Terminal)

#### Endpoint Unitario:

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8000/api/v1/process-status-stream/abc123-def456-ghi789
```

#### Endpoint Batch:

```bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8000/api/v1/periodos/2025-11-onshore/process-status-stream
```

**Nota:** `-N` desactiva el buffering para ver eventos en tiempo real.

---

### Opción 3: Script Python Simple (Manual)

Crea un archivo `test_simple.py`:

```python
import requests
import json

# Endpoint unitario
request_id = "abc123-def456-ghi789"  # Reemplaza con un request_id real
url = f"http://localhost:8000/api/v1/process-status-stream/{request_id}"

print(f"Conectando a: {url}\n")

response = requests.get(url, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            data_str = line_str[6:]
            data = json.loads(data_str)
            print(f"Status: {data.get('status')} | Progress: {data.get('progress')}% | {data.get('message')}")
            
            if data.get('status') in ['completed', 'failed']:
                break
```

Ejecuta:
```bash
python test_simple.py
```

---

### Opción 4: Desde el Navegador (JavaScript Console)

Abre la consola del navegador (F12) y ejecuta:

```javascript
// Endpoint unitario
const eventSource = new EventSource('http://localhost:8000/api/v1/process-status-stream/abc123-def456-ghi789');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Estado:', data.status, '| Progreso:', data.progress + '%', '|', data.message);
    
    if (data.status === 'completed' || data.status === 'failed') {
        eventSource.close();
        console.log('✅ Stream cerrado');
    }
};

eventSource.onerror = (error) => {
    console.error('Error en SSE:', error);
    eventSource.close();
};
```

---

## 📋 Pasos para Probar

### 1. Asegúrate de que el servidor esté corriendo

```bash
python api_server.py
```

### 2. Obtén un `request_id` válido

**Opción A:** Procesa un PDF primero:
```bash
# 1. Sube un PDF
curl -X POST "http://localhost:8000/api/v1/upload-pdf" \
  -F "pdf_file=@mi_archivo.pdf" \
  -F "email=tu@email.com" \
  -F "year=2025" \
  -F "month=Noviembre"

# 2. Obtén el file_id de la respuesta, luego procesa:
curl -X POST "http://localhost:8000/api/v1/process-pdf" \
  -F "file_id=TU_FILE_ID_AQUI"

# 3. El request_id estará en la respuesta
```

**Opción B:** Usa el script para listar:
```bash
python test_sse_endpoints.py --list-request-ids
```

### 3. Prueba el SSE

```bash
# Reemplaza con tu request_id real
python test_sse_endpoints.py --request-id TU_REQUEST_ID_AQUI
```

---

## 🔍 Verificación de Funcionamiento

### ✅ Señales de que funciona:

1. **Conexión establecida:** Verás "✅ Conexión establecida"
2. **Eventos recibidos:** Verás eventos con timestamps
3. **Actualizaciones en tiempo real:** Los valores cambian sin recargar
4. **Cierre automático:** El stream se cierra cuando el job termina

### ❌ Problemas comunes:

1. **"Error de conexión":**
   - Verifica que el servidor esté corriendo
   - Verifica la URL (puerto, IP)

2. **"Request ID no encontrado":**
   - Usa un `request_id` válido
   - Lista los disponibles con `--list-request-ids`

3. **"Timeout":**
   - Normal si el job tarda mucho
   - El timeout es de 30 minutos

4. **No se reciben eventos:**
   - Verifica que el job esté activo
   - Verifica que el servidor esté procesando

---

## 🎯 Casos de Prueba Recomendados

### 1. Job en Cola (queued)
```bash
# Procesa un PDF cuando ya hay 3 jobs corriendo
# El nuevo job quedará en cola
python test_sse_endpoints.py --request-id NUEVO_REQUEST_ID
```

### 2. Job Procesando (processing)
```bash
# Procesa un PDF pequeño para ver el progreso
python test_sse_endpoints.py --request-id REQUEST_ID_PEQUENO
```

### 3. Job Completado (completed)
```bash
# Usa un request_id de un job ya completado
# Verás el estado final y URLs de descarga
python test_sse_endpoints.py --request-id REQUEST_ID_COMPLETADO
```

### 4. Batch Completo (periodo)
```bash
# Procesa múltiples PDFs con el mismo periodo_id
# Luego monitorea el periodo completo
python test_sse_endpoints.py --periodo-id 2025-11-onshore
```

---

## 📊 Interpretación de Eventos

### Endpoint Unitario:
```json
{
  "request_id": "abc123",
  "status": "processing",      // queued | processing | completed | failed
  "progress": 45,              // 0-100
  "message": "Procesando...",  // Mensaje descriptivo
  "pages_processed": 3,         // Páginas procesadas
  "processing_time": 12.5,     // Tiempo en segundos
  "download_url": "/public/...", // URL del ZIP (si completado)
  "excel_download_url": "/public/...", // URL del Excel (si completado)
  "error": null                // Error si falló
}
```

### Endpoint Batch:
```json
{
  "periodo_id": "2025-11-onshore",
  "total_jobs": 5,
  "completed": 2,
  "processing": 1,
  "queued": 2,
  "failed": 0,
  "jobs": [
    {
      "request_id": "abc123",
      "status": "completed",
      "progress": 100,
      "message": "...",
      "pages_processed": 7
    }
  ]
}
```

---

## 💡 Tips

1. **Mantén el servidor corriendo** mientras pruebas
2. **Usa PDFs pequeños** para pruebas rápidas
3. **Observa los timestamps** para verificar que es en tiempo real
4. **Interrumpe con Ctrl+C** si necesitas detener la prueba
5. **Revisa los logs del servidor** para ver actividad

---

## 🐛 Debugging

Si algo no funciona:

1. **Verifica logs del servidor:**
   ```bash
   # Deberías ver logs cuando se conecta al SSE
   ```

2. **Prueba el endpoint normal primero:**
   ```bash
   curl http://localhost:8000/api/v1/process-status/TU_REQUEST_ID
   ```

3. **Verifica CORS** (si pruebas desde navegador):
   - El servidor debe tener CORS habilitado
   - Verifica `config/config.json`

4. **Verifica que el job exista:**
   ```bash
   python test_sse_endpoints.py --list-request-ids
   ```

---

¡Listo para probar! 🚀



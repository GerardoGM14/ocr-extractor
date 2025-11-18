# Tutorial: Pruebas de la API ExtractorOCR

## 📋 Índice
1. [Iniciar el Servidor](#1-iniciar-el-servidor)
2. [Acceder a Swagger UI](#2-acceder-a-swagger-ui)
3. [Probar Endpoints de Periodos](#3-probar-endpoints-de-periodos)
4. [Probar Endpoints de Dashboard](#4-probar-endpoints-de-dashboard)
5. [Probar Flujo Completo](#5-probar-flujo-completo)
6. [Probar con cURL (Opcional)](#6-probar-con-curl-opcional)

---

## 1. Iniciar el Servidor

### Paso 1.1: Activar el entorno virtual
```bash
# En Windows PowerShell
.\venv\Scripts\activate

# Deberías ver (venv) al inicio de la línea
```

### Paso 1.2: Ejecutar el servidor
```bash
python api_server.py
```

**Salida esperada:**
```
============================================================
ExtractorOCR API Server
============================================================

Servidor iniciando...
Documentación disponible en: http://localhost:8000/docs
API disponible en: http://localhost:8000/api/v1/

Presiona Ctrl+C para detener el servidor
```

✅ **Si ves esto, el servidor está funcionando correctamente.**

---

## 2. Acceder a Swagger UI

### Paso 2.1: Abrir en el navegador
Abre tu navegador y ve a:
```
http://localhost:8000/docs
```

Verás la documentación interactiva de todos los endpoints.

### Paso 2.2: Explorar las secciones
En Swagger UI verás estas secciones:
- **General** - Health check
- **Upload** - Subir PDFs
- **Processing** - Procesar PDFs
- **Files** - Listar archivos
- **Dashboard** - Estadísticas y análisis
- **Periodos** - Gestión de periodos
- **Learning** - Sistema de aprendizaje
- **Export** - Exportar Excel
- **Public** - Descargar archivos

---

## 3. Probar Endpoints de Periodos

### 🆕 Paso 3.1: Crear un Periodo

1. En Swagger UI, busca `POST /api/v1/periodos`
2. Haz clic en "Try it out"
3. Modifica el body JSON:
```json
{
  "periodo": "10/2025",
  "tipo": "offshore"
}
```
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "periodo": {
    "periodo_id": "2025-10-offshore",
    "periodo": "10/2025",
    "tipo": "offshore",
    "estado": "vacio",
    "registros": 0,
    "created_at": "2025-01-15T10:00:00.000000"
  }
}
```

✅ **Copia el `periodo_id` para usarlo después: `2025-10-offshore`**

---

### 📋 Paso 3.2: Listar Periodos

1. Busca `GET /api/v1/periodos`
2. Haz clic en "Try it out"
3. Opcionalmente, puedes agregar parámetros:
   - `tipo`: "offshore" o "onshore"
   - `estado`: "vacio", "procesado", "pendiente", etc.
   - `search`: texto para buscar
   - `limit`: 15 (por defecto)
   - `offset`: 0 (por defecto)
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "total": 1,
  "periodos": [
    {
      "periodo_id": "2025-10-offshore",
      "periodo": "10/2025",
      "tipo": "offshore",
      "estado": "vacio",
      "registros": 0,
      "created_at": "2025-01-15T10:00:00.000000"
    }
  ]
}
```

---

### 🔍 Paso 3.3: Ver Detalle de un Periodo

1. Busca `GET /api/v1/periodos/{periodo_id}`
2. Haz clic en "Try it out"
3. En el campo `periodo_id`, pega: `2025-10-offshore`
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "periodo": {
    "periodo_id": "2025-10-offshore",
    "periodo": "10/2025",
    "tipo": "offshore",
    "estado": "vacio",
    "registros": 0,
    "created_at": "2025-01-15T10:00:00.000000"
  },
  "archivos": [],
  "total_archivos": 0
}
```

---

### ✏️ Paso 3.4: Actualizar un Periodo

1. Busca `PUT /api/v1/periodos/{periodo_id}`
2. Haz clic en "Try it out"
3. En `periodo_id`: `2025-10-offshore`
4. En el body JSON, modifica lo que quieras:
```json
{
  "estado": "pendiente",
  "registros": 5
}
```
5. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "periodo": {
    "periodo_id": "2025-10-offshore",
    "periodo": "10/2025",
    "tipo": "offshore",
    "estado": "pendiente",  ← Actualizado
    "registros": 5,  ← Actualizado
    "created_at": "2025-01-15T10:00:00.000000"
  }
}
```

---

### 🔒 Paso 3.5: Bloquear un Periodo

1. Busca `POST /api/v1/periodos/{periodo_id}/bloquear`
2. Haz clic en "Try it out"
3. En `periodo_id`: `2025-10-offshore`
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "message": "Periodo 2025-10-offshore bloqueado"
}
```

Si ahora ves el detalle del periodo, el estado debería ser "cerrado".

---

### 🗑️ Paso 3.6: Eliminar un Periodo (Opcional)

1. Busca `DELETE /api/v1/periodos/{periodo_id}`
2. Haz clic en "Try it out"
3. En `periodo_id`: `2025-10-offshore`
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "message": "Periodo 2025-10-offshore eliminado"
}
```

---

## 4. Probar Endpoints de Dashboard

### 📊 Paso 4.1: Estadísticas Globales

1. Busca `GET /api/v1/dashboard/stats`
2. Haz clic en "Try it out"
3. Opcionalmente, agrega parámetros:
   - `fecha_inicio`: "2024-01-01"
   - `fecha_fin`: "2024-12-31"
   - `moneda`: "USD"
4. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "monto_total_global": 2450000.0,
  "total_horas_global": 1875.0,
  "currency": "USD"
}
```

⚠️ **Nota:** 
- Si no hay JSONs procesados, los valores serán 0.0
- **IMPORTANTE:** Actualmente lee de archivos JSON (temporal). Cuando tengas conexión a SQL Server, se migrará a leer de la base de datos. Ver `MIGRACION_SQL_SERVER.md` para más detalles.

---

### 📈 Paso 4.2: Análisis Off-Shore/On-Shore

1. Busca `GET /api/v1/dashboard/analytics`
2. Haz clic en "Try it out"
3. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "offshore": null,
  "onshore": null
}
```

⚠️ **Nota:** 
- Por ahora retorna null porque la lógica está pendiente de implementar.
- Cuando tengas SQL Server, leerá de las tablas `MCOMPROBANTE` y `MJORNADA` agrupadas por tipo (offshore/onshore).

---

### 🚫 Paso 4.3: Conceptos Rechazados

1. Busca `GET /api/v1/dashboard/rejected-concepts`
2. Haz clic en "Try it out"
3. Haz clic en "Execute"

**Respuesta esperada:**
```json
{
  "success": true,
  "total": 0,
  "concepts": []
}
```

⚠️ **Nota:** 
- Por ahora retorna vacío porque la lógica está pendiente.
- Cuando tengas SQL Server, leerá conceptos rechazados de la tabla `MCOMPROBANTE` con estado 'rechazado'.

---

## 5. Probar Flujo Completo

### 🔄 Flujo: Crear Periodo → Subir PDF → Procesar con Periodo

#### Paso 5.1: Crear Periodo
```
POST /api/v1/periodos
Body: {"periodo": "10/2025", "tipo": "offshore"}
→ Guarda el periodo_id: "2025-10-offshore"
```

#### Paso 5.2: Subir PDF
```
POST /api/v1/upload-pdf
Form data:
  - pdf_file: [selecciona un PDF]
  - email: victor.cabeza@newmont.com
  - year: 2025
  - month: Octubre
→ Guarda el file_id
```

#### Paso 5.3: Procesar PDF con Periodo
```
POST /api/v1/process-pdf
Form data:
  - file_id: [el file_id del paso anterior]
  - periodo_id: 2025-10-offshore  ← IMPORTANTE: Agregar esto
  - save_files: true
→ Guarda el request_id
```

#### Paso 5.4: Verificar que se asoció al Periodo
```
GET /api/v1/periodos/2025-10-offshore
→ Deberías ver el archivo en la lista de "archivos"
→ El estado debería cambiar a "procesado" o "pendiente"
→ registros debería ser 1
```

---

## 6. Probar con cURL (Opcional)

Si prefieres usar la línea de comandos:

### Crear Periodo
```bash
curl -X POST "http://localhost:8000/api/v1/periodos" \
  -H "Content-Type: application/json" \
  -d "{\"periodo\": \"10/2025\", \"tipo\": \"offshore\"}"
```

### Listar Periodos
```bash
curl -X GET "http://localhost:8000/api/v1/periodos"
```

### Ver Detalle
```bash
curl -X GET "http://localhost:8000/api/v1/periodos/2025-10-offshore"
```

### Estadísticas Dashboard
```bash
curl -X GET "http://localhost:8000/api/v1/dashboard/stats?moneda=USD"
```

---

## 🐛 Solución de Problemas

### Error: "Periodo no encontrado"
- Verifica que el `periodo_id` sea correcto
- Usa `GET /api/v1/periodos` para ver la lista de periodos disponibles

### Error: "Correo no autorizado"
- Verifica que el email esté en `config/allowed_emails.json`
- Agrega tu email si no está

### Dashboard retorna 0 o vacío
- Necesitas tener JSONs procesados en `output/api/structured/`
- Procesa algunos PDFs primero

### Error al iniciar el servidor
- Verifica que tengas todas las dependencias: `pip install -r requirements.txt`
- Verifica que `config/gemini_config.json` exista

---

## 📝 Notas Importantes

1. **Periodos se guardan en:** `periodos_tracking.json` (en la raíz del proyecto)
2. **JSONs estructurados están en:** `output/api/structured/`
3. **El Dashboard lee de:** Los JSONs estructurados (no depende de periodos)
4. **Los periodos organizan:** Archivos ya procesados (no procesan por sí mismos)

---

## ✅ Checklist de Pruebas

- [ ] Servidor inicia correctamente
- [ ] Puedo crear un periodo
- [ ] Puedo listar periodos
- [ ] Puedo ver detalle de un periodo
- [ ] Puedo actualizar un periodo
- [ ] Puedo bloquear un periodo
- [ ] Puedo subir un PDF
- [ ] Puedo procesar un PDF con periodo_id
- [ ] El periodo se actualiza automáticamente después de procesar
- [ ] El Dashboard muestra estadísticas (si hay JSONs procesados)

---

¡Listo para probar! 🚀

Si encuentras algún error o algo no funciona como esperas, compártelo y lo ajustamos.


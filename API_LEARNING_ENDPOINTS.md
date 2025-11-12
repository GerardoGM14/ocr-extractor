# 📚 Endpoints de Sistema de Aprendizaje - API

## 🚀 Endpoints Disponibles

### 1. **GET /api/v1/learning/errors**
Obtiene lista de errores registrados.

**Query Parameters:**
- `limit` (opcional, default: 100): Número máximo de errores a retornar

**Ejemplo:**
```bash
GET http://localhost:8000/api/v1/learning/errors?limit=50
```

**Respuesta:**
```json
{
  "success": true,
  "total": 50,
  "errors": [
    {
      "error_id": "error_20250103_143022_0001",
      "timestamp": "2025-01-03T14:30:22",
      "pdf_name": "factura_china_001.pdf",
      "page_number": 1,
      "error_type": "missing_field",
      "error_message": "Campo 'tNumero' está vacío o no se pudo extraer",
      "field_name": "tNumero",
      "context": {...}
    }
  ]
}
```

---

### 2. **GET /api/v1/learning/errors/summary**
Obtiene un resumen estadístico de errores.

**Ejemplo:**
```bash
GET http://localhost:8000/api/v1/learning/errors/summary
```

**Respuesta:**
```json
{
  "success": true,
  "total_errors": 15,
  "error_types": {
    "missing_field": 10,
    "incorrect_value": 5
  },
  "most_common_fields": {
    "tNumero": 8,
    "mdivisa": 4,
    "mcomprobante_detalle": 3
  },
  "recent_errors": [...]
}
```

---

### 3. **POST /api/v1/learning/analyze**
Analiza errores con Gemini y genera sugerencias de mejora.

**Query Parameters:**
- `limit` (opcional, default: 20, máximo: 100): Número de errores a analizar

**Ejemplo:**
```bash
POST http://localhost:8000/api/v1/learning/analyze?limit=20
```

**Respuesta:**
```json
{
  "success": true,
  "analysis": {
    "patterns": ["patrón 1", "patrón 2"],
    "root_causes": ["causa 1", "causa 2"],
    "prompt_improvements": ["mejora 1", "mejora 2"],
    "extraction_improvements": ["mejora 1", "mejora 2"],
    "recommendations": ["recomendación 1", "recomendación 2"]
  },
  "patterns": [
    {
      "type": "frequent_missing_field",
      "field_name": "tNumero",
      "frequency": 8,
      "description": "Campo 'tNumero' falta en 8 documentos",
      "severity": "high"
    }
  ],
  "suggestions": [
    {
      "type": "improve_field_extraction",
      "field_name": "tNumero",
      "description": "Mejorar extracción del campo 'tNumero'",
      "recommendation": "Revisar regex para números de factura chinos",
      "priority": "high"
    }
  ],
  "analyzed_at": "2025-01-03T14:35:00",
  "total_errors_analyzed": 20
}
```

**⚠️ Nota:** Este endpoint usa Gemini AI y puede tomar varios segundos en completarse.

---

### 4. **GET /api/v1/learning/suggestions**
Obtiene sugerencias de mejora generadas previamente.

**Ejemplo:**
```bash
GET http://localhost:8000/api/v1/learning/suggestions
```

**Respuesta:**
```json
{
  "success": true,
  "total": 2,
  "suggestions": [
    {
      "file": "analysis_20250103_143500.json",
      "analyzed_at": "2025-01-03T14:35:00",
      "errors_analyzed": 20,
      "analysis": {...}
    }
  ]
}
```

---

### 5. **GET /api/v1/learning/prompts**
Obtiene información sobre versiones de prompts.

**Query Parameters:**
- `history_limit` (opcional, default: 10): Número de versiones históricas a retornar

**Ejemplo:**
```bash
GET http://localhost:8000/api/v1/learning/prompts?history_limit=5
```

**Respuesta:**
```json
{
  "success": true,
  "current_version": {
    "version": 1,
    "created_at": "2025-01-03T10:00:00",
    "description": "Prompt inicial por defecto",
    "improvements": [],
    "source": null
  },
  "history": [
    {
      "version": 1,
      "created_at": "2025-01-03T10:00:00",
      "description": "Prompt inicial por defecto",
      "improvements": [],
      "source": null
    }
  ]
}
```

---

### 6. **POST /api/v1/learning/prompts/apply**
Aplica una nueva versión del prompt.

**Form Data:**
- `new_prompt` (requerido): Nuevo prompt a aplicar
- `description` (requerido): Descripción de los cambios
- `improvements` (opcional): Lista de mejoras separadas por comas

**Ejemplo:**
```bash
POST http://localhost:8000/api/v1/learning/prompts/apply
Content-Type: application/x-www-form-urlencoded

new_prompt=⚠️ CRITICAL MISSION: Extract 100%...
description=Mejora para detectar números de factura chinos
improvements=Mejor detección de campos chinos,Mejor parsing de fechas
```

**Respuesta:**
```json
{
  "success": true,
  "new_version": 2,
  "message": "Prompt versión 2 aplicado exitosamente"
}
```

---

## 🔧 Configuración Requerida

### Activar Sistema de Aprendizaje

Edita `config/config.json`:

```json
{
  "learning": {
    "enabled": true,    // ← Cambiar a true
    "folder": "learning",
    "auto_analyze": true
  }
}
```

### Reiniciar API

Después de activar, reinicia el servidor API:

```bash
# Detener servidor (Ctrl+C)
# Iniciar de nuevo
python api_server.py
```

---

## 📊 Flujo de Uso Recomendado

### 1. Procesar Documentos
```bash
POST /api/v1/process-pdf
```
Los errores se registran automáticamente.

### 2. Ver Errores Registrados
```bash
GET /api/v1/learning/errors/summary
```

### 3. Analizar Errores
```bash
POST /api/v1/learning/analyze?limit=20
```

### 4. Ver Sugerencias
```bash
GET /api/v1/learning/suggestions
```

### 5. Aplicar Mejoras (Opcional)
```bash
POST /api/v1/learning/prompts/apply
```

---

## 🎯 Ejemplo Completo con cURL

### 1. Ver resumen de errores:
```bash
curl http://localhost:8000/api/v1/learning/errors/summary
```

### 2. Analizar errores:
```bash
curl -X POST "http://localhost:8000/api/v1/learning/analyze?limit=20"
```

### 3. Ver sugerencias:
```bash
curl http://localhost:8000/api/v1/learning/suggestions
```

### 4. Aplicar nuevo prompt:
```bash
curl -X POST "http://localhost:8000/api/v1/learning/prompts/apply" \
  -F "new_prompt=⚠️ CRITICAL MISSION: Extract 100%..." \
  -F "description=Mejora para detectar números chinos" \
  -F "improvements=Mejor detección de campos chinos"
```

---

## 🐛 Solución de Problemas

### Error: "Sistema de aprendizaje no está activado"

**Solución:** Activa el sistema en `config/config.json`:
```json
{
  "learning": {
    "enabled": true
  }
}
```

### Error: "No hay errores para analizar"

**Solución:** Procesa algunos documentos primero para que se registren errores.

### El análisis tarda mucho

**Solución:** Reduce el `limit` en el endpoint de análisis (ej: `limit=10`).

---

## 📝 Notas

- Los errores se registran **automáticamente** cuando procesas documentos
- El análisis con Gemini puede tomar **varios segundos** (depende del número de errores)
- Las sugerencias se guardan en `learning/suggestions/`
- Los prompts se guardan en `learning/prompts/`
- El sistema funciona **solo si está activado** (`"enabled": true`)

---

## 🔗 Documentación Interactiva

Accede a la documentación interactiva en:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Todos los endpoints están disponibles en la sección **"Learning"**.


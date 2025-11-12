# Sistema de Aprendizaje - ExtractorOCR

## 📋 Descripción

Sistema opcional de aprendizaje que registra errores, analiza patrones y sugiere mejoras para aumentar la precisión del OCR.

## 🎯 Características

- ✅ **Registro automático de errores** - Detecta campos faltantes y valores incorrectos
- ✅ **Análisis de patrones** - Identifica problemas comunes automáticamente
- ✅ **Sugerencias de mejora** - Propone mejoras específicas al prompt y lógica de extracción
- ✅ **Gestión de versiones de prompts** - Mantiene historial de cambios en prompts
- ✅ **Análisis con Gemini** - Usa IA para analizar errores y proponer soluciones

## 🚀 Activación

### Paso 1: Activar en configuración

Edita `config/config.json`:

```json
{
  "learning": {
    "enabled": true,    // ← Cambiar a true
    "folder": "learning",
    "auto_analyze": false
  }
}
```

### Paso 2: Reiniciar el sistema

El sistema de aprendizaje se inicializará automáticamente al procesar documentos.

## 📊 Uso

### 1. Procesar documentos normalmente

El sistema registrará errores automáticamente:

```bash
python main.py --batch
```

### 2. Ver errores registrados

Los errores se guardan en `learning/errors/`:

```bash
# Ver últimos errores
ls learning/errors/
```

### 3. Analizar errores

Usa el servicio de aprendizaje para analizar errores:

```python
from src.learning.error_tracker import ErrorTracker
from src.learning.learning_service import LearningService
from src.services.gemini_service import GeminiService

# Cargar errores
tracker = ErrorTracker("learning")
errors = tracker.get_recent_errors(limit=50)

# Analizar con Gemini
gemini_service = GeminiService("config/gemini_config.json")
learning_service = LearningService(gemini_service, "learning")
analysis = learning_service.analyze_with_gemini(errors)

print(analysis)
```

### 4. Ver sugerencias

Las sugerencias se guardan en `learning/suggestions/`:

```bash
ls learning/suggestions/
```

### 5. Aplicar mejoras

#### Mejorar el prompt:

```python
from src.learning.prompt_manager import PromptManager

manager = PromptManager("learning")
current_prompt = manager.get_current_prompt()

# Aplicar nueva versión
new_version = manager.save_new_version(
    new_prompt="...",  # Nuevo prompt mejorado
    description="Mejora basada en análisis de errores",
    improvements=["Mejor detección de números de factura chinos"],
    source="learning"
)
```

#### Revertir a versión anterior:

```python
manager.revert_to_version(version_num=1)
```

## 📁 Estructura de Datos

```
learning/
├── errors/           # Errores registrados (JSON)
├── prompts/          # Versiones de prompts (JSON)
├── suggestions/      # Sugerencias de mejora (JSON)
└── knowledge/        # Base de conocimiento (futuro)
```

## 🔍 Tipos de Errores Detectados

### 1. Campo Faltante (missing_field)
- Campos que deberían existir pero están vacíos
- Ejemplo: `tNumero`, `mdivisa`, `mcomprobante_detalle`

### 2. Valor Incorrecto (incorrect_value)
- Valores que parecen incorrectos
- Ejemplo: `nPrecioTotal` muy bajo (< 0.01)

### 3. Error de Parsing (parse_error)
- Errores al procesar el documento
- Ejemplo: Excepciones durante el procesamiento

## 📈 Ejemplo de Análisis

Después de procesar varios documentos, el sistema puede detectar:

```json
{
  "total_errors": 15,
  "error_types": {
    "missing_field": 10,
    "incorrect_value": 5
  },
  "field_errors": {
    "tNumero": 8,
    "mdivisa": 4,
    "mcomprobante_detalle": 3
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
      "recommendation": "Revisar regex para números de factura chinos",
      "priority": "high"
    }
  ]
}
```

## ⚙️ Configuración Avanzada

### Auto-análisis

Activa el análisis automático después de cierto número de errores:

```json
{
  "learning": {
    "enabled": true,
    "folder": "learning",
    "auto_analyze": true,
    "auto_analyze_threshold": 10  // Analizar después de 10 errores
  }
}
```

### Limpieza de errores antiguos

Los errores se mantienen por 30 días por defecto. Para cambiarlo:

```python
tracker = ErrorTracker("learning")
tracker.clear_old_errors(days=60)  # Mantener 60 días
```

## 🛡️ Seguridad

- Los errores pueden contener texto OCR completo
- Revisa los datos antes de compartirlos
- Los archivos se guardan localmente (no se envían a servidores externos)

## 🔄 Desactivación

Para desactivar el sistema de aprendizaje:

```json
{
  "learning": {
    "enabled": false  // ← Cambiar a false
  }
}
```

El sistema funcionará normalmente sin registro de errores.

## 📝 Notas

- El sistema es **completamente opcional** - no afecta el funcionamiento si está desactivado
- Los errores se registran **automáticamente** cuando está activado
- El análisis con Gemini requiere **API key de Gemini** (la misma que ya usas)
- Los datos se guardan **localmente** en la carpeta `learning/`

## 🆘 Solución de Problemas

### El sistema no se activa

1. Verifica que `"enabled": true` en `config/config.json`
2. Verifica que los módulos de learning estén en `src/learning/`
3. Revisa los logs para mensajes de error

### No se registran errores

1. Verifica que haya errores reales (campos faltantes, etc.)
2. Revisa que la carpeta `learning/` tenga permisos de escritura
3. Revisa los logs para mensajes de error

### Error al analizar con Gemini

1. Verifica que la API key de Gemini sea válida
2. Verifica que tengas créditos disponibles en Gemini
3. Revisa los logs para mensajes de error específicos

## 📚 Referencias

- [Error Tracker](src/learning/error_tracker.py) - Registro de errores
- [Prompt Manager](src/learning/prompt_manager.py) - Gestión de prompts
- [Learning Service](src/learning/learning_service.py) - Análisis con Gemini


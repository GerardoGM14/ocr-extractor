# Impacto en Despliegue - Sistema de Aprendizaje

## ✅ REUTILIZACIÓN COMPLETA DEL CÓDIGO ACTUAL

### Archivos que NO se modifican (100% reutilizados):
- ✅ `src/core/ocr_extractor.py` - Sin cambios
- ✅ `src/core/batch_processor.py` - Sin cambios  
- ✅ `src/core/file_manager.py` - Sin cambios
- ✅ `src/core/json_parser.py` - Sin cambios
- ✅ `src/core/pdf_processor.py` - Sin cambios
- ✅ `src/services/data_mapper.py` - Sin cambios
- ✅ `src/api/main.py` - Sin cambios
- ✅ `src/gui/main_window.py` - Sin cambios
- ✅ `requirements.txt` - Sin cambios (no nuevas dependencias)
- ✅ `ExtractorOCR_Batch.spec` - Sin cambios (PyInstaller igual)

### Archivos con cambios MÍNIMOS:
- ⚠️ `src/services/gemini_service.py` - Solo 10 líneas modificadas (cargar prompt opcional)
- ⚠️ `config/config.json` - Solo agregar 3 líneas (opcional)

## 📦 IMPACTO EN TAMAÑO

### Código Python:
- **Sin aprendizaje**: ~50 KB
- **Con aprendizaje (desactivado)**: ~50 KB (+0 KB, código no se carga)
- **Con aprendizaje (activado)**: ~150 KB (+100 KB)

### Ejecutable .exe (PyInstaller):
- **Sin aprendizaje**: ~30 MB
- **Con aprendizaje**: ~30.1 MB (+100 KB, ~0.3% aumento)

### Dependencias:
- **Nuevas dependencias**: 0 (solo usa JSON nativo de Python)
- **Librerías externas**: 0 (reutiliza Gemini que ya tienes)

## ⚡ IMPACTO EN RENDIMIENTO

### Con aprendizaje DESACTIVADO:
- **Overhead**: 0% (código no se ejecuta)
- **Memoria**: +0 MB (módulos no se cargan)
- **CPU**: +0% (no hay procesamiento)

### Con aprendizaje ACTIVADO:
- **Overhead normal**: 0% (solo registra si hay error)
- **Overhead con análisis**: <1% (solo cuando analizas errores manualmente)
- **Memoria**: +5-10 MB (solo cuando está activo)

## 🚀 DESPLIEGUE

### Opción 1: Desplegar sin aprendizaje (recomendado inicialmente)
```bash
# 1. Copiar proyecto completo (igual que ahora)
# 2. No cambiar nada en config.json
# 3. Funciona exactamente igual que antes
```

### Opción 2: Desplegar con aprendizaje desactivado
```json
// config/config.json
{
  "learning": {
    "enabled": false  // ← Listo, no afecta nada
  }
}
```

### Opción 3: Activar aprendizaje después
```json
// config/config.json
{
  "learning": {
    "enabled": true  // ← Solo cambiar esta línea
  }
}
```

## 📋 CHECKLIST DE DESPLIEGUE

### Servidor (API FastAPI):
- [ ] Copiar código actual (sin cambios)
- [ ] Copiar nuevos módulos `src/learning/` (opcional, no afecta si no se usan)
- [ ] Actualizar `config/config.json` con `"learning": {"enabled": false}`
- [ ] Reiniciar servicio (igual que siempre)
- ✅ **Listo** - Funciona igual que antes

### Ejecutable .exe:
- [ ] Recompilar con PyInstaller (automático, incluye nuevos módulos)
- [ ] Copiar .exe al servidor
- [ ] Copiar `config/config.json` (con learning desactivado)
- ✅ **Listo** - Funciona igual que antes

## 🔄 ACTUALIZACIONES FUTURAS

### Sin aprendizaje activado:
- ✅ Actualizar código normalmente
- ✅ No afecta el funcionamiento
- ✅ Compatibilidad 100% hacia atrás

### Con aprendizaje activado:
- ✅ Actualizar código normalmente
- ✅ Los datos de aprendizaje se mantienen (carpeta `learning/`)
- ✅ Compatibilidad 100% hacia atrás

## 💾 ALMACENAMIENTO

### Sin aprendizaje:
- **Datos adicionales**: 0 MB

### Con aprendizaje activado:
- **Errores registrados**: ~1-5 KB por error (JSON)
- **Prompts versionados**: ~5-10 KB por versión
- **Total estimado**: ~1-10 MB después de 1000 documentos procesados

## 🎯 RECOMENDACIÓN FINAL

**Implementar en 3 fases opcionales:**

1. **Fase 1**: Agregar módulos (sin activar) → Sin impacto
2. **Fase 2**: Activar registro de errores → Impacto mínimo (<1%)
3. **Fase 3**: Activar análisis con Gemini → Solo cuando lo necesites

**Ventaja**: Puedes probar fase por fase sin riesgo.


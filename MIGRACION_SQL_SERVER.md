# Guía de Migración a SQL Server

## 📋 Estado Actual

Actualmente, el sistema lee las estadísticas del Dashboard desde **archivos JSON estructurados** de forma manual. Esto es una solución temporal mientras no hay conexión a la base de datos.

## 🎯 Objetivo

Cuando tengas conexión a SQL Server, las estadísticas deben leerse directamente de las tablas:
- `MCOMPROBANTE` - Para montos totales (`nPrecioTotal`)
- `MJORNADA` - Para total de horas (`nTotalHoras`)
- Otras tablas relacionadas según los filtros

---

## 📍 Ubicaciones a Modificar

### 1. Endpoint: `/api/v1/dashboard/stats`

**Archivo:** `src/api/main.py` (líneas ~1642-1705)

**Código actual:**
```python
# Lee de JSONs estructurados (temporal)
structured_folder = Path(base_output) / "api" / "structured"
for json_file in structured_folder.glob("*_structured.json"):
    # ... lee y suma montos/horas ...
```

**Código a implementar (SQL):**
```python
# Conexión a SQL Server
import pyodbc  # o pymssql

# Configuración de conexión (agregar a config/config.json)
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={username};"
    f"PWD={password}"
)

# Query para estadísticas
query = """
SELECT 
    SUM(c.nPrecioTotal) as monto_total,
    SUM(j.nTotalHoras) as total_horas
FROM MCOMPROBANTE c
LEFT JOIN MJORNADA j ON j.iMHoja = c.iMHoja
LEFT JOIN MHOJA h ON h.iMHoja = c.iMHoja
WHERE 1=1
"""

# Aplicar filtros
if fecha_inicio:
    query += " AND c.fEmision >= ?"
if fecha_fin:
    query += " AND c.fEmision <= ?"
if moneda:
    query += " AND c.iMDivisa = (SELECT iMDivisa FROM MDIVISA WHERE tCodigo = ?)"
if tipo_documento:
    query += " AND h.iMTipoDocumento = ?"
if departamento:
    query += " AND h.tDepartamento = ?"
if disciplina:
    query += " AND h.tDisciplina = ?"

# Ejecutar query
with pyodbc.connect(connection_string) as conn:
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    monto_total = row.monto_total or 0.0
    total_horas = row.total_horas or 0.0
```

---

### 2. Endpoint: `/api/v1/dashboard/analytics`

**Archivo:** `src/api/main.py` (líneas ~1715-1750)

**Estado actual:** Retorna `null` (pendiente de implementar)

**Código a implementar (SQL):**
```python
# Análisis Off-Shore / On-Shore
query_offshore = """
SELECT 
    SUM(c.nPrecioTotal) as total_gasto,
    SUM(j.nTotalHoras) as total_horas,
    COUNT(DISTINCT h.tDisciplina) as total_disciplinas,
    h.tDepartamento,
    SUM(c.nPrecioTotal) as gasto_por_dept
FROM MCOMPROBANTE c
LEFT JOIN MJORNADA j ON j.iMHoja = c.iMHoja
LEFT JOIN MHOJA h ON h.iMHoja = c.iMHoja
WHERE h.tTipo = 'offshore'  -- o el campo que identifique offshore
GROUP BY h.tDepartamento
"""

query_onshore = """
SELECT 
    SUM(c.nPrecioTotal) as total_gasto,
    SUM(j.nTotalHoras) as total_horas,
    COUNT(DISTINCT h.tDisciplina) as total_disciplinas,
    h.tDepartamento,
    SUM(c.nPrecioTotal) as gasto_por_dept
FROM MCOMPROBANTE c
LEFT JOIN MJORNADA j ON j.iMHoja = c.iMHoja
LEFT JOIN MHOJA h ON h.iMHoja = c.iMHoja
WHERE h.tTipo = 'onshore'  -- o el campo que identifique onshore
GROUP BY h.tDepartamento
"""
```

---

### 3. Endpoint: `/api/v1/dashboard/rejected-concepts`

**Archivo:** `src/api/main.py` (líneas ~1755-1790)

**Estado actual:** Retorna lista vacía (pendiente de implementar)

**Código a implementar (SQL):**
```python
# Conceptos rechazados
query = """
SELECT 
    c.tConcepto as concepto,
    COUNT(*) as cantidad_total,
    SUM(c.nPrecioTotal) as monto_total
FROM MCOMPROBANTE c
LEFT JOIN MHOJA h ON h.iMHoja = c.iMHoja
WHERE h.tEstado = 'rechazado'  -- o el campo que identifique rechazados
GROUP BY c.tConcepto
ORDER BY monto_total DESC
"""
```

---

### 4. Endpoint: `/api/v1/periodos/{periodo_id}/resumen-ps`

**Archivo:** `src/api/main.py` (líneas ~1950-2000)

**Estado actual:** Retorna lista vacía (pendiente de implementar)

**Código a implementar (SQL):**
```python
# Resumen PS por departamento y disciplina
query = """
SELECT 
    h.tDepartamento as department,
    h.tDisciplina as discipline,
    SUM(c.nPrecioTotal) as total_us,
    SUM(j.nTotalHoras) as total_horas,
    CASE 
        WHEN SUM(j.nTotalHoras) > 0 
        THEN SUM(c.nPrecioTotal) / SUM(j.nTotalHoras)
        ELSE 0 
    END as ratios_edp
FROM MCOMPROBANTE c
LEFT JOIN MJORNADA j ON j.iMHoja = c.iMHoja
LEFT JOIN MHOJA h ON h.iMHoja = c.iMHoja
LEFT JOIN MARCHIVO a ON a.iMArchivo = h.iMArchivo
WHERE a.periodo_id = ?  -- asociar con periodo
GROUP BY h.tDepartamento, h.tDisciplina
ORDER BY total_us DESC
"""
```

---

## 🔧 Configuración Necesaria

### 1. Agregar dependencias

**Archivo:** `requirements.txt`

```txt
# SQL Server
pyodbc>=5.0.0
# o alternativamente:
# pymssql>=2.2.0
```

### 2. Agregar configuración de BD

**Archivo:** `config/config.json`

```json
{
  "database": {
    "enabled": false,
    "driver": "ODBC Driver 17 for SQL Server",
    "server": "tu-servidor.database.windows.net",
    "database": "BD_NEWMONT_OCR_PDF",
    "username": "tu_usuario",
    "password": "tu_password",
    "trusted_connection": false,
    "encrypt": true
  }
}
```

### 3. Crear servicio de conexión

**Archivo:** `src/services/database_service.py` (nuevo)

```python
"""
Database Service - Gestión de conexiones a SQL Server
"""
import pyodbc
import json
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    """Servicio para conexiones a SQL Server."""
    
    def __init__(self):
        self.connection_string = self._load_connection_string()
    
    def _load_connection_string(self) -> Optional[str]:
        """Carga la cadena de conexión desde config.json"""
        config_path = Path("config/config.json")
        if not config_path.exists():
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        db_config = config.get("database", {})
        if not db_config.get("enabled", False):
            return None
        
        # Construir connection string
        parts = []
        if db_config.get("driver"):
            parts.append(f"DRIVER={{{db_config['driver']}}}")
        if db_config.get("server"):
            parts.append(f"SERVER={db_config['server']}")
        if db_config.get("database"):
            parts.append(f"DATABASE={db_config['database']}")
        if db_config.get("trusted_connection"):
            parts.append("Trusted_Connection=yes")
        else:
            if db_config.get("username"):
                parts.append(f"UID={db_config['username']}")
            if db_config.get("password"):
                parts.append(f"PWD={db_config['password']}")
        if db_config.get("encrypt"):
            parts.append("Encrypt=yes")
        
        return ";".join(parts)
    
    def get_connection(self):
        """Obtiene una conexión a la base de datos."""
        if not self.connection_string:
            raise ValueError("Base de datos no configurada")
        return pyodbc.connect(self.connection_string)
    
    def execute_query(self, query: str, params: tuple = None) -> list:
        """Ejecuta una query y retorna los resultados."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
```

---

## 📝 Pasos para Migrar

1. **Instalar dependencias:**
   ```bash
   pip install pyodbc
   ```

2. **Configurar conexión:**
   - Editar `config/config.json` con datos de tu SQL Server
   - Crear `src/services/database_service.py`

3. **Modificar endpoints:**
   - Reemplazar lectura de JSONs por queries SQL
   - Usar `DatabaseService` para ejecutar queries

4. **Probar:**
   - Verificar que las estadísticas se calculen correctamente
   - Comparar resultados con los JSONs (para validar)

5. **Mantener compatibilidad (opcional):**
   - Si quieres mantener ambos métodos, puedes hacer:
   ```python
   if database_enabled:
       # Leer de SQL
   else:
       # Leer de JSONs (fallback)
   ```

---

## ⚠️ Notas Importantes

1. **Seguridad:**
   - No hardcodear credenciales en el código
   - Usar variables de entorno o archivos de configuración seguros
   - Considerar usar Azure Key Vault o similar

2. **Performance:**
   - Agregar índices en las tablas si es necesario
   - Considerar cachear resultados si las queries son pesadas

3. **Manejo de errores:**
   - Implementar retry logic para conexiones
   - Logging de errores de BD

4. **Testing:**
   - Probar con datos de prueba primero
   - Validar que los resultados coincidan con los JSONs

---

## 🔄 Mapeo de Campos

| JSON (actual) | SQL Server (futuro) |
|---------------|---------------------|
| `additional_data.mcomprobante[].nPrecioTotal` | `MCOMPROBANTE.nPrecioTotal` |
| `additional_data.mjornada[].nTotalHoras` | `MJORNADA.nTotalHoras` |
| `metadata.processed_at` | `MARCHIVO.fRegistro` |
| `metadata.periodo_id` | `MARCHIVO.periodo_id` (si lo agregas) |
| `metadata.email` | `MARCHIVO.tEmail` (si lo agregas) |

---

## ✅ Checklist de Migración

- [ ] Instalar `pyodbc` o `pymssql`
- [ ] Crear `DatabaseService`
- [ ] Agregar configuración de BD en `config.json`
- [ ] Modificar `/api/v1/dashboard/stats`
- [ ] Modificar `/api/v1/dashboard/analytics`
- [ ] Modificar `/api/v1/dashboard/rejected-concepts`
- [ ] Modificar `/api/v1/periodos/{periodo_id}/resumen-ps`
- [ ] Probar todos los endpoints
- [ ] Validar resultados con datos de prueba
- [ ] Documentar cambios

---

¿Necesitas ayuda con algún paso específico? Avísame cuando tengas la conexión a BD y te ayudo a implementarlo. 🚀


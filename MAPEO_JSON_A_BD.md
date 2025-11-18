# Mapeo de JSON Structured a Base de Datos SQL Server

## 📋 Resumen

Con el **JSON structured** es suficiente porque ya tiene toda la estructura de datos. Solo necesito mapear los campos del JSON a las columnas de la BD y manejar las relaciones.

---

## 🔗 Relaciones entre Tablas (Foreign Keys)

```
MARCHIVO (1) ──→ (N) MHOJA
MHOJA (1) ──→ (N) MCOMPROBANTE
MHOJA (1) ──→ (N) MJORNADA
MHOJA (1) ──→ (N) MRESUMEN
MCOMPROBANTE (1) ──→ (N) MCOMPROBANTE_DETALLE
MJORNADA (1) ──→ (N) MJORNADA_EMPLEADO
MCOMPROBANTE ──→ MPROVEEDOR (iMProveedor)
MCOMPROBANTE ──→ MDIVISA (iMDivisa)
MCOMPROBANTE ──→ MNATURALEZA (iMNaturaleza)
MHOJA ──→ MIDIOMA (iMIdioma)
MHOJA ──→ MDOCUMENTO_TIPO (iMDocumentoTipo)
MCOMPROBANTE_DETALLE ──→ MUNIDAD_MEDIDA (iMUnidad)
```

---

## 📊 Mapeo de Campos

### 1. MARCHIVO (Tabla Principal - Archivo PDF)

**Origen:** Metadata del JSON + información del request

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMArchivo` | AUTO (IDENTITY) | Se genera automáticamente |
| `tNombre` | `metadata.pdf_name` | Nombre del PDF original |
| `tRuta` | `metadata.request_id` | Ruta o referencia al archivo |
| `iMArchivoTipo` | `1` (por defecto) | Tipo de archivo (PDF = 1) |
| `fRegistro` | `metadata.processed_at` | Fecha de procesamiento |

**Lógica:**
- Si el archivo ya existe (mismo `tNombre` + `tRuta`), usar ese `iMArchivo`
- Si no existe, crear nuevo registro
- Retornar `iMArchivo` para usar en MHOJA

---

### 2. MHOJA (Hoja/Página del PDF)

**Origen:** `json_structured.hoja` + metadata

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMHoja` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMArchivo` | ← `iMArchivo` de MARCHIVO | Foreign key |
| `iNroHoja` | `metadata.page_number` | Número de página |
| `tSequentialNumber` | `hoja.tSequentialNumber` | Número secuencial |
| `lFormato` | `hoja.lFormato` | Formato (bit) |
| `iMIdioma` | `hoja.iMIdioma` | **Ver catálogo MIDIOMA** |
| `iMDocumentoTipo` | `hoja.iMDocumentoTipo` | **Ver catálogo MDOCUMENTO_TIPO** |
| `tJson` | `hoja.tJson` | JSON crudo (texto) |
| `tJsonTraducido` | `hoja.tJsonTraducido` | JSON traducido (texto) |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |

**Lógica:**
- Crear un registro por cada página/JSON
- Retornar `iMHoja` para usar en tablas relacionadas

---

### 3. MCOMPROBANTE (Comprobantes/Facturas)

**Origen:** `json_structured.additional_data.mcomprobante[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMComprobante` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMHoja` | ← `iMHoja` de MHOJA | Foreign key |
| `iMNaturaleza` | `iMNaturaleza` | **Ver catálogo MNATURALEZA** |
| `tSerie` | `tSerie` | Serie del comprobante |
| `tNumero` | `tNumero` | Número del comprobante |
| `iMDivisa` | `iMDivisa` | **Ver catálogo MDIVISA** |
| `fEmision` | `fEmision` | Fecha de emisión |
| `iMProveedor` | ← `iMProveedor` de MPROVEEDOR | Foreign key (buscar o crear) |
| `tCliente` | `tCliente` | Nombre del cliente |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |
| `nPrecioTotal` | `nPrecioTotal` | Precio total |
| `nPrecioTotalConvertido` | `nPrecioTotalConvertido` | Precio convertido (si aplica) |

**Lógica:**
- Por cada item en `mcomprobante[]`, crear un registro
- Buscar o crear MPROVEEDOR primero
- Retornar `iMComprobante` para MCOMPROBANTE_DETALLE

---

### 4. MCOMPROBANTE_DETALLE (Detalle de Comprobante)

**Origen:** `json_structured.additional_data.mcomprobante_detalle[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMComprobanteDetalle` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMComprobante` | ← `iMComprobante` de MCOMPROBANTE | Foreign key |
| `nCantidad` | `nCantidad` | Cantidad |
| `iMUnidad` | `iMUnidad` | **Ver catálogo MUNIDAD_MEDIDA** |
| `tDescripcion` | `tDescripcion` | Descripción del item |
| `nPrecioUnitario` | `nPrecioUnitario` | Precio unitario |
| `nPrecioTotal` | `nPrecioTotal` | Precio total del item |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |

**Lógica:**
- Por cada item en `mcomprobante_detalle[]`, crear un registro
- Asociar al `iMComprobante` correspondiente

---

### 5. MJORNADA (Jornadas/Horas de Trabajo)

**Origen:** `json_structured.additional_data.mjornada[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMJornada` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMHoja` | ← `iMHoja` de MHOJA | Foreign key |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |
| `nTotalHoras` | `nTotalHoras` | Total de horas |

**Lógica:**
- Por cada item en `mjornada[]`, crear un registro
- Retornar `iMJornada` para MJORNADA_EMPLEADO

---

### 6. MJORNADA_EMPLEADO (Empleados de Jornada)

**Origen:** `json_structured.additional_data.mjornada_empleado[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMEmpleado` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMJornada` | ← `iMJornada` de MJORNADA | Foreign key |
| `tNumero` | `tNumero` | Número de empleado |
| `tNombre` | `tNombre` | Nombre del empleado |
| `tOrganizacion` | `tOrganizacion` | Organización |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |

**Lógica:**
- Por cada item en `mjornada_empleado[]`, crear un registro
- Asociar al `iMJornada` correspondiente

---

### 7. MPROVEEDOR (Proveedores)

**Origen:** `json_structured.additional_data.mproveedor[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMProveedor` | AUTO (IDENTITY) | Se genera automáticamente |
| `tNumeroFiscal` | `tNumeroFiscal` o `tRUC` | RUC/Número fiscal |
| `tRazonSocial` | `tRazonSocial` | Razón social |

**Lógica:**
- **IMPORTANTE:** Buscar primero por `tNumeroFiscal` (RUC)
- Si existe, usar ese `iMProveedor`
- Si no existe, crear nuevo registro
- Retornar `iMProveedor` para usar en MCOMPROBANTE

---

### 8. MRESUMEN (Resumen/Summary)

**Origen:** `json_structured.additional_data.mresumen[]`

| Campo BD | Origen JSON | Notas |
|----------|-------------|-------|
| `iMResumen` | AUTO (IDENTITY) | Se genera automáticamente |
| `iMHoja` | ← `iMHoja` de MHOJA | Foreign key |
| `tjobno` | `tjobno` o `job_no` | Job number |
| `ttype` | `ttype` o `type` | Tipo |
| `tsourcereference` | `tsourcereference` o `source_reference` | Source reference |
| `tsourcerefid` | `tsourcerefid` o `source_ref_id` | Source ref ID |
| `tdescription` | `tdescription` o `description` | Descripción |
| `nImporte` | `nImporte` o `entered_amount` | Importe |
| `tStampname` | `tStampname` o `stamp_name` | Stamp name |
| `tsequentialnumber` | `tsequentialnumber` o `sequential_number` | Sequential number |
| `fRegistro` | `metadata.processed_at` | Fecha de registro |

**Lógica:**
- Por cada item en `mresumen[]`, crear un registro
- Asociar al `iMHoja` correspondiente

---

## 🗂️ Catálogos (Tablas de Referencia)

Estas tablas necesitan **lookup o insert**:

### MDIVISA (Divisas/Monedas)
- Buscar por `tDivisa` (ej: "USD", "PEN", "EUR")
- Si no existe, crear nuevo registro
- Retornar `iMDivisa` para usar en MCOMPROBANTE

### MIDIOMA (Idiomas)
- Buscar por `tIdioma` (ej: "Spanish", "English")
- Si no existe, crear nuevo registro
- Retornar `iMIdioma` para usar en MHOJA

### MDOCUMENTO_TIPO (Tipos de Documento)
- Buscar por `tTipo` (ej: "Invoice", "Boleta", "Resumen")
- Si no existe, crear nuevo registro
- Retornar `iMDocumentoTipo` para usar en MHOJA

### MNATURALEZA (Naturaleza del Comprobante)
- Buscar por `tNaturaleza` (ej: "Ingreso", "Egreso")
- Si no existe, crear nuevo registro
- Retornar `iMNaturaleza` para usar en MCOMPROBANTE

### MUNIDAD_MEDIDA (Unidades de Medida)
- Buscar por `tUnidad` (ej: "Unit", "Hour", "Day")
- Si no existe, crear nuevo registro
- Retornar `iMUnidad` para usar en MCOMPROBANTE_DETALLE

---

## 🔄 Orden de Inserción

1. **MARCHIVO** (si no existe)
2. **MHOJA** (usando `iMArchivo`)
3. **MPROVEEDOR** (buscar o crear, para usar en MCOMPROBANTE)
4. **Catálogos** (MDIVISA, MIDIOMA, etc. - buscar o crear)
5. **MCOMPROBANTE** (usando `iMHoja` y `iMProveedor`)
6. **MCOMPROBANTE_DETALLE** (usando `iMComprobante`)
7. **MJORNADA** (usando `iMHoja`)
8. **MJORNADA_EMPLEADO** (usando `iMJornada`)
9. **MRESUMEN** (usando `iMHoja`)

---

## ✅ Conclusión

**Con el JSON structured es suficiente** porque:
- ✅ Ya tiene toda la estructura de datos
- ✅ Los nombres de campos son similares a las columnas de BD
- ✅ Solo necesito mapear campos y manejar relaciones

**Lo que necesito implementar:**
1. Mapeo de campos (directo, ya está claro)
2. Manejo de foreign keys (relaciones entre tablas)
3. Lookup/Insert de catálogos (MDIVISA, MIDIOMA, etc.)
4. Manejo de duplicados (MPROVEEDOR por RUC)

¿Te parece bien este mapeo? ¿Hay algún campo que deba ajustar o alguna lógica especial que deba considerar?


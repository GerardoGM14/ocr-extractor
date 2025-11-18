# Guía de Prueba del Endpoint de Excel

## Opción 1: Usar Swagger UI (Más Fácil)

1. **Inicia el servidor:**
   ```bash
   python api_server.py
   # O
   run_api.bat
   ```

2. **Abre el navegador:**
   ```
   http://localhost:8000/docs
   ```

3. **Busca el endpoint:**
   - Encuentra: `GET /api/v1/export-excel/{request_id}`
   - Haz clic en "Try it out"

4. **Obtén un request_id:**
   - Ve a `GET /api/v1/processed-files`
   - Ejecuta y copia un `request_id` de la respuesta

5. **Prueba el endpoint:**
   - Pega el `request_id` en el campo
   - Haz clic en "Execute"
   - Debería redirigir a `/public/{excel_filename}` y descargar el Excel

---

## Opción 2: Usar el Script de Prueba

```bash
# Instalar requests si no lo tienes
pip install requests

# Ejecutar el script
python test_excel_endpoint.py
```

---

## Opción 3: Usar cURL (Línea de Comandos)

### Paso 1: Obtener un request_id
```bash
curl -X GET "http://localhost:8000/api/v1/processed-files?limit=5"
```

### Paso 2: Probar el endpoint de Excel
```bash
# Reemplaza {request_id} con un request_id real
curl -L -o excel_descargado.xlsx "http://localhost:8000/api/v1/export-excel/{request_id}"
```

El flag `-L` sigue las redirecciones automáticamente.

---

## Opción 4: Probar el Flujo Completo

### 1. Subir un PDF
```bash
curl -X POST "http://localhost:8000/api/v1/upload-pdf" \
  -F "pdf_file=@ruta/al/archivo.pdf" \
  -F "email=tu_email@autorizado.com" \
  -F "year=2025" \
  -F "month=Noviembre"
```

**Respuesta esperada:**
```json
{
  "success": true,
  "file_id": "abc123-def456-...",
  "filename": "archivo.pdf",
  ...
}
```

### 2. Procesar el PDF
```bash
curl -X POST "http://localhost:8000/api/v1/process-pdf" \
  -F "file_id={file_id_del_paso_anterior}" \
  -F "save_files=true"
```

**Respuesta esperada:**
```json
{
  "success": true,
  "request_id": "f86a7baf-38b7-4426-8312-84735de3488b",
  "download_url": "/public/archivo_20251114_120153_f86a7baf.zip",
  "excel_download_url": "/public/archivo_consolidado_20251114_120153_f86a7baf.xlsx",
  ...
}
```

### 3. Descargar el Excel (3 formas)

**Forma A: Usar excel_download_url de la respuesta**
```bash
curl -L -o excel.xlsx "http://localhost:8000/public/archivo_consolidado_20251114_120153_f86a7baf.xlsx"
```

**Forma B: Usar el endpoint export-excel**
```bash
curl -L -o excel.xlsx "http://localhost:8000/api/v1/export-excel/f86a7baf-38b7-4426-8312-84735de3488b"
```

**Forma C: Usar processed-files para obtener la URL**
```bash
curl -X GET "http://localhost:8000/api/v1/processed-files?limit=1" | jq '.files[0].excel_download_url'
```

---

## Verificación

### Verificar que el Excel se generó:
1. Revisa la carpeta `public/` - debería haber un archivo `.xlsx`
2. Revisa los logs del servidor - debería decir "Excel creado en public/"
3. Revisa la respuesta de `process-pdf` - debería incluir `excel_download_url`

### Verificar que el Excel tiene datos:
1. Abre el Excel descargado
2. Debería tener al menos una fila de encabezados
3. Si hay datos, deberían aparecer en las filas siguientes

---

## Solución de Problemas

### Error 404: "No se encontró información para request_id"
- El `request_id` no existe o es incorrecto
- Verifica con `GET /api/v1/processed-files`

### Error 403: "Correo no autorizado"
- El email del archivo no está en `config/allowed_emails.json`
- Agrega el email a la lista de permitidos

### Excel vacío (solo encabezados)
- Es normal si el PDF no tenía datos extraíbles
- El Excel siempre se genera, aunque esté vacío

### No se genera el Excel automáticamente
- Revisa los logs del servidor para ver errores
- Verifica que `openpyxl` esté instalado: `pip install openpyxl`


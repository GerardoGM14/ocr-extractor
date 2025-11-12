# ExtractorOCR v1.0

Sistema de extracción de datos de PDFs usando Gemini Vision API para Newmont.

## Descripción

Sistema que procesa PDFs consolidados (facturas, boletas, reportes financieros) y extrae información estructurada usando OCR con Gemini 2.5 Flash.

## Características

- Procesamiento por página (dividido automáticamente)
- Dos tipos de JSON de salida:
  - JSON 1: Información cruda extraída
  - JSON 2: Información estructurada y traducida para BD
- Interfaz gráfica amigable
- Configuración de 3 carpetas:
  - Input: PDFs a procesar (OneDrive compartido)
  - Processing: Resultados intermedios
  - Output: JSONs finales
- Soporte multiidioma y múltiples divisas

## Requisitos

- Python 3.9+
- Gemini API Key
- Windows 10/11

## Instalación

### Primera vez (Deployment)

```bash
# 1. Copiar el proyecto a donde quieras
# Copiar toda la carpeta ExtractorOCRv1 a la nueva ubicación

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno (Windows)
.\venv\Scripts\activate.bat

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Configurar API Key de Gemini
# Crear archivo: config/gemini_config.json
# Contenido:
{
    "api_key": "TU_API_KEY_AQUI",
    "model": "gemini-2.5-flash",
    "timeout": 300,
    "max_retries": 3,
    "temperature": 0.1
}

# 6. Ejecutar con run.bat
run.bat
```

### Uso Normal (Una vez configurado)

```bash
# Solo ejecutar:
run.bat
```

## Configuración

### Rutas de Carpetas

Las rutas en `config/config.json` son relativas y se configuran automáticamente:
- `./onedrive` - PDFs de entrada
- `./processed` - Archivos procesados
- `./output` - JSONs de salida

Puedes cambiarlas desde la interfaz gráfica o editando el archivo manualmente.

### API Key de Gemini

**IMPORTANTE:** El archivo `config/gemini_config.json` NO se sube al repositorio por seguridad.
Debes crearlo manualmente en cada instalación.

## Uso

```bash
python main.py
```

## Estructura del Proyecto

```
ExtractorOCRv1/
├── config/              # Archivos de configuración
├── src/
│   ├── core/           # Procesamiento de PDFs y OCR
│   ├── services/       # Servicios de Gemini y mapeo
│   └── gui/            # Interfaz gráfica
├── temp/               # Archivos temporales
├── output/             # JSONs de salida
└── main.py             # Punto de entrada
```

## Licencia

Uso interno - Newmont Corporation


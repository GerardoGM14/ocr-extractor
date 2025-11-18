# Instrucciones para HTTPS Local

## Paso 1: Instalar dependencia

```bash
pip install cryptography
```

## Paso 2: Generar certificados SSL

```bash
python generate_ssl_local.py
```

Esto creará:
- `ssl_certs/cert.pem` (certificado)
- `ssl_certs/key.pem` (clave privada)

## Paso 3: Habilitar HTTPS en config.json

Edita `config/config.json` y cambia:

```json
"api": {
  "ssl": {
    "enabled": true,  // Cambiar de false a true
    "cert_file": "ssl_certs/cert.pem",
    "key_file": "ssl_certs/key.pem"
  }
}
```

## Paso 4: Reiniciar el servidor

```bash
python api_server.py
```

Deberías ver:
```
Servidor iniciando con HTTPS...
Documentación disponible en: https://localhost:8000/docs
API disponible en: https://localhost:8000/api/v1/
```

## Paso 5: Probar en el navegador

1. Abre: `https://localhost:8000/docs`
2. El navegador mostrará una advertencia de seguridad (esto es normal con certificados autofirmados)
3. Haz clic en "Avanzado" → "Continuar a localhost (no seguro)"
4. Deberías ver la documentación de Swagger

## Paso 6: Actualizar el frontend

En tu frontend de Netlify, cambia la URL base de:
```
http://192.168.0.63:8000
```

A:
```
https://TU_IP_LOCAL:8000
```

O si estás probando desde la misma máquina:
```
https://localhost:8000
```

**Nota:** Para acceder desde otra máquina (como Netlify), necesitarás:
- Abrir el puerto 8000 en el firewall
- Usar tu IP local (ej: `https://192.168.0.63:8000`)
- Aceptar el certificado autofirmado en el navegador

## Solución de problemas

### Error: "certificado no válido"
- Esto es normal con certificados autofirmados
- Acepta la excepción en el navegador

### Error: "No se puede conectar"
- Verifica que el servidor esté corriendo
- Verifica que el puerto 8000 esté abierto en el firewall
- Verifica que `api.ssl.enabled: true` en config.json

### Error: "No se encuentran los certificados"
- Verifica que `ssl_certs/cert.pem` y `ssl_certs/key.pem` existan
- Regenera los certificados con `python generate_ssl_local.py`


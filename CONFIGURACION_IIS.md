# Configuración para IIS con HTTPS

## Opción 1: IIS como Reverse Proxy (RECOMENDADO)

Esta es la mejor opción para IIS. IIS maneja el HTTPS y hace proxy a FastAPI.

### Pasos:

1. **Instalar Application Request Routing (ARR) en IIS:**
   - Descarga desde: https://www.iis.net/downloads/microsoft/application-request-routing
   - Instala el módulo

2. **Configurar el sitio en IIS:**
   - Crea un nuevo sitio web
   - Configura el binding HTTPS con tu certificado SSL
   - Configura la URL Rewrite para hacer proxy a `http://localhost:8000`

3. **Configuración de URL Rewrite (web.config):**
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <configuration>
       <system.webServer>
           <rewrite>
               <rules>
                   <rule name="ReverseProxyInboundRule" stopProcessing="true">
                       <match url="(.*)" />
                       <action type="Rewrite" url="http://localhost:8000/{R:1}" />
                   </rule>
               </rules>
           </rewrite>
       </system.webServer>
   </configuration>
   ```

4. **El servidor FastAPI corre en HTTP** (localhost:8000)
   - IIS maneja el HTTPS externamente
   - No necesitas certificados en FastAPI

---

## Opción 2: FastAPI con HTTPS Directo

Si prefieres que FastAPI maneje HTTPS directamente:

### Pasos:

1. **Obtener certificados SSL:**
   - Puedes usar certificados de Windows Certificate Store
   - O certificados autofirmados para desarrollo
   - O certificados de una CA para producción

2. **Exportar certificado desde IIS:**
   - Abre IIS Manager
   - Selecciona tu sitio → Bindings → HTTPS
   - Exporta el certificado a formato .pfx
   - Convierte .pfx a .pem (certificado) y .key (clave privada)

3. **Configurar config.json:**
   ```json
   {
     "api": {
       "ssl": {
         "enabled": true,
         "cert_file": "ssl_certs/cert.pem",
         "key_file": "ssl_certs/key.pem"
       }
     }
   }
   ```

4. **Colocar certificados:**
   - Crea carpeta `ssl_certs/`
   - Coloca `cert.pem` y `key.pem` ahí

5. **Ejecutar el servidor:**
   - El servidor iniciará automáticamente con HTTPS si los certificados existen

---

## Conversión de Certificado .pfx a .pem

Si tienes un certificado .pfx de IIS:

```bash
# Instalar OpenSSL (si no lo tienes)
# Descarga desde: https://slproweb.com/products/Win32OpenSSL.html

# Convertir .pfx a .pem y .key
openssl pkcs12 -in certificado.pfx -nocerts -out key.pem -nodes
openssl pkcs12 -in certificado.pfx -clcerts -nokeys -out cert.pem
```

---

## Recomendación

**Usa la Opción 1 (IIS como Reverse Proxy)** porque:
- ✅ IIS ya maneja certificados SSL fácilmente
- ✅ No necesitas modificar certificados en FastAPI
- ✅ Más fácil de mantener
- ✅ Separación de responsabilidades (IIS = SSL, FastAPI = lógica)

El servidor FastAPI puede seguir corriendo en HTTP en localhost, y IIS se encarga del HTTPS externo.


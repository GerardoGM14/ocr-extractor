# Solución para Error de CORS HTTPS → HTTP

## Problema
El frontend en `https://newmont-pdf.netlify.app` está intentando acceder a tu servidor en `http://192.168.0.63:8000`, lo cual es bloqueado por los navegadores por seguridad (mixed content).

## Soluciones

### Opción 1: Usar ngrok (RECOMENDADO - Más fácil)

1. **Instalar ngrok:**
   - Descarga desde: https://ngrok.com/download
   - O con chocolatey: `choco install ngrok`

2. **Crear cuenta gratuita en ngrok.com** (opcional, pero recomendado)

3. **Ejecutar ngrok:**
   ```bash
   ngrok http 8000
   ```

4. **Copiar la URL HTTPS que te da ngrok** (ej: `https://abc123.ngrok.io`)

5. **Actualizar el frontend** para usar esa URL en lugar de `http://192.168.0.63:8000`

6. **Actualizar CORS en el servidor** para permitir el origen de Netlify (ya está configurado)

**Ventajas:**
- ✅ Muy fácil de configurar
- ✅ HTTPS automático
- ✅ Funciona inmediatamente
- ✅ No requiere cambios en el código del servidor

**Desventajas:**
- La URL cambia cada vez que reinicias ngrok (a menos que tengas cuenta de pago)

---

### Opción 2: Usar Cloudflare Tunnel (Gratis y permanente)

1. **Instalar cloudflared:**
   - Descarga desde: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

2. **Autenticarse:**
   ```bash
   cloudflared tunnel login
   ```

3. **Crear túnel:**
   ```bash
   cloudflared tunnel create my-tunnel
   ```

4. **Configurar túnel:**
   ```bash
   cloudflared tunnel route dns my-tunnel api-tu-dominio.com
   ```

5. **Ejecutar túnel:**
   ```bash
   cloudflared tunnel run my-tunnel
   ```

**Ventajas:**
- ✅ URL permanente
- ✅ Completamente gratis
- ✅ HTTPS automático

---

### Opción 3: Configurar servidor con HTTPS local

Si prefieres mantener el servidor local con HTTPS, necesitas:

1. **Generar certificados SSL** (puedo ayudarte con esto)
2. **Configurar uvicorn para usar HTTPS**
3. **Aceptar el certificado autofirmado en el navegador**

---

## Configuración Actual de CORS

El servidor ya está configurado para permitir:
- `https://newmont-pdf.netlify.app`
- `http://localhost:3000`
- `http://localhost:5173`
- `http://localhost:8080`

## Recomendación

**Usa ngrok** para desarrollo/testing. Es la solución más rápida y no requiere cambios en el código.

Para producción, considera:
- Desplegar el servidor en un servicio con HTTPS (Railway, Render, Fly.io, etc.)
- O usar Cloudflare Tunnel para mantener el servidor local pero accesible vía HTTPS


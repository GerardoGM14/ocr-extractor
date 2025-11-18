# Solución Rápida: Usar ngrok para HTTPS

## Paso 1: Instalar ngrok

**Opción A - Descarga directa:**
1. Ve a: https://ngrok.com/download
2. Descarga la versión para Windows
3. Extrae el archivo `ngrok.exe` en una carpeta (ej: `C:\ngrok\`)

**Opción B - Con Chocolatey (si lo tienes):**
```powershell
choco install ngrok
```

## Paso 2: Ejecutar ngrok

1. **Abre una nueva terminal/PowerShell**
2. **Ejecuta:**
   ```bash
   ngrok http 8000
   ```

3. **Verás algo como:**
   ```
   Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
   ```

4. **Copia la URL HTTPS** (la que empieza con `https://`)

## Paso 3: Actualizar el frontend

En tu frontend de Netlify, cambia la URL base de la API de:
```
http://192.168.0.63:8000
```

A la URL que te dio ngrok:
```
https://abc123.ngrok-free.app
```

## Paso 4: Verificar CORS

El servidor ya está configurado para permitir `https://newmont-pdf.netlify.app`, así que debería funcionar.

## Nota Importante

- La URL de ngrok cambia cada vez que lo reinicias (a menos que tengas cuenta de pago)
- Para desarrollo, esto es perfecto
- Para producción, considera desplegar el servidor en un servicio con HTTPS permanente

## Alternativa: ngrok con URL fija (requiere cuenta)

1. Crea cuenta gratuita en ngrok.com
2. Obtén tu authtoken
3. Configura: `ngrok config add-authtoken TU_TOKEN`
4. Ejecuta: `ngrok http 8000 --domain=tu-dominio.ngrok-free.app`


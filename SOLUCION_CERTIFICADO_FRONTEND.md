# Solución para ERR_CERT_AUTHORITY_INVALID en Frontend

## El Problema

El error `net::ERR_CERT_AUTHORITY_INVALID` ocurre porque:
- El navegador no confía en certificados SSL autofirmados
- **Los navegadores NO permiten que JavaScript ignore certificados inválidos** (por seguridad)
- Esto es diferente a Node.js donde puedes configurar `rejectUnauthorized: false`

## Soluciones

### Opción 1: Usar HTTP para Desarrollo Local (MÁS SIMPLE) ⭐

**Recomendado para desarrollo local.** Usa HTTPS solo cuando uses IIS Reverse Proxy en producción.

#### Paso 1: Desactivar SSL en el servidor

Edita `config/config.json`:

```json
{
  "api": {
    "ssl": {
      "enabled": false
    }
  }
}
```

#### Paso 2: Actualizar el frontend para usar HTTP en desarrollo

```javascript
// En tu archivo de configuración del frontend
const API_BASE_URL = 
  process.env.NODE_ENV === 'production'
    ? 'https://tu-dominio.com'  // HTTPS en producción (con IIS)
    : 'http://192.168.0.63:8000';  // HTTP en desarrollo local
```

**Ventajas:**
- ✅ Funciona inmediatamente, sin configuración adicional
- ✅ No hay problemas de certificados
- ✅ Más rápido para desarrollo
- ✅ HTTPS solo en producción (con IIS que maneja el certificado real)

---

### Opción 2: Aceptar el Certificado Manualmente en el Navegador

**Funciona, pero requiere hacerlo en cada navegador/dispositivo.**

1. Abre directamente en el navegador: `https://192.168.0.63:8000/health`
2. Verás una advertencia de "Tu conexión no es privada"
3. Haz clic en **"Avanzado"** o **"Advanced"**
4. Haz clic en **"Continuar a 192.168.0.63 (no seguro)"** o **"Proceed to 192.168.0.63 (unsafe)"**
5. El navegador recordará tu elección para ese dominio

**Limitaciones:**
- ❌ Debes hacerlo en cada navegador
- ❌ Debes hacerlo en cada dispositivo
- ❌ Puede no funcionar en algunos navegadores móviles
- ❌ El frontend en Netlify seguirá teniendo problemas (mixed content)

---

### Opción 3: Usar mkcert para Certificados Localmente Confiables

**La mejor solución técnica, pero requiere instalación adicional.**

`mkcert` genera certificados que son confiables localmente sin necesidad de aceptarlos manualmente.

#### Instalación de mkcert (Windows):

```powershell
# Opción A: Con Chocolatey
choco install mkcert

# Opción B: Con Scoop
scoop bucket add extras
scoop install mkcert

# Opción C: Descargar manualmente
# https://github.com/FiloSottile/mkcert/releases
```

#### Uso:

```powershell
# Instalar la CA local
mkcert -install

# Generar certificado para tu IP
mkcert 192.168.0.63 localhost 127.0.0.1

# Esto crea:
# - 192.168.0.63+2.pem (certificado)
# - 192.168.0.63+2-key.pem (clave privada)
```

Luego actualiza `config/config.json`:

```json
{
  "api": {
    "ssl": {
      "enabled": true,
      "cert_file": "192.168.0.63+2.pem",
      "key_file": "192.168.0.63+2-key.pem"
    }
  }
}
```

**Ventajas:**
- ✅ Funciona automáticamente en todos los navegadores
- ✅ No requiere aceptar manualmente
- ✅ Funciona en dispositivos móviles

**Desventajas:**
- ❌ Requiere instalar mkcert
- ❌ Cada desarrollador debe instalar mkcert
- ❌ No funciona en Netlify (solo local)

---

## Recomendación Final

**Para desarrollo local:** Usa **Opción 1 (HTTP)** - es la más simple y funciona perfectamente.

**Para producción:** Usa IIS Reverse Proxy con un certificado SSL real (Let's Encrypt o comercial), y el frontend se conecta a `https://tu-dominio.com` sin problemas.

**Flujo recomendado:**
- **Desarrollo:** Frontend (Netlify) → `http://192.168.0.63:8000` (HTTP)
- **Producción:** Frontend (Netlify) → `https://tu-dominio.com` (HTTPS con IIS) → `http://localhost:8000` (HTTP interno)


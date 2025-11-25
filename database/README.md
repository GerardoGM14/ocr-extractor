# Scripts de Base de Datos - Usuarios

Esta carpeta contiene los scripts SQL para crear y gestionar la tabla de usuarios en SQL Server.

## Archivos

### `BaseDatos_Newmont_Users.sql`
Script principal para crear la estructura de la base de datos:
- Tabla `usuarios` con campos: user_id, email, password_hash, nombre, activo, created_at, updated_at
- Función `HashPassword` para hashear contraseñas con SHA-256 y salt
- Procedimiento almacenado `ValidarLogin` para validar credenciales
- Procedimiento almacenado `SyncUsuarioFromJSON` para sincronizar usuarios desde JSON
- INSERTs iniciales para los 5 usuarios autorizados

### `sync_users_to_db.py`
Script Python auxiliar para verificar usuarios en el JSON (no ejecuta sincronización, solo muestra información).

## Instrucciones de Uso

### 1. Ejecutar el Script SQL

1. Abre SQL Server Management Studio (SSMS)
2. Conéctate a tu instancia de SQL Server
3. Asegúrate de que la base de datos `BD_NEWMONT_OCR_PDF` existe
4. Abre el archivo `BaseDatos_Newmont_Users.sql`
5. Ejecuta el script completo (F5)

**Nota:** El script está preparado para usar la base de datos existente. Si necesitas crear la BD, descomenta la sección correspondiente al inicio del script.

### 2. Configurar Conexión en Backend

Para que el backend sincronice automáticamente usuarios a la BD, configura la conexión en `config/config.json`:

```json
{
  "database": {
    "enabled": true,
    "server": "localhost",
    "database": "BD_NEWMONT_OCR_PDF",
    "username": "tu_usuario",
    "password": "tu_contraseña"
  }
}
```

O si usas autenticación de Windows:

```json
{
  "database": {
    "enabled": true,
    "server": "localhost",
    "database": "BD_NEWMONT_OCR_PDF"
  }
}
```

### 3. Instalar Dependencias

El backend necesita `pyodbc` para conectarse a SQL Server:

```bash
pip install pyodbc
```

## Funcionamiento

### Sincronización Automática

El backend sincroniza automáticamente usuarios a la BD cuando:
- Se genera una nueva contraseña en el JSON
- Se actualiza una contraseña existente

**Importante:** 
- El JSON sigue siendo la **fuente de verdad**
- La BD actúa como **respaldo/copia**
- Si la sincronización a BD falla, no afecta el funcionamiento del sistema

### Validación de Contraseñas

El sistema valida contraseñas desde el JSON. La BD solo almacena una copia hasheada.

## Estructura de la Tabla

```sql
CREATE TABLE dbo.usuarios (
    user_id INT IDENTITY(1,1) PRIMARY KEY,
    email NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,
    nombre NVARCHAR(255) NULL,
    activo BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
);
```

## Procedimientos Almacenados

### `ValidarLogin`
Valida credenciales de usuario:
```sql
EXEC dbo.ValidarLogin 
    @email = 'usuario@newmont.com',
    @password = 'contraseña';
```

### `SyncUsuarioFromJSON`
Sincroniza un usuario desde JSON a BD (usado automáticamente por el backend):
```sql
EXEC dbo.SyncUsuarioFromJSON 
    @email = 'usuario@newmont.com',
    @password = 'contraseña',
    @nombre = 'Nombre Usuario';
```

## Notas

- Las contraseñas se hashean usando SHA-256 con el email como salt
- Cada usuario tiene un hash único incluso con la misma contraseña
- El sistema es tolerante a fallos: si la BD no está disponible, el sistema sigue funcionando con el JSON


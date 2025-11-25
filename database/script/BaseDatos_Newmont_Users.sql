-- =============================================
-- USAR LA BASE DE DATOS
-- =============================================
USE BD_NEWMONT_OCR_PDF;
GO

-- =============================================
-- 3. CREACIÓN DE TABLA DE USUARIOS
-- =============================================
IF OBJECT_ID('dbo.MUSUARIOS', 'U') IS NOT NULL
    DROP TABLE dbo.MUSUARIOS;
GO

CREATE TABLE dbo.usuarios (
    user_id INT IDENTITY(1,1) PRIMARY KEY,
    email NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,
    nombre NVARCHAR(255) NULL,
    activo BIT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    
    -- Índices
    CONSTRAINT UQ_usuarios_email UNIQUE (email)
);
GO

-- Índice adicional para búsquedas por email
CREATE NONCLUSTERED INDEX IX_usuarios_email ON dbo.usuarios(email);
GO

-- =============================================
-- 4. FUNCIÓN PARA HASEAR CONTRASEÑAS CON SALT
-- =============================================
-- Función auxiliar para generar hash SHA-256 con salt
-- Nota: SQL Server no tiene bcrypt nativo, usamos SHA-256 con salt
IF OBJECT_ID('dbo.HashPassword', 'FN') IS NOT NULL
    DROP FUNCTION dbo.HashPassword;
GO

CREATE FUNCTION dbo.HashPassword(@password NVARCHAR(255), @salt NVARCHAR(255))
RETURNS NVARCHAR(255)
AS
BEGIN
    DECLARE @hashedPassword NVARCHAR(255);
    -- Concatenar password + salt y generar hash SHA-256
    SET @hashedPassword = CONVERT(NVARCHAR(255), HASHBYTES('SHA2_256', @password + @salt), 2);
    RETURN @hashedPassword;
END;
GO

-- =============================================
-- 5. INSERTAR USUARIOS CON CONTRASEÑAS HASHEADAS
-- =============================================
-- Las contraseñas se hashean con SHA-256 usando el email como salt
-- Esto asegura que cada usuario tenga un hash único incluso con la misma contraseña

-- Usuario 1: mariadelosangeles.abanto@newmont.com
-- Contraseña: fam#goP0
DECLARE @email1 NVARCHAR(255) = 'mariadelosangeles.abanto@newmont.com';
DECLARE @password1 NVARCHAR(255) = 'fam#goP0';
DECLARE @hash1 NVARCHAR(255) = dbo.HashPassword(@password1, @email1);

INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
VALUES (
    @email1,
    @hash1,
    'Maria de los Angeles Abanto',
    1,
    GETDATE(),
    GETDATE()
);
GO

-- Usuario 2: roberto.munoz@newmont.com
-- Contraseña: gE#f1kom
DECLARE @email2 NVARCHAR(255) = 'roberto.munoz@newmont.com';
DECLARE @password2 NVARCHAR(255) = 'gE#f1kom';
DECLARE @hash2 NVARCHAR(255) = dbo.HashPassword(@password2, @email2);

INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
VALUES (
    @email2,
    @hash2,
    'Roberto Munoz',
    1,
    GETDATE(),
    GETDATE()
);
GO

-- Usuario 3: victor.cabeza@newmont.com
-- Contraseña: ohkhk*0K
DECLARE @email3 NVARCHAR(255) = 'victor.cabeza@newmont.com';
DECLARE @password3 NVARCHAR(255) = 'ohkhk*0K';
DECLARE @hash3 NVARCHAR(255) = dbo.HashPassword(@password3, @email3);

INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
VALUES (
    @email3,
    @hash3,
    'Victor Cabeza',
    1,
    GETDATE(),
    GETDATE()
);
GO

-- Usuario 4: walter.quiliche@newmont.com
-- Contraseña: bm8pclM$
DECLARE @email4 NVARCHAR(255) = 'walter.quiliche@newmont.com';
DECLARE @password4 NVARCHAR(255) = 'bm8pclM$';
DECLARE @hash4 NVARCHAR(255) = dbo.HashPassword(@password4, @email4);

INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
VALUES (
    @email4,
    @hash4,
    'Walter Quiliche',
    1,
    GETDATE(),
    GETDATE()
);
GO

-- Usuario 5: luis.saenz@newmont.com
-- Contraseña: d!gg3oFj
DECLARE @email5 NVARCHAR(255) = 'luis.saenz@newmont.com';
DECLARE @password5 NVARCHAR(255) = 'd!gg3oFj';
DECLARE @hash5 NVARCHAR(255) = dbo.HashPassword(@password5, @email5);

INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
VALUES (
    @email5,
    @hash5,
    'Luis Saenz',
    1,
    GETDATE(),
    GETDATE()
);
GO

-- =============================================
-- 6. VERIFICACIÓN DE DATOS INSERTADOS
-- =============================================
SELECT 
    user_id,
    email,
    password_hash,
    nombre,
    activo,
    created_at,
    updated_at
FROM dbo.usuarios;
GO

-- =============================================
-- 7. PROCEDIMIENTO ALMACENADO PARA VALIDAR LOGIN
-- =============================================
-- Este procedimiento puede ser usado por el backend para validar credenciales
IF OBJECT_ID('dbo.ValidarLogin', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ValidarLogin;
GO

CREATE PROCEDURE dbo.ValidarLogin
    @email NVARCHAR(255),
    @password NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @password_hash NVARCHAR(255);
    DECLARE @user_id INT;
    DECLARE @nombre NVARCHAR(255);
    DECLARE @activo BIT;
    
    -- Generar hash de la contraseña proporcionada usando el email como salt
    SET @password_hash = dbo.HashPassword(@password, @email);
    
    -- Buscar usuario con email y password_hash coincidentes
    SELECT 
        @user_id = user_id,
        @nombre = nombre,
        @activo = activo
    FROM dbo.usuarios
    WHERE email = LOWER(LTRIM(RTRIM(@email)))
      AND password_hash = @password_hash
      AND activo = 1;
    
    -- Retornar resultado
    IF @user_id IS NOT NULL
    BEGIN
        SELECT 
            'success' AS resultado,
            @user_id AS user_id,
            @email AS email,
            @nombre AS nombre;
    END
    ELSE
    BEGIN
        SELECT 
            'error' AS resultado,
            'Credenciales inválidas o usuario inactivo' AS mensaje;
    END
END;
GO

-- =============================================
-- 8. PROCEDIMIENTO PARA INSERTAR/ACTUALIZAR USUARIO (BACKUP DESDE JSON)
-- =============================================
-- Este procedimiento permite que el backend sincronice usuarios desde JSON a BD
IF OBJECT_ID('dbo.SyncUsuarioFromJSON', 'P') IS NOT NULL
    DROP PROCEDURE dbo.SyncUsuarioFromJSON;
GO

CREATE PROCEDURE dbo.SyncUsuarioFromJSON
    @email NVARCHAR(255),
    @password NVARCHAR(255),
    @nombre NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @password_hash NVARCHAR(255);
    DECLARE @user_id INT;
    
    -- Generar hash de la contraseña
    SET @password_hash = dbo.HashPassword(@password, @email);
    
    -- Verificar si el usuario ya existe
    SELECT @user_id = user_id
    FROM dbo.usuarios
    WHERE email = LOWER(LTRIM(RTRIM(@email)));
    
    IF @user_id IS NOT NULL
    BEGIN
        -- Actualizar usuario existente
        UPDATE dbo.usuarios
        SET password_hash = @password_hash,
            nombre = ISNULL(@nombre, nombre),
            updated_at = GETDATE()
        WHERE user_id = @user_id;
        
        SELECT 'updated' AS accion, @user_id AS user_id;
    END
    ELSE
    BEGIN
        -- Insertar nuevo usuario
        INSERT INTO dbo.usuarios (email, password_hash, nombre, activo, created_at, updated_at)
        VALUES (
            LOWER(LTRIM(RTRIM(@email))),
            @password_hash,
            @nombre,
            1,
            GETDATE(),
            GETDATE()
        );
        
        SET @user_id = SCOPE_IDENTITY();
        SELECT 'inserted' AS accion, @user_id AS user_id;
    END
END;
GO

-- =============================================
-- 9. EJEMPLO DE USO DEL PROCEDIMIENTO
-- =============================================
-- Descomentar para probar la validación
/*
EXEC dbo.ValidarLogin 
    @email = 'victor.cabeza@newmont.com',
    @password = 'ohkhk*0K';
GO
*/

PRINT 'Script ejecutado correctamente. Base de datos y tabla de usuarios creadas.';
GO


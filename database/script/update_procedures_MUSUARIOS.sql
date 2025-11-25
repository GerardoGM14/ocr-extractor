-- =============================================
-- Script para actualizar procedimientos almacenados
-- para usar la tabla MUSUARIOS en lugar de usuarios
-- =============================================

USE BD_NEWMONT_OCR_PDF;
GO

-- =============================================
-- 1. ACTUALIZAR PROCEDIMIENTO ValidarLogin
-- =============================================
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
    
    -- Buscar usuario con email y password_hash coincidentes en MUSUARIOS
    SELECT 
        @user_id = user_id,
        @nombre = nombre,
        @activo = activo
    FROM dbo.MUSUARIOS
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
-- 2. ACTUALIZAR PROCEDIMIENTO SyncUsuarioFromJSON
-- =============================================
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
    
    -- Verificar si el usuario ya existe en MUSUARIOS
    SELECT @user_id = user_id
    FROM dbo.MUSUARIOS
    WHERE email = LOWER(LTRIM(RTRIM(@email)));
    
    IF @user_id IS NOT NULL
    BEGIN
        -- Actualizar usuario existente
        UPDATE dbo.MUSUARIOS
        SET password_hash = @password_hash,
            nombre = ISNULL(@nombre, nombre),
            updated_at = GETDATE()
        WHERE user_id = @user_id;
        
        SELECT 'updated' AS accion, @user_id AS user_id;
    END
    ELSE
    BEGIN
        -- Insertar nuevo usuario
        INSERT INTO dbo.MUSUARIOS (email, password_hash, nombre, activo, created_at, updated_at)
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

PRINT 'Procedimientos actualizados para usar la tabla MUSUARIOS.';
GO


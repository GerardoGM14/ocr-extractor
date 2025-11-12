"""
API Middleware - Middleware para autenticación y otros
Responsabilidad: Preparar middleware de autenticación (desactivado por ahora)
"""

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Instancia global para autenticación (preparada pero desactivada)
security = HTTPBearer(auto_error=False)


class AuthMiddleware:
    """
    Middleware de autenticación preparado pero desactivado.
    
    Para activar:
    1. Descomentar el código en process_request
    2. Configurar AUTH_ENABLED = True
    3. Implementar validación de tokens real
    """
    
    AUTH_ENABLED = False  # Cambiar a True para activar
    
    async def __call__(self, request: Request, call_next):
        """
        Procesa request y aplica autenticación si está activada.
        
        Args:
            request: Request de FastAPI
            call_next: Siguiente middleware/handler
            
        Returns:
            Response procesada
        """
        # AUTENTICACIÓN DESACTIVADA POR AHORA
        # Para activar, descomentar el bloque de abajo:
        
        # if self.AUTH_ENABLED:
        #     # Verificar token si está habilitado
        #     auth_header = request.headers.get("Authorization")
        #     if not auth_header:
        #         raise HTTPException(
        #             status_code=status.HTTP_401_UNAUTHORIZED,
        #             detail="Token de autenticación requerido"
        #         )
        #     
        #     # Validar token (implementar lógica real aquí)
        #     token = auth_header.replace("Bearer ", "")
        #     if not self._validate_token(token):
        #         raise HTTPException(
        #             status_code=status.HTTP_401_UNAUTHORIZED,
        #             detail="Token inválido"
        #         )
        
        response = await call_next(request)
        return response
    
    def _validate_token(self, token: str) -> bool:
        """
        Valida un token de autenticación.
        
        Args:
            token: Token a validar
            
        Returns:
            True si es válido, False si no
            
        NOTA: Implementar lógica real cuando se active autenticación.
        """
        # TODO: Implementar validación real cuando se active
        # Ejemplos:
        # - Validar JWT
        # - Consultar base de datos
        # - Validar contra servicio externo
        return False


async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = None) -> bool:
    """
    Función de dependencia para verificar tokens.
    
    Args:
        credentials: Credenciales HTTP Bearer (opcional si auth está desactivada)
        
    Returns:
        True si está autenticado
        
    NOTA: Solo se usa si AuthMiddleware.AUTH_ENABLED = True
    """
    if not AuthMiddleware.AUTH_ENABLED:
        return True  # Si auth está desactivada, permitir acceso
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido"
        )
    
    token = credentials.credentials
    # Validar token (implementar lógica real)
    if not _validate_token_real(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    
    return True


def _validate_token_real(token: str) -> bool:
    """
    Implementación real de validación de token (cuando se active).
    
    Args:
        token: Token a validar
        
    Returns:
        True si es válido
    """
    # TODO: Implementar cuando se active autenticación
    return False


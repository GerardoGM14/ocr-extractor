"""
Learning Module - Sistema de aprendizaje para mejora de precisión OCR
Responsabilidad: Registrar errores, analizar patrones, mejorar prompts
"""

from .error_tracker import ErrorTracker
from .prompt_manager import PromptManager
from .learning_service import LearningService

__all__ = ['ErrorTracker', 'PromptManager', 'LearningService']


class FacilioError(Exception):
    """Base exception pour les erreurs métier de Facilito."""


class InvalidUserInputError(FacilioError):
    """Échec de la validation de la saisie utilisateur."""


class InjectionDetectedError(FacilioError):
    """Une tentative d'injection a été détectée dans l'entrée utilisateur."""


class RateLimitError(FacilioError):
    """Les requêtes sont effectuées trop rapidement."""


class LLMTimeoutError(FacilioError):
    """L'appel au LLM a dépassé le délai prévu."""


class InvalidAPIKeyError(FacilioError):
    """La clé API fournie est invalide ou non autorisée."""


class ExternalServiceError(FacilioError):
    """Erreur remontée par un service externe (LLM, réseau, etc.)."""

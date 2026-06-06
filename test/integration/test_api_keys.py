"""Tests d'intégration — validation des clés API.

Vérifie que la détection des clés API fonctionne correctement.
Ces tests sont exécutés uniquement si la clé correspondante est valide."""
import pytest


@pytest.mark.openai
def test_openai_key_detected(request):
    """La clé OpenAI est détectée comme valide."""
    assert request.config._openai_ok is True


@pytest.mark.deepseek
def test_deepseek_key_detected(request):
    """La clé DeepSeek est détectée comme valide."""
    assert request.config._deepseek_ok is True

"""Intent classifier: routes user queries to simple or complex LLM model."""

import json

from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.security import call_llm_with_retry


ROUTER_PROMPT = """Tu es un routeur de requêtes pour un assistant de conception d'ateliers.
Analyse la demande ET le contexte de session fourni.
Réponds UNIQUEMENT en JSON avec les clés complexite et categorie.

Règles :
- complexite = "simple" si : salutation, question directe, consultation d'info, recherche unique, reformulation
- complexite = "complexe" si : analyse ou synthèse multi-étapes, création/modification lourde de session, planification détaillée, comparaison de plusieurs éléments, reconception complète

Catégories : "salutation", "faq", "raisonnement", "code", "analyse"

Exemples SIMPLES :
- "Bonjour" -> {{"complexite": "simple", "categorie": "salutation"}}
- "Liste les sessions" -> {{"complexite": "simple", "categorie": "faq"}}
- "Cherche un icebreaker" -> {{"complexite": "simple", "categorie": "faq"}}
- "Quelle est la durée ?" -> {{"complexite": "simple", "categorie": "faq"}}

Exemples COMPLEXES :
- "Analyse le contenu et suggère des améliorations" -> {{"complexite": "complexe", "categorie": "analyse"}}
- "Conçois une session complète avec 4 pratiques" -> {{"complexite": "complexe", "categorie": "raisonnement"}}
- "Compare les pratiques de brainstorming" -> {{"complexite": "complexe", "categorie": "analyse"}}
- "Reconception complète de la session" -> {{"complexite": "complexe", "categorie": "raisonnement"}}

Requête : {question}"""


def classifier_intent(provider, user_msg: str, session_id: int, cfg: dict) -> dict:
    routing_cfg = cfg.get("routing", {})
    if not routing_cfg.get("enabled", True):
        return {"complexite": "simple", "categorie": "faq"}

    ctx = db_ses.get_session_context(session_id)
    ctx_str = json.dumps(ctx, ensure_ascii=False, default=str) if ctx else "Pas de session"
    full_question = f"Contexte session : {ctx_str}\n\nQuestion : {user_msg}"

    messages = [
        {"role": "system", "content": ROUTER_PROMPT.format(question=full_question)},
    ]
    try:
        response, _ = call_llm_with_retry(
            provider, messages, tools=None,
            model=provider._router_model,
            timeout=10, max_retries=1,
        )
        raw = (response.get("content") or "").strip()
        parsed = json.loads(raw)
        complexite = parsed.get("complexite", "simple")
        categorie = parsed.get("categorie", "faq")
        if complexite not in ("simple", "complexe"):
            complexite = "simple"
        if categorie not in ("salutation", "faq", "raisonnement", "code", "analyse"):
            categorie = "faq"
        return {"complexite": complexite, "categorie": categorie}
    except Exception:
        return {"complexite": "simple", "categorie": "faq"}

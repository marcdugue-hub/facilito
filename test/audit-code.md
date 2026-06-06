# Audit Code — Facilito

**Date :** 5 juin 2026 (mis à jour)  
**Objet :** Analyse complète du code pour améliorer lisibilité et qualité  
**Périmètre :** Backend (Python/FastAPI, ~19 modules, 1347 lignes dans `main.py`), Frontend (Vanilla JS SPA, 1080 lignes), Tests (9 fichiers unitaires, 127 tests + 5 scripts d'évaluation), Infrastructure (Docker, configs)

> **Règle d'or :** cet audit identifie des axes d'amélioration. Aucune modification de code n'est faite à ce stade.

---

## Synthèse des Constats

| Axe | Nb de points | Gravité |
|-----|-------------|---------|
| God Object (`main.py`) | 0 | — |
| Architecture LLM / RAG | 4 | Élevée |
| Gestion d'erreurs | 4 | Moyenne |
| Typage et statique | 3 | Moyenne |
| Imports | 2 | Moyenne |
| Nommage | 2 | Faible |
| Documentation | 3 | Faible |
| Tests | 8 | Faible |
| Frontend | 6 | Moyenne |
| Config / Général | 5 | Moyenne |
| Docker | 3 | Moyenne |
| Prompts d'évaluation | 4 | Faible |

**Total : 44 points** (34 à l'audit initial du 22 mai 2026)

> **Résolu (5 juin 2026) :** Points 1.1 à 1.6 corrigés :
> - `Agent/Config/config.py` créé — `load_config()` et `get_project_root()` unifiés dans 6 fichiers
> - `DeepSeekProvider` hérite de `OpenAIProvider` — 18 lignes identiques supprimées
> - `_safe_json()` créé — 18 appels `json.dumps` standardisés
> - `_is_feature_enabled(key)` — 3 fonctions identiques consolidées
> - 8 routes settings → 2 routes paramétrées `/api/settings/{setting}`
>
> **Résolu (cette session) :** Points 2.1 à 2.4 corrigés (God Object `main.py` découpé) :
> 
> **Résolu (6 juin 2026) :** Points 3.1 à 3.4 corrigés :
> - `rerank.py`, `rewrite.py`, `hyde.py` utilisent désormais `LLMProvider` via `build_provider()` + `call_llm_with_retry()` — plus de clients OpenAI directs, retry, cost tracking, support DeepSeek
> - `hyde.py` : prompt système corrigé (CNIL/RGPD → fiche pratique d'atelier collaboratif)
> - `langfuse_handler.py` déplacé vers `Agent/Observability/`
> - `build_system_prompt()` extrait de `Memory/store.py` vers `Agent/Prompts/system_prompt.py`
> - `main.py` : 1308 → 80 lignes (factory + entry point only)
> - `Agent/Tools/tools_schema.py` : 16 tool schemas extraits
> - `Agent/Tools/tool_dispatch.py` : dispatch table `dict[str, Callable]` au lieu de `if/elif`
> - `Agent/Tools/agent_loop.py` : `run_agent_chat()` extrait de la route
> - `Agent/Tools/pdf_export.py`, `markdown.py`, `intent_classifier.py` : extraits
> - `Agent/LLM/provider_factory.py` : `build_provider()` extrait (évite import circulaire)
> - `Agent/Main/models.py` : 17 Pydantic models extraits
> - `Agent/Main/routes/` : 11 fichiers APIRouter par domaine (51 routes)

---

## 3. Architecture LLM / RAG (ÉLEVÉE)

### 3.1. `rerank.py`, `rewrite.py` et `hyde.py` contournent l'abstraction LLM

**Fichiers :**
- `Agent/Tools/RAG/rerank.py:14` — crée un client `OpenAI` directement
- `Agent/Tools/RAG/rewrite.py:16` — crée un client `OpenAI` directement
- `Agent/Tools/RAG/hyde.py:10` — crée un client `OpenAI` directement

Ces modules instancient leur propre client OpenAI sans passer par `LLMProvider` (ABC), ni par `_build_provider()`, ni par `retry_llm_call()`. Résultat :
- Pas de retry en cas d'échec
- Pas de cost tracking (pas d'intégration LangFuse)
- Pas de support DeepSeek pour ces opérations (sauf `rerank.py` qui a un mode manuel)
- Duplication de `load_dotenv()` et lecture de clé API

**Recommandation :** Faire utiliser `_build_provider()` par ces modules, ou injecter un provider via paramètre. Centraliser la création de client LLM.

### 3.2. `hyde.py` contient une référence erronée "CNIL/RGPD"

**Fichier :** `Agent/Tools/RAG/hyde.py:36`

Le prompt système HyDE dit : `"comme un extrait de guide CNIL/RGPD officiel"`. C'est un copier-coller d'un autre projet (probablement un RAG juridique). N'a aucun sens dans le contexte des pratiques de facilitation.

**Recommandation :** Corriger le prompt pour refléter le domaine réel (guide de facilitation, fiche pratique d'atelier).

### 3.3. `langfuse_handler.py` mal placé dans `Agent/Tools/`

**Fichier :** `Agent/Tools/langfuse_handler.py` (69 lignes)

LangFuse est une couche d'observabilité, pas un "outil" agent. Il n'est jamais référencé par les définitions de tools. Sa présence dans `Tools/` crée une confusion sémantique.

**Recommandation :** Déplacer vers `Agent/Observability/langfuse_handler.py` ou `Agent/Infrastructure/`.

### 3.4. `Memory/store.py` mélange historique et prompt système

**Fichier :** `Agent/Tools/Memory/store.py` (107 lignes)

- Le deque d'historique de conversation : ~30 lignes
- `build_system_prompt()` (prompt système complet en français) : ~67 lignes

Deux responsabilités distinctes dans le même module.

**Recommandation :** Séparer en `Memory/store.py` (historique brut) et `Prompts/system_prompt.py` (construction du prompt). Ou créer un répertoire `Agent/Prompts/` pour tous les prompts.

---

## 4. Gestion d'Erreurs (MOYENNE)

### 4.1. `except Exception` trop génériques

**Emplacements :**
- `Agent/Main/main.py:330` — `_is_rag_fallback()` avale toutes les exceptions et retourne `False`
- `Agent/Main/main.py:906` — `_dispatch_tool()` attrape tout avec `{"error": str(exc)}`, ce qui expose potentiellement des messages internes au client
- `Agent/Tools/RAG/init_rag.py:45` — `except Exception: continue` dans la boucle de parsing des fichiers Markdown (un fichier corrompu est silencieusement ignoré)
- `Agent/Tools/RAG/init_rag.py:106` — `except Exception: pass` sur une tentative de suppression de collection ChromaDB (peut masquer un vrai problème)

**Recommandation :**
- Remplacer par des types d'exceptions spécifiques (`FileNotFoundError`, `yaml.YAMLError`, `KeyError`, etc.)
- Logger systématiquement l'exception avant de l'avaler (`log_error` est disponible dans `security.py`)
- Dans `_dispatch_tool()`, filtrer le message d'erreur pour ne pas exposer la stack trace à l'utilisateur

### 4.2. Aucune journalisation dans les modules DB

Les fonctions CRUD de `Database/` n'ont ni `log_info`, ni `log_error`, ni `log_event`. En cas d'erreur SQL, l'exception remonte brute au client HTTP.

**Recommandation :** Ajouter des `log_error` dans les blocs `try/except` des modules DB, avec le contexte (requête SQL, paramètres).

### 4.3. Pas de fallback si ChromaDB est inaccessible

Si ChromaDB ne démarre pas ou si la collection est corrompue, `search.py` lève une exception non gérée qui remonte jusqu'à l'agent.

**Recommandation :** Wrapper `search_practices()` avec un try/except qui logge et retourne une liste vide ou un message d'indisponibilité.

### 4.4. `app.js` gère mal les erreurs agent

**Fichier :** `Agent/Main/static/app.js:848-849`

Les erreurs de l'agent sont affichées comme des messages de chat (`"Erreur : ..."`) sans action de récupération (retry, suggestion, reset).

**Recommandation :** Ajouter un bouton "Réessayer" sur les messages d'erreur, et différencier les types d'erreur (timeout, indisponibilité, erreur métier).

---

## 5. Typage et Analyse Statique (MOYENNE)

### 5.1. Pas de type checker configuré

Le `.gitignore` mentionne `.mypy_cache/` mais il n'existe ni `mypy.ini`, ni `pyproject.toml` avec config mypy/pyright. Aucun outil de typage statique n'est exécuté dans la CI.

**Recommandation :** Ajouter un `mypy.ini` minimal, corriger les erreurs progressivement. À terme, ajouter `mypy` dans les hooks pre-commit et dans la CI.

### 5.2. Incohérences de typage

- `main.py` utilise `dict` pour `_state` sans préciser les clés (devrait être un `TypedDict` ou un dataclass)
- `security.py:filter_sensitive_data(payload: Any) -> Any` — `Any` partout, le type ne documente rien
- `_dispatch_tool(tool_name, tool_args, session_id: int = 0)` — appelé souvent sans passer `session_id` explicitement, ce qui donne `0` par défaut (potentiellement dangereux)

**Recommandation :**
- Créer un `AppState` TypedDict ou une dataclass pour `_state`
- Typer `filter_sensitive_data` avec des overloads ou au minimum `dict[str, Any]`
- Supprimer le défaut `0` de `session_id`, le rendre obligatoire

### 5.3. Annotations PEP 604 (`dict | None`) utilisées sans vérification

Le code utilise `dict | None` au lieu d'`Optional[dict]` (PEP 604, Python 3.10+). Docker utilise Python 3.11, donc compatible. Mais si quelqu'un exécute le code avec Python 3.9 (non documenté comme incompatible), il aura des `TypeError`.

**Recommandation :** Documenter la version minimale requise (Python 3.10+) dans `README.md` et `setup.py`/`pyproject.toml`.

---

## 6. Imports et Organisation des Dépendances (MOYENNE)

### 6.1. Imports lazy (inside functions) éparpillés

**Emplacements :**
- `main.py:68,77` — dans `_build_provider()`
- `sessions.py:57-58` — dans `get_session_context()`
- `init_rag.py:84,89,93` — dans `init_chroma()`
- `search.py:16,24,36,40` — dans les fonctions de recherche

Raison : éviter de charger `chromadb`, `openai`, `sentence_transformers` au démarrage (lourds). C'est pragmatique mais rend le graphe de dépendances implicite et complique l'analyse statique.

**Recommandation :** Décorateur `@lazy_import` qui logge et gère l'import paresseux de manière standardisée, ou utiliser `importlib.import_module()` de façon cohérente. Documenter quels modules sont lourds et pourquoi ils sont lazy.

### 6.2. `sys.path.insert(0, ...)` hack pour les imports

**Fichiers :**
- `Agent/Main/main.py:19` — `sys.path.insert(0, str(_PROJECT_ROOT))`
- `Agent/Tools/RAG/init_rag.py:14` — `sys.path.insert(0, str(_BASE_DIR))`

Ce pattern modifie `sys.path` globalement. Si un autre module fait la même chose, il y a risque de collision.

**Recommandation :** Remplacer par un package installable (`pip install -e .`) avec un `pyproject.toml` ou `setup.py` qui définit `Agent` comme package racine. Les imports deviennent `from Agent.Tools.RAG.search import ...` sans manipulation de `sys.path`.

---

## 7. Nommage (FAIBLE)

### 7.1. Mélange français/anglais

- `Agent/Tools/erreur.py` → fichier en français, contenu en anglais
- Variable `duree` dans `init_rag.py:59` (français), fonction `parse_duration` (anglais)
- Descriptions de tools en français, code en anglais
- Messages utilisateur en français, noms de fonctions en anglais

**Recommandation :** Choisir une langue et s'y tenir. Si l'interface utilisateur est en français et le code en anglais, documenter cette convention dans `AGENTS.md` et s'assurer que tous les fichiers de code utilisent l'anglais (y compris les noms de fichiers).

### 7.2. Méthodes "privées" appelées de l'extérieur

`_dispatch_tool()` dans `main.py` a un préfixe `_` (convention "privé"), mais est appelée depuis `agent_chat()` (qui est une autre fonction du même module, donc acceptable) et potentiellement de l'extérieur.

**Recommandation :** Si la fonction est destinée à être l'API publique du dispatch, retirer le `_`. Si elle ne doit pas être appelée de l'extérieur, s'assurer que ce n'est pas le cas.

---

## 8. Documentation (FAIBLE)

### 8.1. Aucune docstring dans les modules Database

**Fichiers concernés :**
- `facilitators.py` — 0 docstrings
- `participants.py` — 0 docstrings
- `clients_teams.py` — 0 docstrings
- `analytics.py` — 1 docstring partielle
- `sessions.py` — 1 docstring partielle

Des fonctions comme `create_facilitator()`, `get_session_context()`, `log_event()` n'ont aucune documentation sur leurs paramètres, retours, ou effets de bord.

**Recommandation :** Ajouter des docstrings Google-style ou NumPy-style sur chaque fonction publique. Minimum : une phrase décrivant ce que fait la fonction.

### 8.2. `app.js` sans commentaires

**Fichier :** `Agent/Main/static/app.js` (1080 lignes)

Aucune JSDoc, aucun commentaire explicatif. Les fonctions comme `renderDashboard()`, `setupChat()`, `handleAgentResponse()` sont auto-descriptives mais leur logique métier ne l'est pas.

**Recommandation :** Ajouter des blocs JSDoc sur les fonctions principales (au moins `@param`, `@returns`, description). Commenter les sections complexes (WebSocket vs HTTP, reconnexion, state machine).

### 8.3. `style.css` manque de structure

**Fichier :** `Agent/Main/static/style.css` (810 lignes)

Le fichier a des commentaires de section mais pas de table des matières, pas de convention de nommage documentée, et des styles inline dans `main.py` pour le PDF (94 lignes de CSS dupliqué).

**Recommandation :** Extraire les styles PDF dans un fichier CSS séparé (`pdf_export.css`) chargé par `_render_pdf_html()`. Structurer `style.css` avec une convention (BEM, ITCSS, etc.).

---

## 9. Couverture de Tests (FAIBLE)

### 9.1. Pas de tests pour `security.py`

**Fichier :** `Agent/Tools/security.py` (197 lignes)

Les fonctions `detect_injection()`, `filter_sensitive_data()`, `check_rate_limit()`, `retry_llm_call()` n'ont aucun test unitaire. Ce sont pourtant des fonctions critiques pour la sécurité.

**Recommandation :** Créer `test/unitaires/test_security.py` avec au minimum :
- Injection SQL : cas positifs et négatifs pour chaque pattern
- Filtrage PII : email, téléphone, adresse
- Rate limiting : dépassement de quota, expiration de la fenêtre
- Retry : succès au 1er essai, succès après 2 retries, échec après max retries

### 9.2. Pas de tests pour `erreur.py`

**Fichier :** `Agent/Tools/erreur.py` (26 lignes)

Les classes `FacilitoError`, `ValidationError`, etc. ne sont pas testées (même si elles sont triviales, leur hiérarchie d'héritage mérite un test).

**Recommandation :** Ajouter des tests vérifiant :
- Chaque exception est bien une sous-classe de `FacilitoError`
- Les messages d'erreur sont correctement propagés
- `isinstance()` fonctionne pour chaque sous-classe

### 9.3. Pas de tests pour `init_rag.py`

**Fichier :** `Agent/Tools/RAG/init_rag.py` (161 lignes)

Les fonctions `parse_frontmatter()`, `chunk_content()`, `init_chroma()` sont non testées. L'initialisation RAG est une opération critique.

**Recommandation :** Créer `test/unitaires/test_init_rag.py` avec :
- Parsing de frontmatter YAML valide
- Parsing de frontmatter invalide (YAML corrompu, champs manquants)
- Découpage en chunks avec des contenus longs
- Test d'intégration avec ChromaDB in-memory

### 9.4. Pas de tests unitaires pour `rerank.py`, `rewrite.py`, `hyde.py`

**Fichiers :**
- `Agent/Tools/RAG/rerank.py` (80 lignes) — fonction `rerank_chunks()` avec parsing JSON et fallback
- `Agent/Tools/RAG/rewrite.py` (45 lignes) — fonction `rewrite_query()`
- `Agent/Tools/RAG/hyde.py` (42 lignes) — fonction `generer_hypothese()`

Ces modules sont couverts uniquement par les scripts d'évaluation d'intégration (`test/eval-rag/`) qui nécessitent un serveur fonctionnel et des clés API. Aucun test unitaire avec mock n'existe.

**Recommandation :** Ajouter des tests unitaires mockés : parsing de réponse LLM, fallback en cas d'erreur API, format de sortie.

### 9.5. Pas de tests pour les chemins d'erreur d'`embedder.py`

**Fichier :** `Agent/Tools/RAG/embedder.py` (40 lignes)

`get_openai_embeddings()` est testée indirectement via `test_rag.py` (avec mock), mais le chemin d'erreur "clé API manquante" n'est pas testé. La fonction `get_embeddings()` (locale) n'a pas de tests négatifs.

**Recommandation :** Ajouter des tests unitaires pour les erreurs (clé API absente, échec API).

### 9.6. Fallback `pytest_approx` inutile

**Fichier :** `test/unitaires/test_rag.py:126-130`

Le code vérifie si `pytest.approx` existe (ce qui est toujours le cas avec pytest) et sinon définit un fallback. Ce code mort peut être supprimé.

**Recommandation :** Supprimer la vérification et utiliser `pytest.approx` directement.

### 9.7. Imports dans les fonctions de test

Dans tous les fichiers de test, les imports sont faits à l'intérieur des fonctions plutôt qu'au niveau du module. Exemple : `from Agent.Tools.Database.facilitators import create_facilitator` dans chaque `test_*()`.

C'est intentionnel (pour l'isolation des fixtures via `conftest.py`), mais cela ajoute du bruit.

**Recommandation :** Centraliser les imports utilisés dans plusieurs tests au niveau du module (une fois que les fixtures sont stables), ou documenter explicitement pourquoi chaque import est dans la fonction.

### 9.8. Double `.gitignore` redondant

**Fichiers :**
- `.gitignore` (racine, 43 lignes) — complet
- `Agent/.gitignore` (9 lignes) — partiel, fait doublon

Le `.gitignore` racine couvre déjà tout. Celui dans `Agent/` est redondant.

**Recommandation :** Supprimer `Agent/.gitignore`.

---

## 10. Frontend — `app.js` et `style.css` (MOYENNE)

### 10.1. `state` global mutable sans protection

**Fichier :** `Agent/Main/static/app.js:5-19`

L'objet `state` est un mutex global. Des appels API asynchrones peuvent modifier `state.currentSessionId`, `state.currentView`, `state.participants` en parallèle sans coordination.

**Recommandation :** Utiliser un pattern de gestion d'état (event emitter minimal, ou une fonction `setState(partial)` qui valide les transitions et notifie les vues).

### 10.2. Pas de gestion d'état de chargement / skeleton UI

Les appels API ne montrent pas de loader pendant les requêtes longues (ex: chargement du dashboard, recherche de pratiques). L'utilisateur ne sait pas si l'action est en cours.

**Recommandation :** Ajouter une variable `state.loading` et des spinners/skeletons dans le rendu.

### 10.3. Logique métier dans les handlers DOM

`app.js` mélange logique métier (appels API, transformation de données) et manipulation DOM (création d'éléments HTML). Par exemple, `renderDashboard()` fait à la fois `fetch()` et `innerHTML`.

**Recommandation :** Séparer les appels API dans un module `api.js` et le rendu dans un module `ui.js`. Le `app.js` devient un orchestrateur.

### 10.4. Pas de gestion offline / retry automatique

Si le serveur est inaccessible, les `fetch()` échouent silencieusement ou avec un message générique. Pas de file d'attente de requêtes, pas de reconnexion automatique.

**Recommandation :** Ajouter un wrapper `fetch` avec retry (exponentiel, max 3 essais) et un indicateur de connectivité.

### 10.5. Templates HTML inline dans le JS

`renderDashboard()`, `renderSessionList()`, `renderChatMessage()` génèrent du HTML par concaténation de strings. Aucune protection XSS explicite.

**Recommandation :** Utiliser une fonction `escapeHtml()` systématique pour les données utilisateur. Envisager `<template>` ou un micro-templating pour isoler les templates HTML du code JS.

### 10.6. `style.css` — pas de variables pour les breakpoints

Les media queries dans `style.css` utilisent `768px`, `1024px`, etc. en dur. Si le design change, il faut modifier chaque occurrence.

**Recommandation :** Définir des variables de breakpoint (`--bp-tablet: 768px`, `--bp-desktop: 1024px`) dans `:root` et les référencer dans les media queries.

---

## 11. Configuration et Général (MOYENNE)

### 11.1. `_load_config()` appelée deux fois au démarrage

**Fichier :** `Agent/Main/main.py`

Aux lignes 50-52, `_load_config()` est appelée au niveau module. Puis dans le bloc `if __name__ == "__main__"`, elle est rappelée pour extraire `host` et `port`. Le fichier YAML est lu et parsé deux fois.

**Recommandation :** Appeler une seule fois, stocker dans une variable globale `CONFIG`, et y accéder partout.

### 11.2. Seuils et constantes magiques en dur

| Valeur | Emplacement | Problème |
|--------|-------------|----------|
| `0.3` (seuil RAG) | `main.py:329` | Non configurable, non documenté |
| `10` (taille mémoire) | `store.py` via config YAML | OK, mais pas de validation de plage |
| `10` (max itérations agent) | `main.py:1055` | Doublon avec `store.py`, devrait être synchronisé |
| `||RÉSOLU||` / `||NON_RÉSOLU||` | 3 fichiers | Pas de constante partagée |
| `max_iterations = 10` | `main.py:1055` | Hardcodé, devrait être dans `app_config.yaml` |
| `json.dumps(..., ensure_ascii=False, default=str)` | `main.py:_dispatch_tool()` | 16× duplication |

**Recommandation :**
- Déplacer les seuils dans `app_config.yaml`
- Créer `Agent/Tools/constantes.py` pour les marqueurs de résolution et autres chaînes partagées
- Valider les valeurs de config au démarrage

### 11.3. Pas de schéma de validation pour `app_config.yaml`

Le fichier YAML est chargé sans validation. Si une clé est absente ou mal typée, l'erreur survient au runtime (potentiellement loin du chargement).

**Recommandation :** Utiliser Pydantic `BaseSettings` ou un schéma JSON Schema pour valider la config au chargement. FastAPI a `@app.on_event("startup")` pour faire cette validation.

### 11.4. Prompts système et router hardcodés dans le code Python

**Emplacements :**
- `Agent/Tools/Memory/store.py:42-74` — **Prompt système** de l'agent (33 lignes) : identité, règles RAG, recherche équipes/clients, règles de liste, marqueurs de résolution
- `Agent/Main/main.py:117-139` — **`ROUTER_PROMPT`** (23 lignes) : classification d'intention, catégories, exemples JSON
- `Agent/Main/main.py:175-426` — **`TOOLS`** (250 lignes) : 16 définitions de tools OpenAI avec descriptions françaises, schémas de paramètres, enums

Ces prompts sont noyés dans le code Python. Un ajustement de prompt nécessite une modification de code + redéploiement.

**Recommandation :**
- `build_system_prompt()` → charger le template depuis `Agent/Config/prompts/system_prompt.yaml` avec interpolation Jinja2
- `ROUTER_PROMPT` → `Agent/Config/prompts/router_prompt.yaml`
- `TOOLS` → `Agent/Config/prompts/tools.yaml` et générer les schémas par une factory

### 11.5. Incohérence de nommage dans les fichiers `.env`

**Fichiers :**
- `Agent/.env` utilise `LANGFUSE_BASE_URL`
- `Agent/.env.example` utilise `LANGFUSE_HOST`

La variable n'a pas le même nom entre le fichier réel et le template. Un développeur qui copie `.env.example` vers `.env` aura une variable non reconnue.

**Recommandation :** Uniformiser sur `LANGFUSE_BASE_URL` dans les deux fichiers (ou documenter le mapping).

---

## 12. Docker (MOYENNE)

### 12.1. Flag `--openai` / `--deepseek` hardcodé dans Dockerfile et docker-compose

**Fichiers :**
- `Dockerfile` → `CMD ["python", "-m", "Agent.Main.main", "--openai"]`
- `docker-compose.yml` → `command: ["python", "-m", "Agent.Main.main", "--openai"]`

Le mode LLM est figé à la construction de l'image. Pour passer en DeepSeek, il faut reconstruire ou modifier le compose.

**Recommandation :** Remplacer par une variable d'environnement `LLM_MODE` (valeur `openai` ou `deepseek`), lue par `main.py`. Le `CMD` devient `["python", "-m", "Agent.Main.main"]` et le script choisit le mode via `os.environ`.

### 12.2. Version `torch` épinglée différemment entre Dockerfile et requirements

- `Dockerfile:17` → `torch==2.12.0` (version exacte, index CPU PyTorch)
- `requirements.txt` → `torch>=2.0.0` (minimum lâche)

Si `requirements.txt` est mis à jour vers une version majeure, le Dockerfile n'est pas automatiquement synchronisé. Le `--extra-index-url` CPU dans le Dockerfile peut aussi causer un pip install de la mauvaise version si les index sont en conflit.

**Recommandation :** Extraire la version torch dans une variable `ARG TORCH_VERSION=2.12.0` en haut du Dockerfile. Ou aligner `requirements.txt` avec la même contrainte exacte.

### 12.3. Pas de healthcheck endpoint dédié

**Fichier :** `Dockerfile:31-33`

Le healthcheck Docker interroge `localhost:8000/` (la racine du serveur). Il n'existe pas de route `/health` dédiée. La route `/` sert la SPA HTML — elle n'est pas conçue comme healthcheck.

**Recommandation :** Ajouter une route `GET /health` retournant `{"status": "ok"}` et l'utiliser dans le HEALTHCHECK.

---

## 13. Prompts d'Évaluation (FAIBLE)

### 13.1. Deux `JUDGE_SYSTEM_PROMPT` quasi-dupliqués

**Fichiers :**
- `test/eval-rag/run_eval.py:65-83` — prompt juge pour l'évaluation RAG
- `test/llm_judge/run_judge.py:41-65` — prompt juge pour l'évaluation agent

Les deux prompts sont quasiment identiques (évaluation de pertinence, fidélité, cohérence sur 5 points) avec des différences de formulation mineures. Pas de source unique de vérité pour les critères d'évaluation.

**Recommandation :** Extraire un prompt juge commun dans `test/shared/judge_prompt.yaml` ou `test/judge_prompt.py`, partagé par les deux scripts.

### 13.2. Questions du benchmark routing hardcodées en Python

**Fichier :** `test/routing_benchmark/benchmark_routing.py:27-43`

Les 15 questions du benchmark sont une liste Python inline, alors que `eval-rag` et `llm_judge` utilisent des fichiers `questions.json` externes. Incohérence dans l'approche.

**Recommandation :** Externaliser dans `test/routing_benchmark/questions.json`.

### 13.3. Prix des tokens hardcodés dans les scripts d'évaluation

**Fichiers :**
- `test/eval-rag/run_eval_rerank.py:41-44` — dict `COUTS`
- `test/routing_benchmark/benchmark_routing.py:45-50` — dict `PRICING`

Les coûts par token sont dupliqués en dur, avec un risque de désynchronisation entre eux et avec la table `cost_config` de la base de données.

**Recommandation :** Lire les coûts depuis la base `cost_config` (via l'API `/api/dashboard/config`) ou un fichier de config partagé.

### 13.4. Seuil de pertinence hardcodé dans `metrics.py`

**Fichier :** `test/eval-rag/metrics.py:4`

La fonction `est_pertinent()` utilise un seuil fixe : au moins 2 critères parmi la liste pour considérer un résultat pertinent. Non configurable.

**Recommandation :** Paramétrer le seuil dans `questions.json` (par question si besoin) ou en constante partagée.

---

## 14. Points Positifs (à conserver)

1. **Séparation propre des couches Database** — chaque module (facilitators, sessions, participants, clients_teams, analytics) a une responsabilité unique et une API cohérente.
2. **Bonne isolation des tests** — `conftest.py` fournit des fixtures avec SQLite in-memory, cache RAG vidé, et mémoire agent réinitialisée. 127 tests couvrent l'essentiel du code, tous isolés (zéro appel API).
3. **Abstraction LLM propre** — `LLMProvider` (ABC) avec deux implémentations interchangeables, utilisées via `_build_provider()`. (À corriger pour les modules RAG qui la contournent — cf. §3.1.)
4. **Couche de sécurité complète** — détection d'injection SQL multi-patterns, masquage PII, rate limiting, retry exponentiel. (Manque de tests — cf. §9.1.)
5. **Pas de framework frontend** — SPA en Vanilla JS (IIFE pattern), léger et sans dépendance npm.
6. **Boucle agent bien pensée** — max 10 itérations, injection de `session_id` pour la sécurité, logging structuré via `agent_events`, marqueurs de résolution.
7. **Export PDF professionnel** — weasyprint avec template HTML/CSS inline, en-tête et pied de page. (Fichier à externaliser — cf. §2.1.)
8. **Docker production-ready** — HEALTHCHECK, volumes pour persistance, PyTorch CPU-only, cache multi-layer.
9. **Pipeline RAG modulaire** — embedder → search → rewrite/hyde/rerank en étapes optionnelles, bien isolées. (Abstraction LLM à corriger — cf. §3.1.)
10. **Système d'évaluation complet** — 3 types d'évaluation (RAG qualité, LLM judge, routing benchmark), rapports Markdown horodatés, questions externalisées en JSON.

---

## 15. Plan d'Action Suggéré (ordre de priorité)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | Créer `Agent/Config/config.py` (élimine 6× duplication `_load_config`) | Critique | 1h |
| 2 | Extraire `TOOLS` dans `Agent/Tools/tools_schema.py` | ✓ Fait | — |
| 3 | Remplacer `if/elif` par dispatch table + décorateur `@session_scoped` | ✓ Fait | — |
| 4 | Découper `main.py` en routers + extraire PDF, Markdown, intent classifier | ✓ Fait | — |
| 5 | Faire utiliser `LLMProvider` par `rerank.py`, `rewrite.py`, `hyde.py` | ✓ Fait | — |
| 6 | Corriger le prompt HyDE (référence CNIL/RGPD erronée) | ✓ Fait | — |
| 7 | Externaliser `build_system_prompt`, `ROUTER_PROMPT`, `TOOLS` en YAML | Élevé | 1h30 |
| 8 | Ajouter docstrings dans tous les modules Database | Faible | 1h |
| 9 | Créer `test_security.py` (+ ~20 tests) | Moyen | 2h |
| 10 | Créer `test_init_rag.py` (+ ~10 tests) | Moyen | 1h |
| 11 | Créer tests unitaires pour `rerank.py`, `rewrite.py`, `hyde.py` (mockés) | Moyen | 1h30 |
| 12 | Configurer `mypy` + corriger erreurs progressivement | Moyen | 2h |
| 13 | Extraire `app.js` en modules `api.js` + `ui.js` | Moyen | 3h |
| 14 | Ajouter route `/health` pour Docker HEALTHCHECK | Faible | 10 min |
| 15 | Remplacer `--openai` hardcodé par `LLM_MODE` env var (Dockerfile + compose) | Faible | 15 min |
| 16 | Uniformiser `LANGFUSE_HOST` → `LANGFUSE_BASE_URL` dans `.env.example` | Faible | 2 min |
| 17 | Externaliser questions benchmark routing en JSON | Faible | 15 min |
| 18 | Extraire prompts juge commun pour eval-rag et llm_judge | Faible | 30 min |
| 19 | Ajouter loaders/skeletons dans l'UI | Faible | 1h |
| 20 | Créer `Agent/Tools/constantes.py` (marqueurs, seuils) | Faible | 15 min |
| 21 | Renommer `erreur.py` → `errors.py` (uniformité anglais) | Faible | 10 min |
| 22 | Déplacer `langfuse_handler.py` vers `Agent/Observability/` | ✓ Fait | — |
| 23 | Supprimer `Agent/.gitignore` redondant | Faible | 1 min |

---

*Fin de l'audit. Prêt à passer à l'implémentation sur demande.*

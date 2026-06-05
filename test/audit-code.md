# Audit Code — Facilito

**Date :** 22 mai 2026  
**Objet :** Analyse complète du code pour améliorer lisibilité et qualité  
**Périmètre :** Backend (Python/FastAPI, ~11 modules, 1053 lignes dans `main.py`), Frontend (Vanilla JS SPA, 1080 lignes), Tests (9 fichiers, ~102 tests), Infrastructure (Docker, configs)

> **Règle d'or :** cet audit identifie des axes d'amélioration. Aucune modification de code n'est faite à ce stade.

---

## Synthèse des Constats

| Axe | Nb de points | Gravité |
|-----|-------------|---------|
| Duplication de code | 3 | Critique |
| God Object (`main.py`) | 3 | Élevée |
| Gestion d'erreurs | 4 | Moyenne |
| Typage et statique | 3 | Moyenne |
| Imports | 2 | Moyenne |
| Nommage | 2 | Faible |
| Documentation | 3 | Faible |
| Tests | 5 | Faible |
| Frontend | 6 | Moyenne |
| Config / Général | 3 | Faible |

**Total : 34 points**

---

## 1. Duplication de Code (CRITIQUE)

### 1.1. `_load_config()` dupliquée dans 6 fichiers

**Fichiers concernés :**
- `Agent/Main/main.py:48-52`
- `Agent/Tools/Database/schema.py:9-15`
- `Agent/Tools/RAG/init_rag.py:17-19`
- `Agent/Tools/RAG/search.py:9-11`
- `Agent/Tools/RAG/embedder.py:10-12`
- `Agent/Tools/Memory/store.py:9-11`

La même logique de chargement YAML + résolution de `_BASE_DIR` est recopiée partout, avec des variantes du calcul de `parents[N]` selon la profondeur du fichier.

**Recommandation :** Créer un module `Agent/Config/config.py` exposant `load_config() -> dict` et `load_special_practices() -> dict`, avec cache interne. Tous les modules importeraient ce singleton.

### 1.2. `openai_provider.py` et `deepseek_provider.py` quasi identiques

**Fichiers :**
- `Agent/LLM/openai_provider.py` (17 lignes)
- `Agent/LLM/deepseek_provider.py` (17 lignes)

Seule différence : le constructeur de `DeepSeekProvider` accepte `base_url`. Les deux utilisent le même SDK OpenAI, la même méthode `chat()`, le même `model_dump()`. La séparation en deux classes n'apporte rien.

**Recommandation :** Fusionner en une seule classe `OpenAIProvider` avec `base_url` optionnel. Ou, si la séparation est voulue, `DeepSeekProvider` peut hériter de `OpenAIProvider` en surchargeant uniquement `__init__`.

### 1.3. Résolution de `_BASE_DIR` dépendante de la profondeur

**Fichiers :**
- `Agent/Tools/Database/schema.py:11` — `Path(__file__).resolve().parents[3]`
- `Agent/Tools/RAG/init_rag.py:15` — `Path(__file__).resolve().parents[3]`
- `Agent/Main/main.py:19` — `Path(__file__).resolve().parents[2]`

Le calcul est fragile : si un fichier est déplacé d'un niveau, le `parents[N]` change et les chemins cassent.

**Recommandation :** Définir `PROJECT_ROOT` une seule fois dans un module partagé (`Agent/Config/config.py`), calculé comme le répertoire contenant `pratiques/`, `data/`, ou `Agent/`.

---

## 2. God Object — `Agent/Main/main.py` (ÉLEVÉE)

### 2.1. Fichier de 1053 lignes avec trop de responsabilités

`main.py` contient :
- La factory FastAPI (`create_app()`, ~401 lignes de routes)
- Les 16 schémas JSON des tools agent (239 lignes)
- Le dispatch des tools (`_dispatch_tool()`, 77 lignes, un `if/elif` de 16 branches)
- La boucle de l'agent (`agent_chat()`, 178 lignes)
- Le rendu PDF (`_render_pdf_html()`, 94 lignes de HTML/CSS inline)
- Les modèles Pydantic de requêtes (13 classes)
- Le point d'entrée CLI (`__main__`, 15 lignes)
- Les fonctions de chargement de config

**Recommandation :** Découper en modules dédiés :
- `Agent/Tools/tools_schema.py` → la liste `TOOLS` (239 lignes)
- `Agent/Tools/tool_dispatch.py` → `_dispatch_tool()` (77 lignes) + mapping nom→fonction (pattern dispatch table plutôt qu'un `if/elif`)
- `Agent/Tools/agent_loop.py` → `agent_chat()` (178 lignes)
- `Agent/Tools/pdf_export.py` → `_render_pdf_html()` et la route d'export
- `Agent/Main/routes.py` → les 30 routes REST (découpe possible par domaine : sessions, participants, analytics, etc.)

### 2.2. `_dispatch_tool()` utilise un `if/elif` de 16 branches

**Fichier :** `Agent/Main/main.py:830-907`

La fonction fait un `if tool_name == "search_practices":`, puis un `elif tool_name == "add_practice":`, etc. Ce pattern est fragile : ajouter un tool nécessite d'ajouter une branche.

**Recommandation :** Remplacer par une **dispatch table** (un `dict[str, Callable]`). Chaque handler devient une fonction séparée, testable individuellement. Le mécanisme `_SESSION_SCOPED` (sécurité qui override `session_id`) peut être un décorateur.

### 2.3. Pas de découpage des routes par domaine

Les ~30 routes sont toutes dans `create_app()`. Une route `POST /api/sessions` côtoie `GET /api/analytics/kpis`.

**Recommandation :** Utiliser des `APIRouter` FastAPI par domaine logique :
- `routers/sessions.py`
- `routers/participants.py`
- `routers/facilitators.py`
- `routers/analytics.py`
- `routers/agent.py`
- `routers/pdf_export.py`

---

## 3. Gestion d'Erreurs (MOYENNE)

### 3.1. `except Exception` trop génériques

**Emplacements :**
- `Agent/Main/main.py:330` — `_is_rag_fallback()` avale toutes les exceptions et retourne `False`
- `Agent/Main/main.py:906` — `_dispatch_tool()` attrape tout avec `{"error": str(exc)}`, ce qui expose potentiellement des messages internes au client
- `Agent/Tools/RAG/init_rag.py:45` — `except Exception: continue` dans la boucle de parsing des fichiers Markdown (un fichier corrompu est silencieusement ignoré)
- `Agent/Tools/RAG/init_rag.py:106` — `except Exception: pass` sur une tentative de suppression de collection ChromaDB (peut masquer un vrai problème)

**Recommandation :**
- Remplacer par des types d'exceptions spécifiques (`FileNotFoundError`, `yaml.YAMLError`, `KeyError`, etc.)
- Logger systématiquement l'exception avant de l'avaler (`log_error` est disponible dans `security.py`)
- Dans `_dispatch_tool()`, filtrer le message d'erreur pour ne pas exposer la stack trace à l'utilisateur

### 3.2. Aucune journalisation dans les modules DB

Les fonctions CRUD de `Database/` n'ont ni `log_info`, ni `log_error`, ni `log_event`. En cas d'erreur SQL, l'exception remonte brute au client HTTP.

**Recommandation :** Ajouter des `log_error` dans les blocs `try/except` des modules DB, avec le contexte (requête SQL, paramètres).

### 3.3. Pas de fallback si ChromaDB est inaccessible

Si ChromaDB ne démarre pas ou si la collection est corrompue, `search.py` lève une exception non gérée qui remonte jusqu'à l'agent.

**Recommandation :** Wrapper `search_practices()` avec un try/except qui logge et retourne une liste vide ou un message d'indisponibilité.

### 3.4. `app.js` gère mal les erreurs agent

**Fichier :** `Agent/Main/static/app.js:848-849`

Les erreurs de l'agent sont affichées comme des messages de chat (`"Erreur : ..."`) sans action de récupération (retry, suggestion, reset).

**Recommandation :** Ajouter un bouton "Réessayer" sur les messages d'erreur, et différencier les types d'erreur (timeout, indisponibilité, erreur métier).

---

## 4. Typage et Analyse Statique (MOYENNE)

### 4.1. Pas de type checker configuré

Le `.gitignore` mentionne `.mypy_cache/` mais il n'existe ni `mypy.ini`, ni `pyproject.toml` avec config mypy/pyright. Aucun outil de typage statique n'est exécuté dans la CI.

**Recommandation :** Ajouter un `mypy.ini` minimal, corriger les erreurs progressivement. À terme, ajouter `mypy` dans les hooks pre-commit et dans la CI.

### 4.2. Incohérences de typage

- `main.py` utilise `dict` pour `_state` sans préciser les clés (devrait être un `TypedDict` ou un dataclass)
- `security.py:filter_sensitive_data(payload: Any) -> Any` — `Any` partout, le type ne documente rien
- `_dispatch_tool(tool_name, tool_args, session_id: int = 0)` — appelé souvent sans passer `session_id` explicitement, ce qui donne `0` par défaut (potentiellement dangereux)

**Recommandation :**
- Créer un `AppState` TypedDict ou une dataclass pour `_state`
- Typer `filter_sensitive_data` avec des overloads ou au minimum `dict[str, Any]`
- Supprimer le défaut `0` de `session_id`, le rendre obligatoire

### 4.3. Annotations PEP 604 (`dict | None`) utilisées sans vérification

Le code utilise `dict | None` au lieu d'`Optional[dict]` (PEP 604, Python 3.10+). Docker utilise Python 3.11, donc compatible. Mais si quelqu'un exécute le code avec Python 3.9 (non documenté comme incompatible), il aura des `TypeError`.

**Recommandation :** Documenter la version minimale requise (Python 3.10+) dans `README.md` et `setup.py`/`pyproject.toml`.

---

## 5. Imports et Organisation des Dépendances (MOYENNE)

### 5.1. Imports lazy (inside functions) éparpillés

**Emplacements :**
- `main.py:68,77` — dans `_build_provider()`
- `sessions.py:57-58` — dans `get_session_context()`
- `init_rag.py:84,89,93` — dans `init_chroma()`
- `search.py:16,24,36,40` — dans les fonctions de recherche

Raison : éviter de charger `chromadb`, `openai`, `sentence_transformers` au démarrage (lourds). C'est pragmatique mais rend le graphe de dépendances implicite et complique l'analyse statique.

**Recommandation :** Décorateur `@lazy_import` qui logge et gère l'import paresseux de manière standardisée, ou utiliser `importlib.import_module()` de façon cohérente. Documenter quels modules sont lourds et pourquoi ils sont lazy.

### 5.2. `sys.path.insert(0, ...)` hack pour les imports

**Fichiers :**
- `Agent/Main/main.py:19` — `sys.path.insert(0, str(_PROJECT_ROOT))`
- `Agent/Tools/RAG/init_rag.py:14` — `sys.path.insert(0, str(_BASE_DIR))`

Ce pattern modifie `sys.path` globalement. Si un autre module fait la même chose, il y a risque de collision.

**Recommandation :** Remplacer par un package installable (`pip install -e .`) avec un `pyproject.toml` ou `setup.py` qui définit `Agent` comme package racine. Les imports deviennent `from Agent.Tools.RAG.search import ...` sans manipulation de `sys.path`.

---

## 6. Nommage (FAIBLE)

### 6.1. Mélange français/anglais

- `Agent/Tools/erreur.py` → fichier en français, contenu en anglais
- Variable `duree` dans `init_rag.py:59` (français), fonction `parse_duration` (anglais)
- Descriptions de tools en français, code en anglais
- Messages utilisateur en français, noms de fonctions en anglais

**Recommandation :** Choisir une langue et s'y tenir. Si l'interface utilisateur est en français et le code en anglais, documenter cette convention dans `AGENTS.md` et s'assurer que tous les fichiers de code utilisent l'anglais (y compris les noms de fichiers).

### 6.2. Méthodes "privées" appelées de l'extérieur

`_dispatch_tool()` dans `main.py` a un préfixe `_` (convention "privé"), mais est appelée depuis `agent_chat()` (qui est une autre fonction du même module, donc acceptable) et potentiellement de l'extérieur.

**Recommandation :** Si la fonction est destinée à être l'API publique du dispatch, retirer le `_`. Si elle ne doit pas être appelée de l'extérieur, s'assurer que ce n'est pas le cas.

---

## 7. Documentation (FAIBLE)

### 7.1. Aucune docstring dans les modules Database

**Fichiers concernés :**
- `facilitators.py` — 0 docstrings
- `participants.py` — 0 docstrings
- `clients_teams.py` — 0 docstrings
- `analytics.py` — 1 docstring partielle
- `sessions.py` — 1 docstring partielle

Des fonctions comme `create_facilitator()`, `get_session_context()`, `log_event()` n'ont aucune documentation sur leurs paramètres, retours, ou effets de bord.

**Recommandation :** Ajouter des docstrings Google-style ou NumPy-style sur chaque fonction publique. Minimum : une phrase décrivant ce que fait la fonction.

### 7.2. `app.js` sans commentaires

**Fichier :** `Agent/Main/static/app.js` (1080 lignes)

Aucune JSDoc, aucun commentaire explicatif. Les fonctions comme `renderDashboard()`, `setupChat()`, `handleAgentResponse()` sont auto-descriptives mais leur logique métier ne l'est pas.

**Recommandation :** Ajouter des blocs JSDoc sur les fonctions principales (au moins `@param`, `@returns`, description). Commenter les sections complexes (WebSocket vs HTTP, reconnexion, state machine).

### 7.3. `style.css` manque de structure

**Fichier :** `Agent/Main/static/style.css` (810 lignes)

Le fichier a des commentaires de section mais pas de table des matières, pas de convention de nommage documentée, et des styles inline dans `main.py` pour le PDF (94 lignes de CSS dupliqué).

**Recommandation :** Extraire les styles PDF dans un fichier CSS séparé (`pdf_export.css`) chargé par `_render_pdf_html()`. Structurer `style.css` avec une convention (BEM, ITCSS, etc.).

---

## 8. Couverture de Tests (FAIBLE)

### 8.1. Pas de tests pour `security.py`

**Fichier :** `Agent/Tools/security.py` (188 lignes)

Les fonctions `detect_injection()`, `filter_sensitive_data()`, `check_rate_limit()`, `retry_llm_call()` n'ont aucun test unitaire. Ce sont pourtant des fonctions critiques pour la sécurité.

**Recommandation :** Créer `test/unitaires/test_security.py` avec au minimum :
- Injection SQL : cas positifs et négatifs pour chaque pattern
- Filtrage PII : email, téléphone, adresse
- Rate limiting : dépassement de quota, expiration de la fenêtre
- Retry : succès au 1er essai, succès après 2 retries, échec après max retries

### 8.2. Pas de tests pour `erreur.py`

**Fichier :** `Agent/Tools/erreur.py` (26 lignes)

Les classes `FacilitoError`, `ValidationError`, etc. ne sont pas testées (même si elles sont triviales, leur hiérarchie d'héritage mérite un test).

**Recommandation :** Ajouter des tests vérifiant :
- Chaque exception est bien une sous-classe de `FacilitoError`
- Les messages d'erreur sont correctement propagés
- `isinstance()` fonctionne pour chaque sous-classe

### 8.3. Pas de tests pour `init_rag.py`

**Fichier :** `Agent/Tools/RAG/init_rag.py` (161 lignes)

Les fonctions `parse_frontmatter()`, `chunk_content()`, `init_chroma()` sont non testées. L'initialisation RAG est une opération critique.

**Recommandation :** Créer `test/unitaires/test_init_rag.py` avec :
- Parsing de frontmatter YAML valide
- Parsing de frontmatter invalide (YAML corrompu, champs manquants)
- Découpage en chunks avec des contenus longs
- Test d'intégration avec ChromaDB in-memory

### 8.4. Fallback `pytest_approx` inutile

**Fichier :** `test/unitaires/test_rag.py:126-130`

Le code vérifie si `pytest.approx` existe (ce qui est toujours le cas avec pytest) et sinon définit un fallback. Ce code mort peut être supprimé.

**Recommandation :** Supprimer la vérification et utiliser `pytest.approx` directement.

### 8.5. Imports dans les fonctions de test

Dans tous les fichiers de test, les imports sont faits à l'intérieur des fonctions plutôt qu'au niveau du module. Exemple : `from Agent.Tools.Database.facilitators import create_facilitator` dans chaque `test_*()`.

C'est intentionnel (pour l'isolation des fixtures via `conftest.py`), mais cela ajoute du bruit.

**Recommandation :** Centraliser les imports utilisés dans plusieurs tests au niveau du module (une fois que les fixtures sont stables), ou documenter explicitement pourquoi chaque import est dans la fonction.

---

## 9. Frontend — `app.js` et `style.css` (MOYENNE)

### 9.1. `state` global mutable sans protection

**Fichier :** `Agent/Main/static/app.js:5-19`

L'objet `state` est un mutex global. Des appels API asynchrones peuvent modifier `state.currentSessionId`, `state.currentView`, `state.participants` en parallèle sans coordination.

**Recommandation :** Utiliser un pattern de gestion d'état (event emitter minimal, ou une fonction `setState(partial)` qui valide les transitions et notifie les vues).

### 9.2. Pas de gestion d'état de chargement / skeleton UI

Les appels API ne montrent pas de loader pendant les requêtes longues (ex: chargement du dashboard, recherche de pratiques). L'utilisateur ne sait pas si l'action est en cours.

**Recommandation :** Ajouter une variable `state.loading` et des spinners/skeletons dans le rendu.

### 9.3. Logique métier dans les handlers DOM

`app.js` mélange logique métier (appels API, transformation de données) et manipulation DOM (création d'éléments HTML). Par exemple, `renderDashboard()` fait à la fois `fetch()` et `innerHTML`.

**Recommandation :** Séparer les appels API dans un module `api.js` et le rendu dans un module `ui.js`. Le `app.js` devient un orchestrateur.

### 9.4. Pas de gestion offline / retry automatique

Si le serveur est inaccessible, les `fetch()` échouent silencieusement ou avec un message générique. Pas de file d'attente de requêtes, pas de reconnexion automatique.

**Recommandation :** Ajouter un wrapper `fetch` avec retry (exponentiel, max 3 essais) et un indicateur de connectivité.

### 9.5. Templates HTML inline dans le JS

`renderDashboard()`, `renderSessionList()`, `renderChatMessage()` génèrent du HTML par concaténation de strings. Aucune protection XSS explicite.

**Recommandation :** Utiliser une fonction `escapeHtml()` systématique pour les données utilisateur. Envisager `<template>` ou un micro-templating pour isoler les templates HTML du code JS.

### 9.6. `style.css` — pas de variables pour les breakpoints

Les media queries dans `style.css` utilisent `768px`, `1024px`, etc. en dur. Si le design change, il faut modifier chaque occurrence.

**Recommandation :** Définir des variables de breakpoint (`--bp-tablet: 768px`, `--bp-desktop: 1024px`) dans `:root` et les référencer dans les media queries.

---

## 10. Configuration et Général (FAIBLE)

### 10.1. `_load_config()` appelée deux fois au démarrage

**Fichier :** `Agent/Main/main.py`

Aux lignes 50-52, `_load_config()` est appelée au niveau module. Puis à la ligne 1047, dans le bloc `if __name__ == "__main__"`, elle est rappelée pour extraire `host` et `port`. Le fichier YAML est lu et parsé deux fois.

**Recommandation :** Appeler une seule fois, stocker dans une variable globale `CONFIG`, et y accéder partout.

### 10.2. Seuils et constantes magiques en dur

| Valeur | Emplacement | Problème |
|--------|-------------|----------|
| `0.3` (seuil RAG) | `main.py:329` | Non configurable, non documenté |
| `10` (taille mémoire) | `store.py` via config YAML | OK, mais pas de validation de plage |
| `10` (max itérations agent) | `main.py:868` | Doublon avec `store.py`, devrait être synchronisé |
| `||RÉSOLU||` / `||NON_RÉSOLU||` | 3 fichiers | Pas de constante partagée |

**Recommandation :**
- Déplacer les seuils dans `app_config.yaml`
- Créer `Agent/Tools/constantes.py` pour les marqueurs de résolution et autres chaînes partagées
- Valider les valeurs de config au démarrage

### 10.3. Pas de schéma de validation pour `app_config.yaml`

Le fichier YAML est chargé sans validation. Si une clé est absente ou mal typée, l'erreur survient au runtime (potentiellement loin du chargement).

**Recommandation :** Utiliser Pydantic `BaseSettings` ou un schéma JSON Schema pour valider la config au chargement. FastAPI a `@app.on_event("startup")` pour faire cette validation.

---

## 11. Points Positifs (à conserver)

1. **Séparation propre des couches Database** — chaque module (facilitators, sessions, participants, clients_teams, analytics) a une responsabilité unique et une API cohérente.
2. **Bonne isolation des tests** — `conftest.py` fournit des fixtures avec SQLite in-memory, cache RAG vidé, et mémoire agent réinitialisée. 102 tests couvrent l'essentiel du code.
3. **Abstraction LLM propre** — `LLMProvider` (ABC) avec deux implémentations interchangeables, utilisées via `_build_provider()`.
4. **Couche de sécurité complète** — détection d'injection SQL multi-patterns, masquage PII, rate limiting, retry exponentiel.
5. **Pas de framework frontend** — SPA en Vanilla JS (IIFE pattern), léger et sans dépendance npm.
6. **Boucle agent bien pensée** — max 10 itérations, injection de `session_id` pour la sécurité, logging structuré, marqueurs de résolution.
7. **Export PDF professionnel** — weasyprint avec template HTML/CSS inline, en-tête et pied de page.
8. **Docker production-ready** — HEALTHCHECK, volumes pour persistance, PyTorch CPU-only, cache multi-layer.

---

## 12. Plan d'Action Suggéré (ordre de priorité)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | Créer `Agent/Config/config.py` (élimine 6× duplication) | Critique | 1h |
| 2 | Extraire `TOOLS` dans `Agent/Tools/tools_schema.py` | Élevé | 30 min |
| 3 | Remplacer `if/elif` par dispatch table + décorateur `@session_scoped` | Élevé | 1h |
| 4 | Découper `main.py` en routers + extraire PDF | Élevé | 2h |
| 5 | Ajouter docstrings dans tous les modules Database | Faible | 1h |
| 6 | Créer `test_security.py` (+ ~20 tests) | Moyen | 2h |
| 7 | Créer `test_init_rag.py` (+ ~10 tests) | Moyen | 1h |
| 8 | Configurer `mypy` + corriger erreurs progressivement | Moyen | 2h |
| 9 | Extraire `app.js` en modules `api.js` + `ui.js` | Moyen | 3h |
| 10 | Ajouter loaders/skeletons dans l'UI | Faible | 1h |
| 11 | Créer `Agent/Tools/constantes.py` (marqueurs, seuils) | Faible | 15 min |
| 12 | Renommer `erreur.py` → `errors.py` (uniformité anglais) | Faible | 10 min |

---

*Fin de l'audit. Prêt à passer à l'implémentation sur demande.*

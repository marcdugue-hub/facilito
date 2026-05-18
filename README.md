# Facilito

Application web Python/FastAPI pour aider les facilitateurs à concevoir des ateliers collaboratifs. Un agent IA (LLM avec function-calling) recommande des pratiques issues d'un RAG et peut agir directement sur les sessions.

---

## Lancement rapide avec Docker

### Prérequis

- [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/) installés
- Variables d’environnement définies dans `Agent/.env`
- Créer `Agent/.env` à partir de `Agent/.env.example` et y renseigner vos clés API :

```bash
cp Agent/.env.example Agent/.env
```

Puis éditez `Agent/.env` :

```env
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
```

### 1. Construire l'image

```bash
docker build -t facilito:v1 .
```

### 2. Initialiser le RAG (une seule fois, en local)

Le répertoire `data/` est partagé entre la machine hôte et le conteneur via un bind mount. Il suffit d'initialiser le RAG **une seule fois en local** — Docker utilisera directement les mêmes données :

```bash
python -m Agent.Tools.RAG.init_rag
```

Cela crée `data/chroma_db/` et `data/facilito.db` sur la machine hôte.

### 3. Démarrer l'application

**Option A : avec docker-compose**

```bash
docker-compose up -d
```

**Option B : avec docker run**

```bash
docker run -d \
  -p 8001:8001 \
  -e OPENAI_API_KEY=sk-your-key-here \
  -v $(pwd)/data:/app/data \
  facilito:v1
```

Ou avec DeepSeek :

```bash
docker run -d \
  -p 8001:8001 \
  -e DEEPSEEK_API_KEY=sk-your-key-here \
  -v $(pwd)/data:/app/data \
  facilito:v1 python -m Agent.Main.main --deepseek
```

### Interface

**http://localhost:8001**

Pour utiliser DeepSeek comme LLM :

```bash
# Modifier la commande dans docker-compose.yml :
# CMD ["python", "-m", "Agent.Main.main", "--deepseek"]
docker-compose up -d
```

### Arrêter

```bash
docker-compose down
```

Les données sont dans `data/` sur la machine hôte (bind mount) — elles survivent aux redémarrages du conteneur. Pour tout réinitialiser :

```bash
rm -rf data/
python -m Agent.Tools.RAG.init_rag
```

---

## Lancement local (sans Docker)

### Prérequis

```bash
python -m pip install -r requirements.txt
```

- Copiez `Agent/.env.example` en `Agent/.env` et renseignez vos clés API :

```bash
cp Agent/.env.example Agent/.env
```

### 1. Initialiser le RAG

```bash
python -m Agent.Tools.RAG.init_rag
```

### 2. Démarrer le serveur

```bash
python -m Agent.Main.main --openai    # GPT-4o (défaut)
python -m Agent.Main.main --deepseek  # DeepSeek
```

**http://localhost:8001**

---

## Tests unitaires

### Prérequis

```bash
python -m pip install -r requirements-test.txt
```

### Lancer tous les tests

```bash
python -m pytest test/unitaires/
```

### Avec détail et couverture

```bash
python -m pytest test/unitaires/ -v
python -m pytest test/unitaires/ -v --cov=Agent --cov-report=term-missing
```

118 tests couvrent : outils Database (facilitateurs, sessions, participants, équipes, clients, analytics), mémoire agent, RAG (ChromaDB + fallback), providers LLM (OpenAI / DeepSeek) et la boucle agent complète. Le LLM est mocké avec des réponses statiques — aucun appel API réel n'est effectué.

---

## Évaluation LLM-as-Judge

Le framework d'évaluation qualitative mesure la qualité des réponses de l'agent sur trois dimensions : **Pertinence** (pratiques adaptées au besoin), **Fidélité** (informations exactes, sans hallucination) et **Cohérence** (réponse structurée et gestion des cas limites). Chaque dimension est activable/désactivable question par question via des booléens dans le fichier de configuration.

### Fichiers

| Fichier | Rôle |
|---|---|
| `test/llm_judge/questions.json` | 20 questions réparties en 9 catégories avec comportement attendu et booléens d'évaluation |
| `test/llm_judge/run_judge.py` | Script principal — interroge l'agent puis le juge, génère le rapport |
| `test/llm_judge/reports/` | Rapports Markdown horodatés générés par le script |

### Prérequis

Le serveur Facilito doit être démarré avant de lancer l'évaluation :

```bash
python -m Agent.Main.main --openai
```

### Lancer l'évaluation complète

```bash
# Avec OpenAI comme juge (défaut)
python test/llm_judge/run_judge.py --openai

# Avec DeepSeek comme juge
python test/llm_judge/run_judge.py --deepseek

# Serveur sur un port non standard
python test/llm_judge/run_judge.py --base-url http://localhost:8001
```

### Options avancées

```bash
# Évaluer seulement certaines questions (par ID)
python test/llm_judge/run_judge.py --ids 1,4,10,14

# Spécifier un fichier de questions alternatif
python test/llm_judge/run_judge.py --questions test/llm_judge/my_questions.json

# Écrire le rapport à un emplacement précis
python test/llm_judge/run_judge.py --output rapports/eval_v2.md
```

### Structure du fichier questions.json

```json
{
  "id": 1,
  "categorie": "Factuelle simple",
  "question": "...",
  "comportement_attendu": "...",
  "eval_pertinence": true,
  "eval_fidelite": true,
  "eval_coherence": false
}
```

Les trois booléens (`eval_pertinence`, `eval_fidelite`, `eval_coherence`) activent ou désactivent chaque dimension d'évaluation pour la question. Une dimension désactivée apparaît comme « non évalué » dans le rapport et n'entre pas dans le calcul de la moyenne.

### Catégories de questions

| Catégorie | Description | Nb |
|---|---|:-:|
| Factuelle simple | Vérification de données brutes issues des fiches (durée, participants, niveau) | 3 |
| Complexe / comparative | Comparaisons et recommandations argumentées entre plusieurs pratiques | 2 |
| Ambiguë | Questions sans contexte suffisant — l'agent doit demander des précisions | 2 |
| Hors sujet / absurde | Questions hors domaine — l'agent doit décliner poliment | 2 |
| Piège (fidélité) | Questions dont la réponse intuitive est fausse selon le corpus | 2 |
| Contrainte de format | Respect d'une consigne de format (tableau, une phrase, n éléments) | 2 |
| Multi-tools | Enchaînements d'outils (recherche RAG + ajout session) | 2 |
| Bord de domaine | Cas à la limite du corpus (distanciel, gestion des conflits) | 2 |
| Recommandation guidée | Conception d'un programme complet avec contraintes multiples | 3 |

### Format du rapport généré

Le rapport Markdown commence par un tableau de synthèse coloré (🔴 < 3.0 · 🟡 3.0–3.9 · 🟢 ≥ 4.0), suivi des résultats détaillés par question : réponse de l'agent, scores par dimension et justification du juge.

---

## Architecture

| Composant | Description |
|---|---|
| `Agent/Main/main.py` | Serveur FastAPI — routes API + boucle agent |
| `Agent/Main/static/` | SPA HTML/CSS/JS (aucun framework frontend) |
| `Agent/Tools/Database/` | CRUD SQLite (facilitateurs, sessions, participants, équipes, clients) |
| `Agent/Tools/RAG/` | Initialisation et recherche ChromaDB |
| `Agent/Tools/Memory/` | Historique 10 échanges + builder system prompt |
| `Agent/LLM/` | Abstraction LLM (OpenAI / DeepSeek) |
| `Agent/Config/` | `app_config.yaml`, `special_practices.yaml` |
| `pratiques/` | 73 fiches pratiques Markdown (source du RAG) |

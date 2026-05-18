# Facilito

Application web Python/FastAPI pour aider les facilitateurs à concevoir des ateliers collaboratifs. Un agent IA (LLM avec function-calling) recommande des pratiques issues d'un RAG et peut agir directement sur les sessions.

---

## Lancement rapide avec Docker

### Prérequis

- [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/) installés
- Clés API renseignées dans `Agent/.env` :

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

```bash
docker-compose up -d
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

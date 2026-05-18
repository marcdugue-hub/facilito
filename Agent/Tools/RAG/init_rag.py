"""
Script d'initialisation du RAG Chroma DB.
Usage : python -m Agent.Tools.RAG.init_rag [--reinit]
"""
import argparse
import re
import sys
from pathlib import Path

import frontmatter
import yaml

_BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BASE_DIR))


def _load_config() -> dict:
    with open(_BASE_DIR / "Agent" / "Config" / "app_config.yaml") as f:
        return yaml.safe_load(f)


def _parse_duration(duree: str) -> int:
    """Convert duration string like '30'' or '60-90'' to integer minutes (take max)."""
    if not duree:
        return 30
    nums = re.findall(r"\d+", str(duree))
    if not nums:
        return 30
    return max(int(n) for n in nums)


def _extract_section(content: str, section: str) -> str:
    """Extract text under a Markdown ## section heading."""
    pattern = rf"##\s+{re.escape(section)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def load_practices() -> list[dict]:
    practices_dir = _BASE_DIR / "pratiques"
    practices = []
    for md_file in sorted(practices_dir.glob("*.md")):
        try:
            post = frontmatter.load(str(md_file))
        except Exception as e:
            print(f"  Skip {md_file.name}: {e}")
            continue

        meta = post.metadata
        content = post.content

        objectif = _extract_section(content, "Objectif")
        resume = _extract_section(content, "Résumé de la pratique")

        text_to_embed = " ".join(filter(None, [
            meta.get("titre", ""),
            meta.get("categorie", ""),
            meta.get("phase", ""),
            objectif,
            resume,
        ]))

        practices.append({
            "id": str(meta.get("id", md_file.stem)),
            "titre": meta.get("titre", md_file.stem),
            "categorie": meta.get("categorie", ""),
            "phase": meta.get("phase", ""),
            "difficulte": meta.get("difficulte", ""),
            "duree": meta.get("duree", ""),
            "duration_minutes": _parse_duration(meta.get("duree")),
            "participants": meta.get("participants", ""),
            "icone_code": meta.get("icone_code", ""),
            "url": meta.get("url", ""),
            "pdf": meta.get("pdf", ""),
            "illustration": meta.get("illustration", ""),
            "text_to_embed": text_to_embed,
            "objectif": objectif,
            "resume": resume,
        })
    return practices


def init_chroma(reinit: bool = False) -> None:
    import chromadb

    from Agent.Tools.RAG.embedder import get_embeddings

    cfg = _load_config()

    chroma_path = str(_BASE_DIR / cfg["chroma"]["path"])
    collection_name = cfg["chroma"]["collection"]

    client = chromadb.PersistentClient(path=chroma_path)

    if reinit:
        try:
            client.delete_collection(collection_name)
            print(f"Collection '{collection_name}' supprimée.")
        except Exception:
            pass

    existing = [c.name for c in client.list_collections()]
    if collection_name in existing and not reinit:
        count = client.get_collection(collection_name).count()
        print(f"Collection '{collection_name}' existe déjà ({count} documents). Utilisez --reinit pour réinitialiser.")
        return

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    practices = load_practices()
    print(f"  {len(practices)} pratiques trouvées. Génération des embeddings...")

    batch_size = 50
    for i in range(0, len(practices), batch_size):
        batch = practices[i:i + batch_size]
        texts = [p["text_to_embed"] for p in batch]
        embeddings = get_embeddings(texts)

        collection.add(
            ids=[p["id"] for p in batch],
            embeddings=embeddings,
            documents=[p["text_to_embed"] for p in batch],
            metadatas=[{
                "titre": p["titre"],
                "categorie": p["categorie"],
                "phase": p["phase"],
                "difficulte": p["difficulte"],
                "duree": p["duree"],
                "duration_minutes": p["duration_minutes"],
                "participants": p["participants"],
                "icone_code": p["icone_code"],
                "url": p["url"],
                "pdf": p["pdf"],
                "objectif": p["objectif"],
                "resume": p["resume"],
            } for p in batch],
        )
        print(f"  Lot {i // batch_size + 1} : {len(batch)} pratiques indexées.")

    print(f"\nRAG initialisé : {collection.count()} documents dans '{collection_name}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialise le RAG Facilito")
    parser.add_argument("--reinit", action="store_true", help="Supprime et recrée la collection")
    args = parser.parse_args()
    init_chroma(reinit=args.reinit)

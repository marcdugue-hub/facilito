"""
Évaluation Re-ranking LLM (LLM-as-Reranker) — compare vecteur seul vs re-ranking maison.

Pipeline par question (exercice 6 — « Retrieve large, rerank small ») :
  1. Top-10 vectoriel (question → embedding → ChromaDB)
  2. Baseline : MRR@3, Recall@3 sur les 3 premiers chunks (vecteur seul)
  3. Re-ranking LLM : classer les 10 chunks avec gpt-4o-mini / deepseek-chat, garder top-3
  4. MRR@3, Recall@3 après re-ranking
  5. Tableau comparatif avec latence et coût estimé

Usage :
  python test/eval-rag/run_eval_rerank.py              # re-ranker = gpt-4o-mini
  python test/eval-rag/run_eval_rerank.py --deepseek    # re-ranker = deepseek-chat
  python test/eval-rag/run_eval_rerank.py --ids Q1,Q3   # questions spécifiques
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import chromadb
import yaml
from dotenv import load_dotenv
from openai import OpenAI

from metrics import est_pertinent, mrr_at_k, recall_at_k

# ── Paths ──────────────────────────────────────────────────────────────────────
ENV_FILE = Path(__file__).resolve().parents[2] / "Agent" / ".env"
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
REPORTS_DIR = Path(__file__).parent / "reports"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "Agent" / "Config" / "app_config.yaml"

load_dotenv(ENV_FILE)

# ── Coûts estimés par token (USD) ─────────────────────────────────────────────
COUTS = {
    "gpt-4o-mini": {"input": 0.15e-6, "output": 0.60e-6},   # par token
    "deepseek-chat": {"input": 0.50e-6, "output": 1.00e-6},  # par token
}

# ── ChromaDB helpers ───────────────────────────────────────────────────────────
def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _get_collection():
    cfg = _load_config()
    path = str(Path(__file__).resolve().parents[2] / cfg["chroma"]["path"])
    client = chromadb.PersistentClient(path=path)
    return client.get_collection(cfg["chroma"]["collection"])


def embed(texte: str) -> list[float]:
    e = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).embeddings.create(
        model="text-embedding-3-small",
        input=texte,
    )
    return e.data[0].embedding


def search_rag_chroma(query_embedding: list[float], k: int = 10) -> list[dict]:
    collection = _get_collection()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()),
        include=["metadatas", "documents", "distances"],
    )
    practices = []
    for i, meta in enumerate(results["metadatas"][0]):
        practices.append({
            "titre": meta.get("titre", ""),
            "categorie": meta.get("categorie", ""),
            "phase": meta.get("phase", ""),
            "difficulte": meta.get("difficulte", ""),
            "duree": meta.get("duree", ""),
            "objectif": meta.get("objectif", ""),
            "resume": meta.get("resume", ""),
            "score": round(1 - results["distances"][0][i], 3),
        })
    return practices


# ── Re-ranking LLM (exercice 6 — « Retrieve large, rerank small ») ────────────
def reranker_llm(question: str, chunks: list[dict], top_n: int = 3,
                 llm_client: OpenAI = None, model: str = "gpt-4o-mini") -> tuple[list[dict], list[int]]:
    """
    Re-rank chunks by LLM relevance judgment.
    Retourne (top_n chunks, ordre_complet des indices).
    Fallback : ordre vectoriel si JSON invalide.
    """
    client = llm_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    docs = ""
    for i, c in enumerate(chunks):
        source = c.get("source", c.get("categorie", ""))
        contenu = c.get("contenu", "")[:500]
        docs += f"\n--- DOC {i} [{source}] ---\n{contenu}\n"

    try:
        r = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=100,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Classe TOUS les {len(chunks)} documents du PLUS au MOINS pertinent "
                        f"par rapport à la question. "
                        'Réponds UNIQUEMENT au format JSON {"ranking":[indices]} avec TOUS '
                        f"les indices de 0 à {len(chunks)-1}."
                    ),
                },
                {
                    "role": "user",
                    "content": f"QUESTION : {question}\n\nDOCUMENTS :{docs}",
                },
            ],
        )
        raw_content = r.choices[0].message.content
        parsed = json.loads(raw_content)
        ordre = parsed["ranking"]
        if len(ordre) != len(chunks):
            print(f"    ⚠ LLM n'a classé que {len(ordre)}/{len(chunks)} docs: {ordre}")
    except Exception:
        return chunks[:top_n], list(range(len(chunks)))

    out = [chunks[i] for i in ordre if 0 <= i < len(chunks)]
    for c in chunks:
        if c not in out:
            out.append(c)
    return out[:top_n], ordre


def estimer_cout(question: str, chunks: list[dict], model: str) -> float:
    """Estimation du coût d'une requête de re-ranking en USD."""
    couts = COUTS.get(model, COUTS["gpt-4o-mini"])
    input_chars = sum(len(c.get("contenu", "")[:500]) for c in chunks) + len(question)
    input_tokens = input_chars // 4
    output_tokens = 50
    return input_tokens * couts["input"] + output_tokens * couts["output"]


# ── Helpers (repris de run_eval_hyde.py) ──────────────────────────────────────
def _build_chunks(raw: list[dict], q: dict) -> list[dict]:
    for c in raw:
        c["contenu"] = " ".join(filter(None, [
            c.get("titre", ""),
            c.get("categorie", ""),
            c.get("objectif", ""),
            c.get("resume", ""),
        ]))
        c["source"] = c.get("categorie", "")
    flags = [est_pertinent(c, q) for c in raw]
    for i, c in enumerate(raw):
        c["pertinent"] = flags[i] if i < len(flags) else False
    return raw


def _rag_metrics(chunks: list[dict], q: dict) -> tuple[float, float, list[bool], list[dict]]:
    flags = [est_pertinent(c, q) for c in chunks]
    return mrr_at_k(flags, 3), recall_at_k(flags, 3), flags, chunks


# ── Report ─────────────────────────────────────────────────────────────────────
def build_report(results: list[dict], meta: dict, llm_model: str) -> str:
    now_str = meta["generated_at"]
    duration = meta["total_duration_s"]

    lines = [
        f"# Rapport d'évaluation Re-ranking LLM — Facilito\n",
        f"> Généré le **{now_str}**  |  Durée : **{duration:.1f}s**  |  "
        f"Modèle de re-ranking : **{llm_model}**\n",
        "## Comparaison Vecteur seul vs Re-ranking LLM\n",
        "| # | Question | MRR@3 vecteur | MRR@3 rerank | Gain MRR | "
        "Rec@3 vecteur | Rec@3 rerank | Gain Rec |",
        "|:-:|:---------|:-------------:|:------------:|:--------:|"
        ":-------------:|:------------:|:--------:|",
    ]

    all_mrr_v, all_mrr_r = [], []
    all_rec_v, all_rec_r = [], []
    all_lat_v, all_lat_r = [], []
    all_cost = []

    for r in results:
        all_mrr_v.append(r["mrr_vecteur"])
        all_mrr_r.append(r["mrr_rerank"])
        all_rec_v.append(r["recall_vecteur"])
        all_rec_r.append(r["recall_rerank"])
        all_lat_v.append(r["latence_vecteur_ms"])
        all_lat_r.append(r["latence_rerank_ms"])
        all_cost.append(r["cout_rerank"])

        gain_mrr = r["mrr_rerank"] - r["mrr_vecteur"]
        gain_rec = r["recall_rerank"] - r["recall_vecteur"]
        gain_mrr_s = f"+{gain_mrr:.3f}" if gain_mrr >= 0 else f"{gain_mrr:.3f}"
        gain_rec_s = f"+{gain_rec:.3f}" if gain_rec >= 0 else f"{gain_rec:.3f}"

        lines.append(
            f"| {r['id']} "
            f"| {r['question'][:50]}… "
            f"| {r['mrr_vecteur']:.3f} "
            f"| {r['mrr_rerank']:.3f} "
            f"| {gain_mrr_s} "
            f"| {r['recall_vecteur']:.3f} "
            f"| {r['recall_rerank']:.3f} "
            f"| {gain_rec_s} |"
        )

    avg_mrr_v = round(sum(all_mrr_v) / len(all_mrr_v), 3)
    avg_mrr_r = round(sum(all_mrr_r) / len(all_mrr_r), 3)
    avg_rec_v = round(sum(all_rec_v) / len(all_rec_v), 3)
    avg_rec_r = round(sum(all_rec_r) / len(all_rec_r), 3)
    avg_lat_v = round(sum(all_lat_v) / len(all_lat_v), 1)
    avg_lat_r = round(sum(all_lat_r) / len(all_lat_r), 1)
    avg_cost = round(sum(all_cost) / len(all_cost), 6)
    gain_mrr_tot = round(avg_mrr_r - avg_mrr_v, 3)
    gain_rec_tot = round(avg_rec_r - avg_rec_v, 3)

    lines += [
        "",
        f"| **Moy.** | — | **{avg_mrr_v:.3f}** | **{avg_mrr_r:.3f}** "
        f"| **{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f}** "
        f"| **{avg_rec_v:.3f}** | **{avg_rec_r:.3f}** "
        f"| **{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f}** |",
        "",
    ]

    # ── Tableau de synthèse (format exercice 6) ──────────────────────
    pct_mrr = (gain_mrr_tot / avg_mrr_v * 100) if avg_mrr_v else 0
    pct_rec = (gain_rec_tot / avg_rec_v * 100) if avg_rec_v else 0
    lines += [
        "### Métriques agrégées\n",
        "| Métrique (moyenne 8 questions) | Vecteur seul (top-3) | Re-rank maison (top-3) | Gain |",
        "|:-------------------------------|:---------------------:|:-----------------------:|:----:|",
        f"| **MRR@3** | {avg_mrr_v:.3f} | {avg_mrr_r:.3f} | "
        f"{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f} ({pct_mrr:+.1f}%) |",
        f"| **Recall@3** | {avg_rec_v:.3f} | {avg_rec_r:.3f} | "
        f"{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f} ({pct_rec:+.1f}%) |",
        f"| **Latence moyenne / requête (ms)** | {avg_lat_v:.0f} | {avg_lat_r:.0f} | "
        f"{avg_lat_r - avg_lat_v:+.0f} |",
        f"| **Coût / requête ($)** | ≈ 0 | ~{avg_cost:.6f} | — |",
        "",
    ]

    # ── Résultats détaillés par question ─────────────────────────────
    lines.append("## Résultats détaillés par question\n")

    for r in results:
        lines += [
            f"### {r['id']} — {r['question'][:70]}",
            "",
            f"**Question :** {r['question']}",
            "",
            f"**MRR@3 vecteur :** {r['mrr_vecteur']:.3f}  |  "
            f"**MRR@3 rerank :** {r['mrr_rerank']:.3f}  |  "
            f"**Recall@3 vecteur :** {r['recall_vecteur']:.3f}  |  "
            f"**Recall@3 rerank :** {r['recall_rerank']:.3f}",
            "",
            f"**Latence vecteur :** {r['latence_vecteur_ms']:.0f} ms  |  "
            f"**Latence rerank :** {r['latence_rerank_ms']:.0f} ms  |  "
            f"**Coût rerank :** ~${r['cout_rerank']:.6f}",
            "",
            "#### Top-10 (vecteur seul — ordre ChromaDB)",
            "",
            "| Rang | Pertinent | Titre | Catégorie | Score |",
            "|:---:|:---------:|:------|:----------|:----:|",
        ]
        for ci, c in enumerate(r["chunks_vecteur"]):
            flag = "🟢" if c["pertinent"] else "🔴"
            lines.append(
                f"| {ci + 1} | {flag} | **{c['titre']}** | {c['categorie']} | {c.get('score', '—')} |"
            )

        lines += [
            "",
            "#### Top-10 (après re-ranking LLM)",
            "",
            "| Rang | Pertinent | Titre | Catégorie | Score originel |",
            "|:---:|:---------:|:------|:----------|:--------------:|",
        ]
        for ci, c in enumerate(r["chunks_rerank_full"]):
            flag = "🟢" if c["pertinent"] else "🔴"
            lines.append(
                f"| {ci + 1} | {flag} | **{c['titre']}** | {c['categorie']} | {c.get('score', '—')} |"
            )

        lines += [
            "",
            f"**Ordre complet (indices originaux) :** {r['ordre_complet']}",
            "",
            f"**Top-3 retenus :** {r['ordre_rerank']}",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation Re-ranking LLM Facilito")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--openai", action="store_true", default=True,
                       help="Utiliser OpenAI comme re-ranker (défaut : gpt-4o-mini)")
    group.add_argument("--deepseek", action="store_true",
                       help="Utiliser DeepSeek comme re-ranker (deepseek-chat)")
    parser.add_argument("--output", default=None,
                        help="Chemin du rapport (défaut: reports/report_exo6_YYYYMMDD_HHMMSS.md)")
    parser.add_argument("--ids", default=None,
                        help="IDs de questions à exécuter, séparés par des virgules (ex: Q1,Q3)")
    args = parser.parse_args()

    provider = "deepseek" if args.deepseek else "openai"
    llm_model = "deepseek-chat" if args.deepseek else "gpt-4o-mini"

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            sys.exit("DEEPSEEK_API_KEY manquant dans Agent/.env")
        llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    else:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            sys.exit("OPENAI_API_KEY manquant dans Agent/.env")
        llm_client = OpenAI(api_key=api_key)

    if not QUESTIONS_PATH.exists():
        sys.exit(f"Fichier introuvable : {QUESTIONS_PATH}")
    questions: list[dict] = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    if args.ids:
        id_filter = {s.strip() for s in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in id_filter]
        if not questions:
            sys.exit(f"Aucune question trouvée pour les IDs : {args.ids}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"report_exo6_{timestamp}.md"

    global_start = time.time()
    results = []

    for q in questions:
        qid = q["id"]
        question = q["question"]
        criteres = q["criteres"]
        print(f"\n[{qid}] {question[:70]}…")

        # ── 1. Baseline : embedding → RAG top-10 → métriques sur top-3 ─
        t0 = time.time()
        emb = embed(question)
        raw_top10 = search_rag_chroma(emb, k=10)
        lat_vec = (time.time() - t0) * 1000
        chunks_vec = _build_chunks(raw_top10, q)
        mrr_v, rec_v, flags_v, _ = _rag_metrics(chunks_vec, q)
        n_rel_v = sum(flags_v)
        print(f"  Vecteur    ({lat_vec:.0f}ms): {len(chunks_vec)} chunks, "
              f"{n_rel_v} pert. — MRR@3={mrr_v:.3f} Rec@3={rec_v:.3f}")

        # ── 2. Re-ranking LLM : classer les 10 → garder top-3 ─────────
        t0 = time.time()
        try:
            reranked_top3, ordre_complet = reranker_llm(
                question, chunks_vec, top_n=3,
                llm_client=llm_client, model=llm_model,
            )
        except Exception as exc:
            print(f"  Rerank error: {exc}")
            reranked_top3 = chunks_vec[:3]
            ordre_complet = list(range(len(chunks_vec)))
        lat_rerank = (time.time() - t0) * 1000

        chunks_rerank = _build_chunks(reranked_top3, q)
        mrr_rr, rec_rr, flags_rr, _ = _rag_metrics(chunks_rerank, q)
        n_rel_rr = sum(flags_rr)
        cout = estimer_cout(question, chunks_vec, llm_model)

        # Reconstruire l'ordre complet des 10 chunks re-classés
        reranked_full = [chunks_vec[i] for i in ordre_complet if 0 <= i < len(chunks_vec)]
        for c in chunks_vec:
            if c not in reranked_full:
                reranked_full.append(c)
        chunks_rerank_full = _build_chunks(reranked_full, q)

        # Indices du top-3
        ordre_rerank_top3 = []
        for c in reranked_top3:
            try:
                idx = next(i for i, oc in enumerate(chunks_vec)
                           if oc["titre"] == c["titre"])
                ordre_rerank_top3.append(idx)
            except StopIteration:
                ordre_rerank_top3.append(-1)

        # Vérifier si l'ordre a changé par rapport au vecteur
        rerank_diff = "↔" if ordre_rerank_top3 == [0, 1, 2] else "↕"
        print(f"  Rerank     ({lat_rerank:.0f}ms): {len(reranked_top3)} chunks, "
              f"{n_rel_rr} pert. — MRR@3={mrr_rr:.3f} Rec@3={rec_rr:.3f} "
              f"{rerank_diff} ordre: {ordre_complet[:10]} (~${cout:.6f})")

        results.append({
            "id": qid,
            "question": question,
            "criteres": criteres,
            "chunks_vecteur": chunks_vec,
            "chunks_rerank": chunks_rerank,
            "chunks_rerank_full": chunks_rerank_full,
            "mrr_vecteur": mrr_v,
            "mrr_rerank": mrr_rr,
            "recall_vecteur": rec_v,
            "recall_rerank": rec_rr,
            "latence_vecteur_ms": lat_vec,
            "latence_rerank_ms": lat_rerank,
            "cout_rerank": cout,
            "ordre_rerank": ordre_rerank_top3,
            "ordre_complet": ordre_complet[:10],
        })

    total_duration = time.time() - global_start
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_s": total_duration,
    }

    report_md = build_report(results, meta, llm_model)
    output_path.write_text(report_md, encoding="utf-8")
    print(f"\nRapport : {output_path}")


if __name__ == "__main__":
    main()

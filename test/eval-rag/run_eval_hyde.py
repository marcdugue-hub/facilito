"""
Évaluation HyDE (Hypothetical Document Embeddings) — compare requête brute vs HyDE.

Pour chaque question :
  1. RAG TOP-10 (question brute) → vecteur pertinence → MRR@3, Recall@3
  2. Génération document hypothétique (gpt-4o-mini) → embedding → RAG TOP-10 → MRR@3, Recall@3
  3. Tableau comparatif

Usage :
  python test/eval-rag/run_eval_hyde.py
  python test/eval-rag/run_eval_hyde.py --ids Q1,Q3
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import chromadb
import httpx
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

# ── Clients ────────────────────────────────────────────────────────────────────
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ── HyDE helpers ───────────────────────────────────────────────────────────────
def generer_hypothese(question: str) -> str:
    r = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        max_tokens=180,
        messages=[
            {
                "role": "system",
                "content": (
                    "Redige un court paragraphe repondant a la question, "
                    "comme un extrait de guide CNIL/RGPD officiel."
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    return r.choices[0].message.content.strip()


def embed(texte: str) -> list[float]:
    e = _openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texte,
    )
    return e.data[0].embedding


# ── ChromaDB helpers ───────────────────────────────────────────────────────────
def _get_collection():
    cfg = _load_config()
    path = str(Path(__file__).resolve().parents[2] / cfg["chroma"]["path"])
    client = chromadb.PersistentClient(path=path)
    return client.get_collection(cfg["chroma"]["collection"])


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


# ── Helpers ────────────────────────────────────────────────────────────────────
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
def build_report(results: list[dict], meta: dict) -> str:
    now_str = meta["generated_at"]
    duration = meta["total_duration_s"]

    lines = [
        f"# Rapport d'évaluation HyDE — Facilito\n",
        f"> Généré le **{now_str}**  |  Durée : **{duration:.1f}s**\n",
        "## Comparaison Baseline vs HyDE\n",
        "| # | Hypothèse | MRR@3 baseline | MRR@3 HyDE | Gain MRR | "
        "Rec@3 baseline | Rec@3 HyDE | Gain Rec |",
        "|:-:|:----------|:--------------:|:----------:|:--------:|"
        ":--------------:|:----------:|:--------:|",
    ]

    all_mrr_base, all_mrr_hyde = [], []
    all_rec_base, all_rec_hyde = [], []
    all_lat_base, all_lat_hyde = [], []

    for r in results:
        all_mrr_base.append(r["mrr_brut"])
        all_mrr_hyde.append(r["mrr_hyde"])
        all_rec_base.append(r["recall_brut"])
        all_rec_hyde.append(r["recall_hyde"])
        all_lat_base.append(r["latence_brut_ms"])
        all_lat_hyde.append(r["latence_hyde_ms"])

        gain_mrr = r["mrr_hyde"] - r["mrr_brut"]
        gain_rec = r["recall_hyde"] - r["recall_brut"]
        gain_mrr_s = f"+{gain_mrr:.3f}" if gain_mrr >= 0 else f"{gain_mrr:.3f}"
        gain_rec_s = f"+{gain_rec:.3f}" if gain_rec >= 0 else f"{gain_rec:.3f}"

        hypo_short = r["hypothese"][:50].replace("\n", " ")
        lines.append(
            f"| {r['id']} "
            f"| {hypo_short}… "
            f"| {r['mrr_brut']:.3f} "
            f"| {r['mrr_hyde']:.3f} "
            f"| {gain_mrr_s} "
            f"| {r['recall_brut']:.3f} "
            f"| {r['recall_hyde']:.3f} "
            f"| {gain_rec_s} |"
        )

    avg_mrr_b = round(sum(all_mrr_base) / len(all_mrr_base), 3)
    avg_mrr_h = round(sum(all_mrr_hyde) / len(all_mrr_hyde), 3)
    avg_rec_b = round(sum(all_rec_base) / len(all_rec_base), 3)
    avg_rec_h = round(sum(all_rec_hyde) / len(all_rec_hyde), 3)
    avg_lat_b = round(sum(all_lat_base) / len(all_lat_base), 1)
    avg_lat_h = round(sum(all_lat_hyde) / len(all_lat_hyde), 1)
    gain_mrr_tot = round(avg_mrr_h - avg_mrr_b, 3)
    gain_rec_tot = round(avg_rec_h - avg_rec_b, 3)

    lines += [
        "",
        f"| **Moy.** | — | **{avg_mrr_b:.3f}** | **{avg_mrr_h:.3f}** "
        f"| **{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f}** "
        f"| **{avg_rec_b:.3f}** | **{avg_rec_h:.3f}** "
        f"| **{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f}** |",
        "",
    ]

    # ── Tableau de synthèse des moyennes (format exercice) ──────────────
    pct_mrr = (gain_mrr_tot / avg_mrr_b * 100) if avg_mrr_b else 0
    pct_rec = (gain_rec_tot / avg_rec_b * 100) if avg_rec_b else 0
    lines += [
        "### Métriques agrégées\n",
        "| Métrique (moyenne 8 questions) | Baseline (question) | HyDE | Gain |",
        "|:-------------------------------|:--------------------:|:----:|:----:|",
        f"| **MRR@3** | {avg_mrr_b:.3f} | {avg_mrr_h:.3f} | "
        f"{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f} ({pct_mrr:+.1f}%) |",
        f"| **Recall@3** | {avg_rec_b:.3f} | {avg_rec_h:.3f} | "
        f"{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f} ({pct_rec:+.1f}%) |",
        f"| **Latence moyenne / requête (ms)** | {avg_lat_b:.0f} | {avg_lat_h:.0f} | "
        f"{avg_lat_h - avg_lat_b:+.0f} |",
        "",
    ]

    # ── Résultats détaillés par question ────────────────────────────────
    lines.append("## Résultats détaillés par question\n")

    for r in results:
        lines += [
            f"### {r['id']} — {r['question'][:70]}",
            "",
            f"**Question :** {r['question']}",
            "",
            f"**Hypothèse HyDE :** {r['hypothese']}",
            "",
            f"**MRR@3 baseline :** {r['mrr_brut']:.3f}  |  "
            f"**MRR@3 HyDE :** {r['mrr_hyde']:.3f}  |  "
            f"**Recall@3 baseline :** {r['recall_brut']:.3f}  |  "
            f"**Recall@3 HyDE :** {r['recall_hyde']:.3f}",
            "",
            f"**Latence baseline :** {r['latence_brut_ms']:.0f} ms  |  "
            f"**Latence HyDE :** {r['latence_hyde_ms']:.0f} ms",
            "",
            "#### Top-10 (baseline — question brute)",
            "",
            "| Rang | Pertinent | Titre | Catégorie | Score |",
            "|:---:|:---------:|:------|:----------|:----:|",
        ]
        for ci, c in enumerate(r["chunks_brut"]):
            flag = "🟢" if c["pertinent"] else "🔴"
            lines.append(
                f"| {ci + 1} | {flag} | **{c['titre']}** | {c['categorie']} | {c.get('score', '—')} |"
            )

        lines += [
            "",
            "#### Top-10 (HyDE)",
            "",
            "| Rang | Pertinent | Titre | Catégorie | Score |",
            "|:---:|:---------:|:------|:----------|:----:|",
        ]
        for ci, c in enumerate(r["chunks_hyde"]):
            flag = "🟢" if c["pertinent"] else "🔴"
            lines.append(
                f"| {ci + 1} | {flag} | **{c['titre']}** | {c['categorie']} | {c.get('score', '—')} |"
            )

        lines += ["", "---", ""]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation HyDE Facilito")
    parser.add_argument("--output", default=None,
                        help="Chemin du rapport (défaut: reports/report_hyde_YYYYMMDD_HHMMSS.md)")
    parser.add_argument("--ids", default=None,
                        help="IDs de questions à exécuter, séparés par des virgules (ex: Q1,Q3)")
    args = parser.parse_args()

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
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"report_hyde_{timestamp}.md"

    global_start = time.time()
    results = []

    for q in questions:
        qid = q["id"]
        question = q["question"]
        criteres = q["criteres"]
        print(f"\n[{qid}] {question[:70]}…")

        # ── 1. Baseline : question brute → embedding → RAG top-10 ──────
        t0 = time.time()
        emb_question = embed(question)
        raw_brut = search_rag_chroma(emb_question, k=10)
        lat_brut = (time.time() - t0) * 1000
        chunks_brut = _build_chunks(raw_brut, q)
        mrr_b, rec_b, flags_b, _ = _rag_metrics(chunks_brut, q)
        n_rel_b = sum(flags_b)
        print(f"  Baseline  ({lat_brut:.0f}ms): {len(chunks_brut)} chunks, "
              f"{n_rel_b} pert. — MRR@3={mrr_b:.3f} Rec@3={rec_b:.3f}")

        # ── 2. HyDE : générer hypothèse → embedding → RAG top-10 ───────
        t0 = time.time()
        hypothese = ""
        raw_hyde = []
        try:
            hypothese = generer_hypothese(question)
            emb_hypo = embed(hypothese)
            raw_hyde = search_rag_chroma(emb_hypo, k=10)
        except Exception as exc:
            print(f"  HyDE error: {exc}")
        lat_hyde = (time.time() - t0) * 1000

        chunks_hyde = _build_chunks(raw_hyde, q) if raw_hyde else []
        mrr_h, rec_h, flags_h, _ = _rag_metrics(chunks_hyde, q) if chunks_hyde else (0.0, 0.0, [], [])
        n_rel_h = sum(flags_h) if flags_h else 0
        print(f"  HyDE      ({lat_hyde:.0f}ms): {len(chunks_hyde)} chunks, "
              f"{n_rel_h} pert. — MRR@3={mrr_h:.3f} Rec@3={rec_h:.3f}")

        results.append({
            "id": qid,
            "question": question,
            "criteres": criteres,
            "hypothese": hypothese,
            "chunks_brut": chunks_brut,
            "chunks_hyde": chunks_hyde,
            "mrr_brut": mrr_b,
            "mrr_hyde": mrr_h,
            "recall_brut": rec_b,
            "recall_hyde": rec_h,
            "latence_brut_ms": lat_brut,
            "latence_hyde_ms": lat_hyde,
        })

    total_duration = time.time() - global_start
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_s": total_duration,
    }

    report_md = build_report(results, meta)
    output_path.write_text(report_md, encoding="utf-8")
    print(f"\nRapport : {output_path}")


if __name__ == "__main__":
    main()

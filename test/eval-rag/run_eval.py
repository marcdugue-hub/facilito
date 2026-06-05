"""
Évaluation du RAG Facilito — compare requêtes brutes vs reformulées.

Pour chaque question :
  1. RAG TOP-10 (brute) → vecteur pertinence → MRR@3, Recall@3
  2. Reformulation LLM (gpt-4o-mini) → RAG TOP-10 → MRR@3, Recall@3
  3. Agent → réponse → juge LLM (pertinence / fidélité / cohérence)

Usage :
  python test/eval-rag/run_eval.py
  python test/eval-rag/run_eval.py --deepseek
  python test/eval-rag/run_eval.py --ids Q1,Q3
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from metrics import est_pertinent, mrr_at_k, recall_at_k

# ── Paths ──────────────────────────────────────────────────────────────────────
ENV_FILE = Path(__file__).resolve().parents[2] / "Agent" / ".env"
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
REPORTS_DIR = Path(__file__).parent / "reports"

load_dotenv(ENV_FILE)

# ── Query rewriting ────────────────────────────────────────────────────────────
_rewrite_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def rewrite_query(question: str) -> str:
    r = _rewrite_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=100,
        messages=[
            {
                "role": "system",
                "content": (
                    "Reformule la question pour optimiser une recherche "
                    "de pratiques de facilitation d'ateliers collaboratifs. "
                    "Utilise des termes techniques précis (type de pratique, "
                    "phase d'atelier, objectif, nombre de participants, durée, "
                    "catégorie). Réponds UNIQUEMENT la question reformulée, "
                    "sans préfixe ni ponctuation superflue."
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    return r.choices[0].message.content.strip()


# ── Judge prompt ───────────────────────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """Tu es un évaluateur expert en facilitation d'ateliers.

Tu analyses la réponse d'un agent IA qui recommande des pratiques de facilitation.
Pour chaque dimension activée, attribue un score de 1 à 5 :
  1 — Complètement inadéquat
  2 — Insuffisant
  3 — Acceptable mais incomplet
  4 — Bon
  5 — Excellent

Critères :
  • pertinence  : Les pratiques recommandées sont-elles adaptées au besoin
                  (objectif, taille du groupe, phase de l'atelier) ?
  • fidelite    : Les détails donnés sont-ils exacts (durée, participants, déroulé) ?
  • coherence   : La réponse est-elle claire, bien structurée et logique ?

Réponds UNIQUEMENT avec ce JSON :
{"pertinence": <1-5 ou null>, "fidelite": <1-5 ou null>, "coherence": <1-5 ou null>,
 "justification": "<2-3 phrases en français>"}"""

JUDGE_USER_TEMPLATE = """## Question
{question}

## Mots-clés attendus dans la réponse
La réponse devrait idéalement mentionner ces notions : {criteres}

## Dimensions à évaluer
- pertinence : true
- fidelite   : true
- coherence  : true

## Réponse de l'agent
{agent_reply}

Évalue la réponse."""


# ── Helpers ────────────────────────────────────────────────────────────────────
def score_emoji(score: float | None) -> str:
    if score is None:
        return "—"
    if score >= 4.0:
        return f"🟢 **{score:.1f}**"
    if score >= 3.0:
        return f"🟡 **{score:.1f}**"
    return f"🔴 **{score:.1f}**"


def mean_scores(scores: list[float | None]) -> float | None:
    valid = [s for s in scores if s is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


# ── API helpers ────────────────────────────────────────────────────────────────
def create_test_session(base_url: str, client: httpx.Client) -> tuple[int, int]:
    label = f"EVAL_RAG_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    r = client.post(f"{base_url}/api/facilitators", json={"name": label})
    r.raise_for_status()
    fac_id = r.json()["id"]
    r = client.post(f"{base_url}/api/sessions", json={
        "facilitator_id": fac_id,
        "title": label,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objective": "Session de test eval-rag — supprimable",
    })
    r.raise_for_status()
    return fac_id, r.json()["id"]


def delete_session(base_url: str, client: httpx.Client, session_id: int) -> None:
    try:
        client.delete(f"{base_url}/api/sessions/{session_id}")
    except Exception:
        pass


def search_rag(base_url: str, client: httpx.Client, query: str, k: int = 10) -> list[dict]:
    r = client.get(f"{base_url}/api/practices/search", params={"q": query, "n": k})
    r.raise_for_status()
    return r.json()


def ask_agent(base_url: str, client: httpx.Client, session_id: int, message: str) -> str:
    r = client.post(
        f"{base_url}/api/agent/chat",
        json={"session_id": session_id, "message": message},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json().get("reply", "")


# ── Judge LLM ──────────────────────────────────────────────────────────────────
def build_judge_client(provider: str) -> tuple[object, str]:
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            sys.exit("DEEPSEEK_API_KEY manquant dans Agent/.env")
        oc = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        model = "deepseek-chat"
    else:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            sys.exit("OPENAI_API_KEY manquant dans Agent/.env")
        oc = OpenAI(api_key=api_key)
        model = "gpt-4o"
    return oc, model


def judge_response(oc, model: str, question: str, criteres: list[str], agent_reply: str) -> dict:
    user_msg = JUDGE_USER_TEMPLATE.format(
        question=question,
        criteres=", ".join(criteres),
        agent_reply=agent_reply,
    )
    completion = oc.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    return {
        "pertinence": data.get("pertinence"),
        "fidelite": data.get("fidelite"),
        "coherence": data.get("coherence"),
        "justification": data.get("justification", ""),
    }


# ── Analyse RAG sur une requête ───────────────────────────────────────────────
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
def build_report(results: list[dict], meta: dict, provider: str, judge_model: str) -> str:
    now_str = meta["generated_at"]
    duration = meta["total_duration_s"]

    lines = [
        f"# Rapport d'évaluation RAG — Facilito\n",
        f"> Généré le **{now_str}**  |  Durée : **{duration:.1f}s**  |  "
        f"Provider : **{provider}**  |  Juge : **{judge_model}**\n",
        "## Comparaison requête brute vs reformulée\n",
        "| # | Brute | Reformulée | MRR@3 brut | MRR@3 rewrite | Gain MRR | "
        "Rec@3 brut | Rec@3 rewrite | Gain Rec |",
        "|:-:|:------|:-----------|:----------:|:--------------:|:--------:|"
        ":----------:|:--------------:|:--------:|",
    ]

    all_mrr_base, all_mrr_rewrite = [], []
    all_rec_base, all_rec_rewrite = [], []
    all_lat_base, all_lat_rewrite = [], []

    for r in results:
        all_mrr_base.append(r["mrr_brut"])
        all_mrr_rewrite.append(r["mrr_rewrite"])
        all_rec_base.append(r["recall_brut"])
        all_rec_rewrite.append(r["recall_rewrite"])
        all_lat_base.append(r["latence_brut_ms"])
        all_lat_rewrite.append(r["latence_rewrite_ms"])

        gain_mrr = r["mrr_rewrite"] - r["mrr_brut"]
        gain_rec = r["recall_rewrite"] - r["recall_brut"]
        gain_mrr_s = f"+{gain_mrr:.3f}" if gain_mrr >= 0 else f"{gain_mrr:.3f}"
        gain_rec_s = f"+{gain_rec:.3f}" if gain_rec >= 0 else f"{gain_rec:.3f}"

        lines.append(
            f"| {r['id']} "
            f"| {r['rewritten'][:50]}… "
            f"| {r['rewritten'][:50]}… "
            f"| {r['mrr_brut']:.3f} "
            f"| {r['mrr_rewrite']:.3f} "
            f"| {gain_mrr_s} "
            f"| {r['recall_brut']:.3f} "
            f"| {r['recall_rewrite']:.3f} "
            f"| {gain_rec_s} |"
        )

    avg_mrr_b = round(sum(all_mrr_base) / len(all_mrr_base), 3)
    avg_mrr_r = round(sum(all_mrr_rewrite) / len(all_mrr_rewrite), 3)
    avg_rec_b = round(sum(all_rec_base) / len(all_rec_base), 3)
    avg_rec_r = round(sum(all_rec_rewrite) / len(all_rec_rewrite), 3)
    avg_lat_b = round(sum(all_lat_base) / len(all_lat_base), 1)
    avg_lat_r = round(sum(all_lat_rewrite) / len(all_lat_rewrite), 1)
    gain_mrr_tot = round(avg_mrr_r - avg_mrr_b, 3)
    gain_rec_tot = round(avg_rec_r - avg_rec_b, 3)

    lines += [
        "",
        f"| **Moy.** | — | — | **{avg_mrr_b:.3f}** | **{avg_mrr_r:.3f}** "
        f"| **{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f}** "
        f"| **{avg_rec_b:.3f}** | **{avg_rec_r:.3f}** "
        f"| **{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f}** |",
        "",
    ]

    # ── Tableau de synthèse des moyennes ──────────────────────────
    pct_mrr = (gain_mrr_tot / avg_mrr_b * 100) if avg_mrr_b else 0
    pct_rec = (gain_rec_tot / avg_rec_b * 100) if avg_rec_b else 0
    lines += [
        "### Métriques agrégées\n",
        "| Métrique (moyenne 8 questions) | Question brute | Question reformulée | Gain |",
        "|:-------------------------------|:--------------:|:-------------------:|:----:|",
        f"| **MRR@3** | {avg_mrr_b:.3f} | {avg_mrr_r:.3f} | "
        f"{'+' if gain_mrr_tot >= 0 else ''}{gain_mrr_tot:.3f} ({pct_mrr:+.1f}%) |",
        f"| **Recall@3** | {avg_rec_b:.3f} | {avg_rec_r:.3f} | "
        f"{'+' if gain_rec_tot >= 0 else ''}{gain_rec_tot:.3f} ({pct_rec:+.1f}%) |",
        f"| **Latence moyenne / requête (ms)** | {avg_lat_b:.0f} | {avg_lat_r:.0f} | "
        f"{avg_lat_r - avg_lat_b:+.0f} |",
        "",
    ]

    # ── Scores juge ───────────────────────────────────────────────
    lines += [
        "### Scores juge (LLM-as-Judge)\n",
        "| # | Pertinence | Fidélité | Cohérence | Moyenne |",
        "|:-:|:----------:|:--------:|:---------:|:-------:|",
    ]
    all_judge = []
    for r in results:
        j_avg = mean_scores([r["scores"]["pertinence"], r["scores"]["fidelite"], r["scores"]["coherence"]])
        all_judge.append(j_avg)
        lines.append(
            f"| {r['id']} "
            f"| {score_emoji(r['scores']['pertinence'])} "
            f"| {score_emoji(r['scores']['fidelite'])} "
            f"| {score_emoji(r['scores']['coherence'])} "
            f"| {j_avg if j_avg else '—'} |"
        )
    valid_j = [m for m in all_judge if m is not None]
    global_mean = round(sum(valid_j) / len(valid_j), 2) if valid_j else 0.0
    lines += ["", f"> **Score juge moyen : {global_mean} / 5**", "", "---", ""]

    # ── Résultats détaillés ───────────────────────────────────────
    lines.append("## Résultats détaillés par question\n")

    for r in results:
        avg = mean_scores([r["scores"]["pertinence"], r["scores"]["fidelite"], r["scores"]["coherence"]])
        if avg is None:
            hdr_emoji = "⬜"
        elif avg >= 4.0:
            hdr_emoji = "🟢"
        elif avg >= 3.0:
            hdr_emoji = "🟡"
        else:
            hdr_emoji = "🔴"

        lines += [
            f"### {hdr_emoji} {r['id']} — {r['question'][:70]}",
            "",
            f"**Question :** {r['question']}",
            "",
            f"**Requête reformulée :** {r['rewritten']}",
            "",
            f"**MRR@3 brut :** {r['mrr_brut']:.3f}  |  "
            f"**MRR@3 rewrite :** {r['mrr_rewrite']:.3f}  |  "
            f"**Recall@3 brut :** {r['recall_brut']:.3f}  |  "
            f"**Recall@3 rewrite :** {r['recall_rewrite']:.3f}",
            "",
            f"**Latence brute :** {r['latence_brut_ms']:.0f} ms  |  "
            f"**Latence rewrite :** {r['latence_rewrite_ms']:.0f} ms",
            "",
            "#### Top-10 (requête brute)",
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
            "#### Top-10 (requête reformulée)",
            "",
            "| Rang | Pertinent | Titre | Catégorie | Score |",
            "|:---:|:---------:|:------|:----------|:----:|",
        ]

        for ci, c in enumerate(r["chunks_rewrite"]):
            flag = "🟢" if c["pertinent"] else "🔴"
            lines.append(
                f"| {ci + 1} | {flag} | **{c['titre']}** | {c['categorie']} | {c.get('score', '—')} |"
            )

        lines += [
            "",
            "#### Réponse de l'agent",
            "",
            r["agent_reply"],
            "",
            "#### Évaluation du juge",
            f"- **Pertinence** : {score_emoji(r['scores']['pertinence'])}",
            f"- **Fidélité** : {score_emoji(r['scores']['fidelite'])}",
            f"- **Cohérence** : {score_emoji(r['scores']['coherence'])}",
            f"- **Moyenne** : {avg if avg else '—'} / 5",
            "",
            f"*{r['scores']['justification']}*",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation RAG Facilito")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--openai", action="store_true", default=True,
                       help="Utiliser OpenAI comme juge (défaut)")
    group.add_argument("--deepseek", action="store_true",
                       help="Utiliser DeepSeek comme juge")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="URL du serveur Facilito (défaut: http://localhost:8000)")
    parser.add_argument("--output", default=None,
                        help="Chemin du rapport (défaut: reports/report_YYYYMMDD_HHMMSS.md)")
    parser.add_argument("--ids", default=None,
                        help="IDs de questions à exécuter, séparés par des virgules (ex: Q1,Q3)")
    args = parser.parse_args()

    provider = "deepseek" if args.deepseek else "openai"

    if not QUESTIONS_PATH.exists():
        sys.exit(f"Fichier introuvable : {QUESTIONS_PATH}")
    questions: list[dict] = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    if args.ids:
        id_filter = {s.strip() for s in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in id_filter]
        if not questions:
            sys.exit(f"Aucune question trouvée pour les IDs : {args.ids}")

    oc, judge_model = build_judge_client(provider)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"report_{timestamp}.md"

    global_start = time.time()

    with httpx.Client(timeout=30.0) as http:
        try:
            http.get(f"{args.base_url}/api/facilitators")
        except httpx.ConnectError:
            sys.exit(
                f"Impossible de joindre le serveur à {args.base_url}\n"
                "Démarrez-le avec : python -m Agent.Main.main --openai"
            )

        fac_id, session_id = create_test_session(args.base_url, http)
        print(f"Session de test — facilitator_id={fac_id}, session_id={session_id}")

        results = []
        for q in questions:
            qid = q["id"]
            question = q["question"]
            criteres = q["criteres"]
            print(f"\n[{qid}] {question[:70]}…")

            # ── 1. RAG brute (top-10) ────────────────────────────────────────
            t0 = time.time()
            try:
                raw_brut = search_rag(args.base_url, http, question, k=10)
            except Exception as exc:
                print(f"  RAG brut error: {exc}")
                raw_brut = []
            lat_brut = (time.time() - t0) * 1000
            chunks_brut = _build_chunks(raw_brut, q)
            mrr_b, rec_b, flags_b, _ = _rag_metrics(chunks_brut, q)
            n_rel_b = sum(flags_b)
            print(f"  RAG brut   ({lat_brut:.0f}ms): {len(chunks_brut)} chunks, "
                  f"{n_rel_b} pert. — MRR@3={mrr_b:.3f} Rec@3={rec_b:.3f}")

            # ── 2. Reformulation ──────────────────────────────────────────────
            t0 = time.time()
            rewritten = rewrite_query(question)
            lat_rw = (time.time() - t0) * 1000
            print(f"  Rewrite    ({lat_rw:.0f}ms): {rewritten[:80]}…")

            # ── 3. RAG reformulée (top-10) ───────────────────────────────────
            t0 = time.time()
            try:
                raw_rw = search_rag(args.base_url, http, rewritten, k=10)
            except Exception as exc:
                print(f"  RAG rewrite error: {exc}")
                raw_rw = []
            lat_rw_search = (time.time() - t0) * 1000
            chunks_rw = _build_chunks(raw_rw, q)
            mrr_r, rec_r, flags_r, _ = _rag_metrics(chunks_rw, q)
            n_rel_r = sum(flags_r)
            print(f"  RAG rewrite ({lat_rw_search:.0f}ms): {len(chunks_rw)} chunks, "
                  f"{n_rel_r} pert. — MRR@3={mrr_r:.3f} Rec@3={rec_r:.3f}")

            # ── 4. Agent ─────────────────────────────────────────────────────
            t0 = time.time()
            try:
                agent_reply = ask_agent(args.base_url, http, session_id, question)
            except Exception as exc:
                agent_reply = f"[ERREUR agent: {exc}]"
            agent_dur = time.time() - t0
            print(f"  Agent      ({agent_dur:.1f}s): {agent_reply[:80]}…")

            # ── 5. Juge ──────────────────────────────────────────────────────
            t0 = time.time()
            scores = judge_response(oc, judge_model, question, criteres, agent_reply)
            judge_dur = time.time() - t0
            avg_j = mean_scores([scores["pertinence"], scores["fidelite"], scores["coherence"]])
            print(f"  Juge       ({judge_dur:.1f}s): P={scores['pertinence']} "
                  f"F={scores['fidelite']} C={scores['coherence']} → {avg_j}")

            results.append({
                "id": qid,
                "question": question,
                "criteres": criteres,
                "rewritten": rewritten,
                "chunks_brut": chunks_brut,
                "chunks_rewrite": chunks_rw,
                "mrr_brut": mrr_b,
                "mrr_rewrite": mrr_r,
                "recall_brut": rec_b,
                "recall_rewrite": rec_r,
                "latence_brut_ms": lat_brut,
                "latence_rewrite_ms": lat_rw + lat_rw_search,
                "agent_reply": agent_reply,
                "scores": scores,
                "agent_duration_s": agent_dur,
                "judge_duration_s": judge_dur,
            })

        delete_session(args.base_url, http, session_id)
        print(f"\nSession {session_id} supprimée.")

    total_duration = time.time() - global_start
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_s": total_duration,
    }

    report_md = build_report(results, meta, provider, judge_model)
    output_path.write_text(report_md, encoding="utf-8")
    print(f"\nRapport : {output_path}")


if __name__ == "__main__":
    main()

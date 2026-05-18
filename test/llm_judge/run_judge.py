#!/usr/bin/env python3
"""
LLM-as-Judge evaluation script for the Facilito agent.

Usage:
    python test/llm_judge/run_judge.py [--openai|--deepseek] [--base-url URL]
                                       [--questions PATH] [--output PATH]
                                       [--ids 1,3,5]

The script:
  1. Creates a temporary facilitator + session via the API
  2. Sends each question to POST /api/agent/chat
  3. Asks a judge LLM to score the response on 1-5 for each enabled dimension
  4. Writes a Markdown report to test/llm_judge/reports/

Requires the Facilito server to be running (default: http://localhost:8000).
API keys are read from Agent/.env.
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

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / "Agent" / ".env"
QUESTIONS_DEFAULT = Path(__file__).parent / "questions.json"
REPORTS_DIR = Path(__file__).parent / "reports"

load_dotenv(ENV_FILE)

# ── Judge prompt ───────────────────────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """Tu es un évaluateur expert en facilitation d'ateliers collaboratifs.
Tu évalues la réponse d'un agent IA spécialisé dans la recommandation de pratiques de facilitation.

Pour chaque dimension activée, attribue un score entier de 1 à 5 :
  1 — Complètement inadéquat ou erroné
  2 — Insuffisant, problèmes majeurs
  3 — Acceptable mais incomplet ou imprécis
  4 — Bonne réponse avec légers défauts
  5 — Excellent, répond parfaitement aux attentes

Critères d'évaluation :
  • pertinence  : L'agent a-t-il recommandé des pratiques vraiment adaptées au besoin
                  (nombre de participants, durée, phase de l'atelier, objectif) ?
  • fidelite    : Les informations sur les pratiques sont-elles exactes ?
                  (durée, participants, catégorie, déroulé) — sans hallucination.
  • coherence   : La réponse est-elle bien structurée, logique et claire ?
                  L'agent gère-t-il correctement les cas hors-sujet ou ambigus ?

Réponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans texte autour) :
{
  "pertinence": <1-5 ou null si non évalué>,
  "fidelite":   <1-5 ou null si non évalué>,
  "coherence":  <1-5 ou null si non évalué>,
  "justification": "<explication concise en français, 2-3 phrases>"
}"""

JUDGE_USER_TEMPLATE = """## Question posée à l'agent
{question}

## Comportement attendu
{comportement_attendu}

## Dimensions à évaluer
- pertinence : {eval_pertinence}
- fidelite   : {eval_fidelite}
- coherence  : {eval_coherence}

## Réponse de l'agent
{agent_reply}

Évalue maintenant la réponse selon les dimensions activées (true = évaluer, false = mettre null)."""


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


def mean_emoji(score: float | None) -> str:
    if score is None:
        return "—"
    return f"**{score:.1f}**"


# ── API helpers ────────────────────────────────────────────────────────────────

def create_test_session(base_url: str, client: httpx.Client) -> tuple[int, int]:
    """Create a temporary facilitator and session; return (facilitator_id, session_id)."""
    label = f"LLM_JUDGE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    r = client.post(f"{base_url}/api/facilitators", json={"name": label})
    r.raise_for_status()
    fac_id = r.json()["id"]

    r = client.post(f"{base_url}/api/sessions", json={
        "facilitator_id": fac_id,
        "title": label,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objective": "Session de test LLM-as-Judge — supprimable",
    })
    r.raise_for_status()
    ses_id = r.json()["id"]

    return fac_id, ses_id


def delete_session(base_url: str, client: httpx.Client, session_id: int) -> None:
    try:
        client.delete(f"{base_url}/api/sessions/{session_id}")
    except Exception:
        pass


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
    """Return (openai_client, model_name) for the judge."""
    from openai import OpenAI

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


def judge_response(
    oc, model: str, q: dict, agent_reply: str
) -> dict:
    """Ask the judge LLM to score agent_reply; return scores dict."""
    user_msg = JUDGE_USER_TEMPLATE.format(
        question=q["question"],
        comportement_attendu=q["comportement_attendu"],
        eval_pertinence=q["eval_pertinence"],
        eval_fidelite=q["eval_fidelite"],
        eval_coherence=q["eval_coherence"],
        agent_reply=agent_reply,
    )

    completion = oc.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract JSON block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}

    return {
        "pertinence":    data.get("pertinence"),
        "fidelite":      data.get("fidelite"),
        "coherence":     data.get("coherence"),
        "justification": data.get("justification", ""),
    }


# ── Report generator ──────────────────────────────────────────────────────────

def build_report(
    results: list[dict],
    meta: dict,
    provider: str,
    judge_model: str,
) -> str:
    now_str = meta["generated_at"]
    duration = meta["total_duration_s"]

    lines = [
        f"# Rapport LLM-as-Judge — Agent Facilito\n",
        f"> Généré le **{now_str}**  |  Durée totale : **{duration:.1f} s**  |  "
        f"Provider agent : **{provider}**  |  Juge : **{judge_model}**\n",
        "## Tableau de synthèse\n",
        "| # | Catégorie | Pertinence | Fidélité | Cohérence | Moyenne |",
        "|:-:|:----------|:----------:|:--------:|:---------:|:-------:|",
    ]

    all_means = []
    for r in results:
        scores = [r["scores"]["pertinence"], r["scores"]["fidelite"], r["scores"]["coherence"]]
        avg = mean_scores(scores)
        all_means.append(avg)
        lines.append(
            f"| {r['id']} | {r['categorie']} "
            f"| {score_emoji(r['scores']['pertinence'])} "
            f"| {score_emoji(r['scores']['fidelite'])} "
            f"| {score_emoji(r['scores']['coherence'])} "
            f"| {mean_emoji(avg)} |"
        )

    valid_means = [m for m in all_means if m is not None]
    global_mean = round(sum(valid_means) / len(valid_means), 2) if valid_means else 0.0
    lines += [
        "",
        f"> **Score global moyen : {global_mean} / 5**",
        "",
        "---",
        "",
        "## Résultats détaillés par question",
        "",
    ]

    emoji_map = {
        (True, True, True): "🟢",
        (False, False, False): "⬜",
    }

    for r in results:
        scores = r["scores"]
        avg = mean_scores([scores["pertinence"], scores["fidelite"], scores["coherence"]])
        avg_str = f"{avg:.1f}" if avg is not None else "—"

        # Section header with global score colour
        if avg is None:
            hdr_emoji = "⬜"
        elif avg >= 4.0:
            hdr_emoji = "🟢"
        elif avg >= 3.0:
            hdr_emoji = "🟡"
        else:
            hdr_emoji = "🔴"

        lines += [
            f"### {hdr_emoji} {r['id']}. {r['categorie']}",
            "",
            f"**Durée agent :** {r['agent_duration_s']:.2f} s  |  "
            f"**Durée juge :** {r['judge_duration_s']:.2f} s",
            "",
            "**Question :**",
            f"> {r['question']}",
            "",
            "**Comportement attendu :**",
            f"> {r['comportement_attendu']}",
            "",
            "**Réponse de l'agent :**",
            "",
            r["agent_reply"],
            "",
            "**Évaluation du juge :**",
            "",
        ]

        score_rows = []
        dim_labels = [
            ("Pertinence", "pertinence", r["q"]["eval_pertinence"]),
            ("Fidélité",   "fidelite",   r["q"]["eval_fidelite"]),
            ("Cohérence",  "coherence",  r["q"]["eval_coherence"]),
        ]
        for label, key, enabled in dim_labels:
            if enabled:
                score_rows.append(f"- **{label}** : {score_emoji(scores[key])}")
            else:
                score_rows.append(f"- **{label}** : *(non évalué)*")

        lines += score_rows
        lines += [
            f"- **Moyenne** : {avg_str} / 5",
            "",
            f"*{scores['justification']}*",
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-Judge pour Facilito")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--openai",    action="store_true", default=True,
                       help="Utiliser OpenAI GPT-4o comme juge (défaut)")
    group.add_argument("--deepseek",  action="store_true",
                       help="Utiliser DeepSeek comme juge")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="URL de base du serveur Facilito (défaut: http://localhost:8000)")
    parser.add_argument("--questions", default=str(QUESTIONS_DEFAULT),
                        help="Chemin vers le fichier questions.json")
    parser.add_argument("--output",   default=None,
                        help="Chemin du rapport de sortie (défaut: reports/report_YYYYMMDD_HHMMSS.md)")
    parser.add_argument("--ids",      default=None,
                        help="IDs de questions à exécuter, séparés par des virgules (ex: 1,3,5)")
    args = parser.parse_args()

    provider = "deepseek" if args.deepseek else "openai"

    # Load questions
    questions_path = Path(args.questions)
    if not questions_path.exists():
        sys.exit(f"Fichier introuvable : {questions_path}")
    questions: list[dict] = json.loads(questions_path.read_text(encoding="utf-8"))

    if args.ids:
        id_filter = {int(i.strip()) for i in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in id_filter]
        if not questions:
            sys.exit(f"Aucune question trouvée pour les IDs : {args.ids}")

    # Build judge client
    oc, judge_model = build_judge_client(provider)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"report_{timestamp}.md"

    global_start = time.time()

    with httpx.Client(timeout=30.0) as http:
        # Verify server is reachable
        try:
            http.get(f"{args.base_url}/api/facilitators")
        except httpx.ConnectError:
            sys.exit(
                f"Impossible de joindre le serveur à {args.base_url}\n"
                "Démarrez-le avec : python -m Agent.Main.main --openai"
            )

        fac_id, session_id = create_test_session(args.base_url, http)
        print(f"Session de test créée — facilitator_id={fac_id}, session_id={session_id}")

        results = []
        for q in questions:
            print(f"\n[Q{q['id']:02d}] {q['categorie']} — {q['question'][:60]}…")

            # Ask the agent
            t0 = time.time()
            try:
                agent_reply = ask_agent(args.base_url, http, session_id, q["question"])
            except Exception as exc:
                agent_reply = f"[ERREUR agent: {exc}]"
            agent_dur = time.time() - t0
            print(f"  Agent ({agent_dur:.1f}s): {agent_reply[:80]}…")

            # Judge evaluation
            t0 = time.time()
            scores = judge_response(oc, judge_model, q, agent_reply)
            judge_dur = time.time() - t0

            avg = mean_scores([scores["pertinence"], scores["fidelite"], scores["coherence"]])
            print(f"  Juge  ({judge_dur:.1f}s): P={scores['pertinence']} F={scores['fidelite']} C={scores['coherence']} → {avg}")

            results.append({
                "id": q["id"],
                "categorie": q["categorie"],
                "question": q["question"],
                "comportement_attendu": q["comportement_attendu"],
                "agent_reply": agent_reply,
                "scores": scores,
                "agent_duration_s": agent_dur,
                "judge_duration_s": judge_dur,
                "q": q,
            })

        # Cleanup test session
        delete_session(args.base_url, http, session_id)
        print(f"\nSession de test {session_id} supprimée.")

    total_duration = time.time() - global_start
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_s": total_duration,
    }

    report_md = build_report(results, meta, provider, judge_model)
    output_path.write_text(report_md, encoding="utf-8")
    print(f"\nRapport généré : {output_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Benchmark de coût du routage — compare avec et sans cascade.
Génère un rapport Markdown sur le même modèle que LLM-as-Judge.

Usage:
    python -m Agent.Main.main --openai          (terminal 1)
    python test/routing_benchmark/benchmark_routing.py
    python test/routing_benchmark/benchmark_routing.py --base-url http://localhost:8001

Pricing utilisé :
    gpt-4o-mini / deepseek-chat     : $0.15 / 1M input  — $0.60 / 1M output
    gpt-4o      / deepseek-reasoner : $2.50 / 1M input  — $10.00 / 1M output
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

QUESTIONS = [
    {"id": 1,  "type": "simple",  "question": "Bonjour"},
    {"id": 2,  "type": "simple",  "question": "Liste les sessions"},
    {"id": 3,  "type": "simple",  "question": "Quels sont les horaires de la session ?"},
    {"id": 4,  "type": "simple",  "question": "Liste les participants"},
    {"id": 5,  "type": "simple",  "question": "Quelle est la durée totale de la session ?"},
    {"id": 6,  "type": "simple",  "question": "Cherche un icebreaker"},
    {"id": 7,  "type": "simple",  "question": "C'est quoi le design thinking ?"},
    {"id": 8,  "type": "simple",  "question": "Combien de participants max peut-on avoir ?"},
    {"id": 9,  "type": "complex", "question": "Analyse le contenu de la session et suggère des améliorations"},
    {"id": 10, "type": "complex", "question": "Conçois une session complète sur l'innovation avec 4 pratiques"},
    {"id": 11, "type": "complex", "question": "Crée un atelier de team building de 3h avec ouverture, exercice principal et closing"},
    {"id": 12, "type": "complex", "question": "Planifie une formation aux OKR sur 2 jours avec 6 pratiques"},
    {"id": 13, "type": "complex", "question": "Compare les pratiques de brainstorming disponibles et recommande la meilleure pour mon objectif"},
    {"id": 14, "type": "complex", "question": "Reconception complète de la session actuelle avec une nouvelle structure"},
    {"id": 15, "type": "complex", "question": "Analyse les forces et faiblesses du déroulé actuel et propose des alternatives"},
]

PRICING = {
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
    "deepseek-chat":     {"input": 0.15,  "output": 0.60},
    "deepseek-reasoner": {"input": 2.50,  "output": 10.00},
}


def _extract_model(payload_str: str) -> str | None:
    try:
        return json.loads(payload_str).get("model")
    except Exception:
        return None


def _cost_emoji(cost: float, threshold_cheap: float = 0.05, threshold_moderate: float = 0.20) -> str:
    if cost <= threshold_cheap:
        return "🟢"
    if cost <= threshold_moderate:
        return "🟡"
    return "🔴"


def ask_agent(base_url: str, client: httpx.Client, session_id: int, message: str, timeout: float = 120.0) -> dict:
    r = client.post(
        f"{base_url}/api/agent/chat",
        json={"session_id": session_id, "message": message},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def read_events_for_session(session_id: int) -> list[dict]:
    from Agent.Tools.Database.analytics import get_logs
    raw = get_logs(types=["llm"], limit=500)
    return [e for e in raw if e["session_id"] == session_id]


def create_test_session(base_url: str, client: httpx.Client) -> dict:
    label = f"BENCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    r = client.post(f"{base_url}/api/facilitators", json={"name": label})
    r.raise_for_status()
    fac = r.json()

    r = client.post(f"{base_url}/api/sessions", json={
        "facilitator_id": fac["id"],
        "title": "Session Benchmark Routage",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "start_time": "09:00",
        "objective": "Session de test pour le benchmark du routage",
    })
    r.raise_for_status()
    ses = r.json()
    ses_id = ses["id"]

    participants = [
        {"first_name": "Alice", "last_name": "Martin", "email": "alice@test.com", "role": "Facilitateur"},
        {"first_name": "Bob", "last_name": "Durand", "email": "bob@test.com", "role": "Participant"},
        {"first_name": "Claire", "last_name": "Petit", "email": "claire@test.com", "role": "Participant"},
        {"first_name": "David", "last_name": "Leroy", "email": "david@test.com", "role": "Observateur"},
    ]
    for p in participants:
        client.post(f"{base_url}/api/sessions/{ses_id}/participants", json=p).raise_for_status()

    r = client.post(f"{base_url}/api/clients", json={"name": "Acme Corp"})
    r.raise_for_status()
    client_data = r.json()
    r = client.post(f"{base_url}/api/teams", json={"name": "Équipe Innovation", "client_id": client_data["id"]})
    r.raise_for_status()
    team = r.json()
    for p in participants[:2]:
        client.post(f"{base_url}/api/teams/{team['id']}/participants",
                     json={"first_name": p["first_name"], "last_name": p["last_name"]}).raise_for_status()

    return {"facilitator": fac, "session": ses}


def delete_test_data(base_url: str, client: httpx.Client, facilitator_id: int, session_id: int) -> None:
    for sid in [session_id]:
        try:
            client.delete(f"{base_url}/api/sessions/{sid}")
        except Exception:
            pass
    try:
        client.delete(f"{base_url}/api/facilitators/{facilitator_id}")
    except Exception:
        pass


# ── Report generator (style LLM-as-Judge) ─────────────────────────────────────

def build_report(results: list[dict], meta: dict) -> str:
    total_4o_calls = meta["total_4o_calls"]
    total_mini_calls = meta["total_mini_calls"]
    cost_routing = meta["cost_routing"]
    cost_without = meta["cost_without"]
    economy = meta["economy"]
    avg_latency = meta["avg_latency"]

    total_ok = sum(1 for r in results if not r.get("error"))
    simple_ok = sum(1 for r in results if r["type"] == "simple" and not r.get("error"))
    complex_ok = sum(1 for r in results if r["type"] == "complex" and not r.get("error"))

    lines = [
        f"# Rapport Benchmark Routage — Facilito\n",
        f"> Généré le **{meta['generated_at']}**  |  "
        f"Durée totale : **{meta['total_duration_s']:.1f} s**  |  "
        f"Questions : **{total_ok}** ({simple_ok} simples, {complex_ok} complexes)  |  "
        f"Provider : **{meta['mode']}**\n",
        "## Prix utilisés\n",
        "| Modèle | Input ($/1M tokens) | Output ($/1M tokens) |",
        "|:-------|:-------------------:|:--------------------:|",
        "| `gpt-4o-mini` | 0.15 | 0.60 |",
        "| `gpt-4o` | 2.50 | 10.00 |\n",
        "## Comparaison avec / sans routage\n",
        "| Scénario | Appels GPT-4o | Appels GPT4o-mini | Coût total ($) | Latence moy. (ms) |",
        "|:---------|:-------------:|:-----------------:|:---------------:|:-----------------:|",
        f"| **Avec routage** | {total_4o_calls} | {total_mini_calls} | {cost_routing:.5f} | {avg_latency} |",
        f"| **Sans routage** | {total_4o_calls + total_mini_calls} | 0 | {cost_without:.5f} | N/A |",
        f"| **Économie (%)** | — | — | **{economy:.1f}%** | — |\n",
        f"> **Coût évité : ${cost_without - cost_routing:.5f}**  |  "
        f"**Économie relative : {economy:.1f}%**\n",
        "---\n",
        "## Résultats détaillés par question\n",
    ]

    for r in results:
        error = r.get("error")
        q_id = r["id"]
        q_type = r["type"]
        q_text = r["question"]
        duration_s = r.get("duration_ms", 0) / 1000
        complexite = r.get("complexite") or "?"
        categorie = r.get("categorie") or "?"
        agent_reply = r.get("reply", "") or ""

        # Compute per-question stats
        events = r.get("events", [])
        n_calls = len([e for e in events if e.get("tokens_in", 0) > 0])
        t_in = sum(e.get("tokens_in", 0) or 0 for e in events)
        t_out = sum(e.get("tokens_out", 0) or 0 for e in events)

        models = sorted(set(
            m for e in events
            if (m := _extract_model(e.get("payload", "{}")))
        ))
        models_str = ", ".join(models) if models else "—"

        # Compute cost for this question
        cost_q = 0.0
        for e in events:
            m = _extract_model(e.get("payload", "{}"))
            p = PRICING.get(m)
            if p:
                cost_q += (e.get("tokens_in", 0) or 0) * p["input"] / 1_000_000
                cost_q += (e.get("tokens_out", 0) or 0) * p["output"] / 1_000_000

        cost_q_without = (t_in * 2.50 + t_out * 10.00) / 1_000_000
        economy_q = ((cost_q_without - cost_q) / cost_q_without * 100) if cost_q_without > 0 else 0

        if error:
            emoji = "🔴"
        elif complexite == "complex" or complexite == "complexe":
            emoji = "🟠"
        else:
            emoji = "🟢"

        lines += [
            f"### {emoji} Q{q_id:02d}. {q_type}{' — ERREUR' if error else ''}\n",
            f"**Question :**",
            f"> {q_text}",
            "",
        ]

        if error:
            lines += [
                f"**Erreur :** `{error}`\n",
                "---\n",
            ]
            continue

        lines += [
            f"**Durée :** {duration_s:.1f} s  |  "
            f"**Appels LLM :** {n_calls}  |  "
            f"**Complexité :** {complexite}  |  "
            f"**Catégorie :** {categorie}\n",
            "**Tokens utilisés :**",
            f"- Input : **{t_in:,}**  |  Output : **{t_out:,}**  |  Total : **{t_in + t_out:,}**",
            "",
            f"**Modèles utilisés :** {models_str}",
            "",
            f"**Coût de la question :** ${cost_q:.5f} "
            f"(_sans routage : ${cost_q_without:.5f}_, "
            f"économie : **{economy_q:.1f}%**)",
            "",
        ]

        if agent_reply:
            preview = agent_reply[:600]
            if len(agent_reply) > 600:
                preview += "…"
            lines += [
                "**Réponse de l'agent :**",
                "",
                preview,
                "",
            ]

        lines.append("---\n")

    # Cost breakdown summary
    total_t_in = meta["total_tokens_in"]
    total_t_out = meta["total_tokens_out"]
    lines += [
        "## Bilan des coûts\n",
        f"**Avec routage :** ${cost_routing:.5f}",
        f"  - GPT-4o : {total_4o_calls} appels",
        f"  - GPT-4o-mini : {total_mini_calls} appels",
        "",
        f"**Sans routage :** ${cost_without:.5f} (simulation : tous les tokens au tarif GPT-4o)",
        "",
        f"**Tokens totaux :** {total_t_in + total_t_out:,} "
        f"({total_t_in:,} in, {total_t_out:,} out)",
        "",
        f"> **Économie réalisée : {economy:.1f}%**  "
        f"(soit ${cost_without - cost_routing:.5f} économisés)\n",
        f"*Rapport généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark coût du routage Facilito")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="URL du serveur Facilito (défaut: http://localhost:8000)")
    args = parser.parse_args()

    print("=" * 70)
    print("  Benchmark de routage — Facilito")
    print("=" * 70)

    with httpx.Client(timeout=30.0) as http:
        try:
            http.get(f"{args.base_url}/api/facilitators")
        except httpx.ConnectError:
            sys.exit(f"Impossible de joindre le serveur à {args.base_url}\n"
                     "Lancez : python -m Agent.Main.main --openai")

        test_data = create_test_session(args.base_url, http)
        ses_id = test_data["session"]["id"]
        fac_id = test_data["facilitator"]["id"]
        print(f"\nSession de test créée — session_id={ses_id}")

        results = []
        for q in QUESTIONS:
            label = f"[Q{q['id']:02d}] ({q['type']:>8}) {q['question'][:70]}"
            print(f"\n{label}")
            sys.stdout.flush()

            t0 = time.time()
            try:
                resp = ask_agent(args.base_url, http, ses_id, q["question"])
            except Exception as exc:
                print(f"  ERREUR: {exc}")
                results.append({
                    **q,
                    "duration_ms": 0, "events": [],
                    "error": str(exc), "complexite": None,
                    "categorie": None, "reply": None,
                })
                continue

            elapsed_ms = int((time.time() - t0) * 1000)
            events = read_events_for_session(ses_id)

            results.append({
                **q,
                "duration_ms": elapsed_ms,
                "events": events,
                "complexite": resp.get("complexite"),
                "categorie": resp.get("categorie"),
                "reply": resp.get("reply", ""),
            })

            print(f"  → {elapsed_ms}ms  |  complexité={resp.get('complexite')}  |  {len(events)} événements LLM")

        delete_test_data(args.base_url, http, fac_id, ses_id)
        print(f"\nDonnées de test nettoyées.")

    # ── Aggregation ────────────────────────────────────────────────────────────
    total_mini_calls = 0
    total_4o_calls = 0
    total_mini_t_in = 0
    total_mini_t_out = 0
    total_4o_t_in = 0
    total_4o_t_out = 0
    all_durations = []

    for r in results:
        durations = [e.get("duration_ms", 0) or 0 for e in r["events"]]
        all_durations.append(sum(durations) / len(durations) if durations else 0)

        for e in r["events"]:
            model = _extract_model(e.get("payload", "{}"))
            t_in = e.get("tokens_in", 0) or 0
            t_out = e.get("tokens_out", 0) or 0
            if model and "mini" in model.lower():
                total_mini_calls += 1
                total_mini_t_in += t_in
                total_mini_t_out += t_out
            else:
                total_4o_calls += 1
                total_4o_t_in += t_in
                total_4o_t_out += t_out

    cost_mini = (total_mini_t_in * 0.15 + total_mini_t_out * 0.60) / 1_000_000
    cost_4o = (total_4o_t_in * 2.50 + total_4o_t_out * 10.00) / 1_000_000
    cost_routing = cost_mini + cost_4o

    total_t_in = total_mini_t_in + total_4o_t_in
    total_t_out = total_mini_t_out + total_4o_t_out
    cost_without = (total_t_in * 2.50 + total_t_out * 10.00) / 1_000_000
    economy = ((cost_without - cost_routing) / cost_without * 100) if cost_without > 0 else 0
    avg_latency = round(sum(all_durations) / len(all_durations)) if all_durations else 0

    # ── Console output ────────────────────────────────────────────────────────
    total_ok = sum(1 for r in results if not r.get("error"))
    simple_ok = sum(1 for r in results if r["type"] == "simple" and not r.get("error"))
    complex_ok = sum(1 for r in results if r["type"] == "complex" and not r.get("error"))

    print("\n" + "=" * 70)
    print("  RÉSULTATS")
    print("=" * 70)
    print(f"\nQuestions traitées : {total_ok} ({simple_ok} simples, {complex_ok} complexes)")
    print()
    print(f"| {'Scénario':<20} | {'GPT-4o':<8} | {'GPT4o-mini':<11} | {'Coût ($)':<10} | {'Latence (ms)':<13} |")
    print("|-" + "-"*18 + "-|-" + "-"*6 + "-|-" + "-"*9 + "-|-" + "-"*8 + "-|-" + "-"*11 + "-|")
    print(f"| {'Avec routage':<20} | {total_4o_calls:<8} | {total_mini_calls:<11} | {cost_routing:<8.5f} | {avg_latency:<11} |")
    print(f"| {'Sans routage':<20} | {total_4o_calls + total_mini_calls:<8} | {'0':<11} | {cost_without:<8.5f} | {'N/A':<11} |")
    print(f"| {'Économie (%)':<20} | {'—':<8} | {'—':<11} | {economy:<7.1f}% | {'—':<11} |")
    print()
    print(f"Coût total AVEC  routage : ${cost_routing:.5f}")
    print(f"Coût total SANS  routage : ${cost_without:.5f}")
    print(f"Économie réalisée        : {economy:.1f}%")

    # ── Report ────────────────────────────────────────────────────────────────
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_s": 0,
        "mode": "openai",
        "total_4o_calls": total_4o_calls,
        "total_mini_calls": total_mini_calls,
        "cost_routing": cost_routing,
        "cost_without": cost_without,
        "economy": economy,
        "avg_latency": avg_latency,
        "total_tokens_in": total_t_in,
        "total_tokens_out": total_t_out,
    }

    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"benchmark_{timestamp}.md"

    report_md = build_report(results, meta)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\nRapport sauvegardé : {report_path}")


if __name__ == "__main__":
    main()

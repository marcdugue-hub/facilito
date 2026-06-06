"""PDF export: renders session as HTML then converts via weasyprint."""


def _add_minutes(hhmm: str, mins: int) -> str:
    h, m = map(int, hhmm.split(":"))
    t = h * 60 + m + mins
    return f"{(t // 60) % 24:02d}:{t % 60:02d}"


def render_pdf_html(ctx: dict) -> str:
    participants = ctx.get("participants", [])
    practices = ctx.get("practices", [])
    total = ctx.get("total_duration", 0)
    facilitator = ctx.get("facilitator", {})
    start_time = ctx.get("start_time")

    status_labels = {"draft": "Brouillon", "confirmed": "Confirmé", "finished": "Terminé"}
    status_label = status_labels.get(ctx.get("status", "draft"), ctx.get("status", "draft"))

    rows = ""
    cursor = start_time
    for p in practices:
        if cursor:
            slot_end = _add_minutes(cursor, p["duration_minutes"])
            time_cell = f"<td class='tc'>{cursor}</td><td class='tc'>{slot_end}</td>"
            cursor = slot_end
        else:
            time_cell = "<td class='tc'>—</td><td class='tc'>—</td>"
        src = p.get("source", "rag")
        badge_cls = "badge-sp" if src == "special" else "badge-rag"
        badge_lbl = p.get("icone_code") or ("Spécial" if src == "special" else "RAG")
        rows += (
            f"<tr><td>{p['titre']} <span class='badge {badge_cls}'>{badge_lbl}</span></td>"
            f"<td class='dur'>{p['duration_minutes']} min</td>{time_cell}</tr>\n"
        )

    def _p_role(p):
        role = p.get("role")
        return f" <span class='role'>— {role}</span>" if role else ""

    p_list = "".join(
        f"<li>{p['first_name']} {p['last_name']}{_p_role(p)}</li>\n"
        for p in participants
    )

    timing_html = ""
    if start_time:
        timing_html = (
            f"<span>Début : <strong>{start_time}</strong></span>"
            f"<span>Fin estimée : <strong>{_add_minutes(start_time, total)}</strong></span>"
        )

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: Arial, Helvetica, sans-serif; padding: 36px 44px; color: #01031B; background: #fff; font-size: 13px; line-height: 1.55; }}
h1 {{ font-size: 22px; font-weight: 700; color: #01031B; margin-bottom: 3px; }}
.pink {{ color: #D8346E; }}
.meta-bar {{ display: flex; flex-wrap: wrap; gap: 6px 24px; font-size: 12px; color: #6b6b80; margin: 10px 0 22px; padding: 10px 16px; background: #f7f7fb; border-radius: 8px; border-left: 4px solid #D8346E; }}
.meta-bar strong {{ color: #01031B; }}
.objective {{ font-style: italic; color: #6b6b80; margin-bottom: 20px; padding: 8px 16px; border-left: 3px solid #f2aac9; font-size: 12px; }}
h2 {{ color: #D8346E; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.7px; margin: 24px 0 8px; border-bottom: 2px solid #f2aac9; padding-bottom: 5px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ background: #fdf0f5; color: #D8346E; font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 10px; border-bottom: 2px solid #f2aac9; text-align: left; }}
th.tc {{ text-align: center; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #e2e2ee; vertical-align: middle; }}
tr:nth-child(even) td {{ background: #fafafa; }}
td.dur {{ text-align: center; color: #6b6b80; white-space: nowrap; }}
td.tc  {{ text-align: center; color: #D8346E; font-weight: 700; white-space: nowrap; }}
.badge {{ font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 6px; vertical-align: middle; display: inline-block; margin-left: 6px; }}
.badge-rag {{ background: #fdf0f5; color: #D8346E; }}
.badge-sp  {{ background: #f0fff4; color: #2c7a4b; }}
ul {{ padding-left: 20px; margin: 0; }}
li {{ padding: 3px 0; font-size: 12px; }}
.role {{ color: #6b6b80; }}
.footer {{ margin-top: 36px; padding-top: 10px; border-top: 1px solid #e2e2ee; font-size: 10px; color: #9ca3af; text-align: right; }}
</style>
</head><body>
<h1><span class="pink">‹</span> {ctx.get('title', 'Session')} <span class="pink">›</span></h1>
<div class="meta-bar">
  <span>Facilitateur : <strong>{facilitator.get('name', '')}</strong></span>
  <span>Date : <strong>{ctx.get('date') or '—'}</strong></span>
  <span>Statut : <strong>{status_label}</strong></span>
  <span>Durée : <strong>{total} min</strong></span>
  {timing_html}
</div>
{"<p class='objective'>" + ctx.get('objective', '') + "</p>" if ctx.get('objective') else ""}
{"<h2>Participants</h2><ul>" + p_list + "</ul>" if participants else ""}
<h2>Déroulé</h2>
<table>
  <thead><tr><th>Pratique</th><th class="tc">Durée</th><th class="tc">Début</th><th class="tc">Fin</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="footer">Facilito — {ctx.get('date', '')}</p>
</body></html>"""

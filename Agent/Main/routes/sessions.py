"""Session REST routes."""

from fastapi import APIRouter, HTTPException, Response

from Agent.Tools.Database import sessions as db_ses
from Agent.Tools.pdf_export import render_pdf_html
from Agent.Main.models import SessionCreate, SessionUpdate

router = APIRouter(tags=["sessions"])


@router.post("/api/sessions", status_code=201)
def post_session(body: SessionCreate):
    return db_ses.create_session(body.facilitator_id, body.title, body.date, body.start_time, body.objective)


@router.get("/api/sessions/{sid}")
def get_session(sid: int):
    s = db_ses.get_session_context(sid)
    if not s:
        raise HTTPException(404)
    return s


@router.patch("/api/sessions/{sid}")
def patch_session(sid: int, body: SessionUpdate):
    s = db_ses.update_session(sid, **body.model_dump(exclude_none=True))
    if not s:
        raise HTTPException(404)
    return s


@router.delete("/api/sessions/{sid}")
def del_session(sid: int):
    db_ses.delete_session(sid)
    return {"ok": True}


@router.get("/api/sessions/{sid}/export/pdf")
def export_pdf(sid: int):
    from weasyprint import HTML as WP_HTML
    ctx = db_ses.get_session_context(sid)
    if not ctx:
        raise HTTPException(404)
    html = render_pdf_html(ctx)
    pdf_bytes = WP_HTML(string=html).write_pdf()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="session-{sid}.pdf"'},
    )

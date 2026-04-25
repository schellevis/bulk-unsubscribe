from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.action import Action, ActionKind, ActionStatus
from app.models.sender import Sender, SenderStatus
from app.services.unsubscribe import UnsubscribeMethods
from app.services.unsubscribe_exec import execute_one_click

router = APIRouter(tags=["unsubscribe"])
DbSession = Annotated[Session, Depends(get_db)]

Method = Literal["one_click", "http", "mailto"]


def _templates():
    from app.main import templates

    return templates


def _methods_for(sender: Sender) -> UnsubscribeMethods:
    one_click_url = (sender.unsubscribe_http or "").lower().startswith("https://")
    return UnsubscribeMethods(
        http_url=sender.unsubscribe_http,
        mailto_url=sender.unsubscribe_mailto,
        one_click=bool(sender.unsubscribe_one_click_post and one_click_url),
    )


@router.get("/senders/{sender_id}/unsubscribe", response_class=HTMLResponse)
def show_unsubscribe(
    sender_id: int,
    request: Request,
    db: DbSession,
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)
    methods = _methods_for(sender)
    return _templates().TemplateResponse(
        request,
        "fragments/unsubscribe_modal.html",
        {
            "sender": sender,
            "methods": methods,
            "recommended": methods.recommended(),
        },
    )


@router.post("/senders/{sender_id}/unsubscribe", response_class=HTMLResponse)
async def execute_unsubscribe(
    sender_id: int,
    request: Request,
    method: Annotated[Method, Query()],
    db: DbSession,
) -> HTMLResponse:
    sender = db.get(Sender, sender_id)
    if sender is None:
        raise HTTPException(status_code=404)

    detail = ""
    success = False
    kind = {
        "one_click": ActionKind.unsubscribe_one_click,
        "http": ActionKind.unsubscribe_http,
        "mailto": ActionKind.unsubscribe_mailto,
    }[method]

    if method == "one_click":
        one_click_url = (sender.unsubscribe_http or "").lower().startswith("https://")
        if not sender.unsubscribe_http or not sender.unsubscribe_one_click_post or not one_click_url:
            raise HTTPException(status_code=400, detail="One-click not available")
        result = await execute_one_click(sender.unsubscribe_http)
        success = result.success
        detail = result.detail
        if success:
            sender.status = SenderStatus.unsubscribed
    elif method == "http":
        if not sender.unsubscribe_http:
            raise HTTPException(status_code=400, detail="No HTTP link available")
        success = True
        detail = f"Opened in browser: {sender.unsubscribe_http}"
    else:  # mailto
        if not sender.unsubscribe_mailto:
            raise HTTPException(status_code=400, detail="No mailto link available")
        success = True
        detail = f"mailto link: {sender.unsubscribe_mailto}"

    db.add(
        Action(
            account_id=sender.account_id,
            sender_id=sender_id,
            kind=kind,
            status=ActionStatus.success if success else ActionStatus.failed,
            affected_count=1,
            detail=detail,
        )
    )
    db.commit()
    db.refresh(sender)

    return _templates().TemplateResponse(
        request,
        "fragments/unsubscribe_result.html",
        {
            "sender": sender,
            "method": method,
            "success": success,
            "detail": detail,
        },
    )

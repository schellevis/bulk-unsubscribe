from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.account import Account
from app.models.sender import Sender
from app.models.whitelist_rule import WhitelistKind, WhitelistRule
from app.services.whitelist import recompute_sender_statuses

router = APIRouter(prefix="/whitelist", tags=["whitelist"])
DbSession = Annotated[Session, Depends(get_db)]


def _templates():
    from app.main import templates

    return templates


@router.get("", response_class=HTMLResponse)
def list_rules(
    request: Request,
    db: DbSession,
    account_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    accounts = (
        db.execute(select(Account).order_by(Account.created_at)).scalars().all()
    )
    if account_id is None and accounts:
        account_id = accounts[0].id
    selected = db.get(Account, account_id) if account_id else None
    rules: list[WhitelistRule] = []
    affected: dict[int, int] = {}
    if selected:
        rules = list(
            db.scalars(
                select(WhitelistRule)
                .where(WhitelistRule.account_id == selected.id)
                .order_by(WhitelistRule.kind, WhitelistRule.value)
            )
        )
        for r in rules:
            if r.kind == WhitelistKind.sender:
                cnt = (
                    db.scalar(
                        select(func.count(Sender.id)).where(
                            Sender.account_id == selected.id,
                            func.lower(Sender.from_email) == r.value.lower(),
                        )
                    )
                    or 0
                )
            elif r.kind == WhitelistKind.domain:
                cnt = (
                    db.scalar(
                        select(func.count(Sender.id)).where(
                            Sender.account_id == selected.id,
                            func.lower(Sender.from_domain) == r.value.lower(),
                        )
                    )
                    or 0
                )
            else:
                cnt = 0
            affected[r.id] = cnt

    return _templates().TemplateResponse(
        request,
        "pages/whitelist.html",
        {
            "accounts": accounts,
            "selected_account": selected,
            "rules": rules,
            "affected": affected,
            "kinds": list(WhitelistKind),
        },
    )


@router.post("")
def create_rule(
    account_id: Annotated[int, Form()],
    kind: Annotated[WhitelistKind, Form()],
    value: Annotated[str, Form()],
    db: DbSession,
):
    if not db.get(Account, account_id):
        raise HTTPException(status_code=404)
    value = value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="value required")
    existing = db.scalar(
        select(WhitelistRule).where(
            WhitelistRule.account_id == account_id,
            WhitelistRule.kind == kind,
            WhitelistRule.value == value,
        )
    )
    if not existing:
        db.add(WhitelistRule(account_id=account_id, kind=kind, value=value))
        db.commit()
        recompute_sender_statuses(db, account_id)
    return RedirectResponse(
        url=f"/whitelist?account_id={account_id}", status_code=303
    )


@router.post("/{rule_id}/delete")
def delete_rule(rule_id: int, db: DbSession):
    rule = db.get(WhitelistRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404)
    account_id = rule.account_id
    db.delete(rule)
    db.commit()
    recompute_sender_statuses(db, account_id)
    return RedirectResponse(
        url=f"/whitelist?account_id={account_id}", status_code=303
    )

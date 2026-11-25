import re
from typing import Any, Dict, Type
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, select

from database import get_session


def generate_next_id(session: Session, model: Type[SQLModel], prefix: str, pad: int = 2) -> str:
    """Generate the next sequential string ID for a model (e.g., EMP-33, POD-4)."""
    existing_ids = session.exec(select(model.id)).all()  # type: ignore[attr-defined]
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_num = 0
    for row_id in existing_ids:
        match = pattern.match(str(row_id))
        if match:
            max_num = max(max_num, int(match.group(1)))
    next_num = max_num + 1
    if pad > 0:
        return f"{prefix}{next_num:0{pad}d}"
    return f"{prefix}{next_num}"


def register_crud_routes(
    router: APIRouter,
    path: str,
    model: Type[SQLModel],
    prefix: str,
    pad: int = 2,
) -> None:
    """Register standard GET (list & by id), POST, PUT, DELETE routes for a SQLModel table."""
    model_name = model.__name__

    @router.get(path)
    def list_items(session: Session = Depends(get_session)):
        return session.exec(select(model)).all()

    @router.get(f"{path}/{{item_id}}")
    def get_item(item_id: str, session: Session = Depends(get_session)):
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{model_name} '{item_id}' not found")
        return obj

    @router.post(path)
    def create_item(
        body: Dict[str, Any] = Body(...),
        session: Session = Depends(get_session),
    ):
        payload = dict(body)
        if not payload.get("id"):
            payload["id"] = generate_next_id(session, model, prefix, pad)
        elif session.get(model, payload["id"]):
            raise HTTPException(
                status_code=409,
                detail=f"{model_name} with id '{payload['id']}' already exists",
            )
        try:
            obj = model.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj

    @router.put(f"{path}/{{item_id}}")
    def update_item(
        item_id: str,
        body: Dict[str, Any] = Body(...),
        session: Session = Depends(get_session),
    ):
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{model_name} '{item_id}' not found")
        merged = obj.model_dump()
        for key, val in body.items():
            if key != "id" and key in merged:
                merged[key] = val
        try:
            validated = model.model_validate(merged)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())
        for key, val in validated.model_dump().items():
            setattr(obj, key, val)
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj

    @router.delete(f"{path}/{{item_id}}")
    def delete_item(item_id: str, session: Session = Depends(get_session)):
        obj = session.get(model, item_id)
        if not obj:
            raise HTTPException(status_code=404, detail=f"{model_name} '{item_id}' not found")
        session.delete(obj)
        session.commit()
        return {"status": "deleted", "id": item_id}

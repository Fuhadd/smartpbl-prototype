"""POST /notes (ingest and process) and GET /notes/{id}."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_llm_client, get_prompt, require
from app.api.schemas import NoteOut
from app.auth.models import User
from app.auth.permissions import Permission
from app.core.db import get_session
from app.nlp.llm import ChatClient
from app.nlp.models import CareNoteRecord
from app.nlp.pipeline import process_note
from app.nlp.prompts import PromptTemplate
from app.nlp.schemas import CareNote

router = APIRouter(prefix="/notes", tags=["notes"], dependencies=[Depends(get_current_user)])
SessionDep = Annotated[Session, Depends(get_session)]


def _duplicate(external_id: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f"note {external_id!r} already exists")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(
    _: Annotated[User, Depends(require(Permission.NOTE_CREATE))],
    note: CareNote,
    session: SessionDep,
    client: Annotated[ChatClient, Depends(get_llm_client)],
    prompt: Annotated[PromptTemplate, Depends(get_prompt)],
) -> NoteOut:
    """Redact, extract (LLM + rules), ground, route and persist one note.

    Synchronous: the request waits for the LLM (~6 s on the dev laptop). A job queue is
    future work. If the LLM is down the note is still saved, with baseline flags.
    """
    exists = session.scalar(
        select(CareNoteRecord.id).where(CareNoteRecord.external_id == note.note_id)
    )
    if exists:
        raise _duplicate(note.note_id)  # fail fast, before spending seconds on the LLM
    session.rollback()  # end the read transaction: don't hold a connection during the LLM call

    rec = process_note(session, note, client, prompt)
    try:
        session.commit()
    except IntegrityError as e:  # a concurrent request inserted the same note_id
        session.rollback()
        raise _duplicate(note.note_id) from e
    return NoteOut.model_validate(rec)


@router.get("/{note_id}")
def get_note(
    _: Annotated[User, Depends(require(Permission.NOTE_READ))],
    note_id: UUID,
    session: SessionDep,
) -> NoteOut:
    rec = session.get(CareNoteRecord, note_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found")
    return NoteOut.model_validate(rec)

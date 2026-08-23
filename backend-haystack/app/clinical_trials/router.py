"""
ClinicalTrials.gov assist (optional JSON API): Spanish question → LLM keywords → fetch → LLM answer.
Main UX uses query-stream + clinical_trials_search flag.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_model_config
from app.rag.clinical_trials_search import fetch_clinical_trials_documents
from app.rag.pipeline import SYSTEM_PROMPT, build_chat_messages, get_pipeline_manager
from app.rag.router import _doc_to_source, _filter_cited_sources, _sanitize_text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["clinical-trials"])

CT_CONTEXT = (
    "\n\nCONTEXTO DE ESTA SESIÓN: Las fuentes numeradas [N] son registros públicos de ClinicalTrials.gov "
    "(National Library of Medicine). Solo hay ensayos con criterio de ubicación México en la búsqueda. "
    "Interpreta los datos del registro (estado, resumen, condiciones) en español mexicano. "
    "Cita con [N] cuando te bases en un ensayo concreto. Si los registros no responden bien a la pregunta, dilo con claridad."
)


class ClinicalTrialsAssistRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=8000)
    model: Optional[str] = None


class ClinicalTrialsAssistResponse(BaseModel):
    answer: str
    sources: list[dict]
    keywords_used: str
    studies_fetched: int
    model: str


@router.post("/clinical-trials/assist", response_model=ClinicalTrialsAssistResponse)
async def clinical_trials_assist(
    body: ClinicalTrialsAssistRequest,
    user: User = Depends(get_current_user),
):
    logger.debug("clinical_trials assist user_id=%s", user.id)
    manager = get_pipeline_manager()
    model_id = manager.get_model_id(body.model)
    public_model_id = manager.get_public_model_id(model_id)
    generator = manager.get_generator(model_id)
    model_cfg = get_model_config(model_id)
    base_system = (getattr(model_cfg, "system_prompt", None) or "").strip() or SYSTEM_PROMPT
    system_for_ct = base_system + CT_CONTEXT

    documents, keywords_used = await fetch_clinical_trials_documents(
        body.question.strip(), manager, model_id, max_results=22
    )

    if not documents:
        messages = build_chat_messages(
            question=(
                f"{body.question.strip()}\n\n"
                "(No se recuperaron registros en ClinicalTrials.gov con la búsqueda automática en México. "
                f"Palabras clave usadas en inglés: «{keywords_used}». Explica con claridad y sugiere reformular la pregunta o términos.)"
            ),
            documents=[],
            history=[],
            system_prompt=system_for_ct,
        )
        gen_result = generator.run(messages=messages)
        replies = gen_result.get("replies", [])
        answer = replies[0].text if replies else "No se pudo generar respuesta."
        answer = _sanitize_text(answer)
        return ClinicalTrialsAssistResponse(
            answer=answer,
            sources=[],
            keywords_used=keywords_used,
            studies_fetched=0,
            model=public_model_id,
        )

    messages = build_chat_messages(
        question=body.question.strip(),
        documents=documents,
        history=[],
        system_prompt=system_for_ct,
        max_content_per_doc=1200,
    )
    gen_result = generator.run(messages=messages)
    replies = gen_result.get("replies", [])
    answer = replies[0].text if replies else "No se pudo generar respuesta."
    answer = _sanitize_text(answer)

    all_sources: list[dict] = []
    for doc in documents:
        if doc.content and doc.meta.get("url"):
            all_sources.append(_doc_to_source(doc))

    sources = _filter_cited_sources(answer, all_sources)
    if not sources and all_sources:
        sources = all_sources[: min(8, len(all_sources))]

    return ClinicalTrialsAssistResponse(
        answer=answer,
        sources=sources,
        keywords_used=keywords_used,
        studies_fetched=len(documents),
        model=public_model_id,
    )

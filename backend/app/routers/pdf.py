"""
PDF study-tool routes.

All endpoints:
- require authentication (Bearer token)
- are rate-limited (AI calls are expensive — Groq bills per request)
- validate uploads via pdf_service (type, size, magic bytes, encryption)
- convert PDFError / AIError into clean 400 / 503 responses (no tracebacks)
"""
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app.config import get_settings
from app.dependencies import get_current_user
from app.models import User
from app.rate_limit import limiter
from app.schemas import ScoredQuizResult, TextResult
from app.services import ai_service
from app.services.ai_service import AIError
from app.services.pdf_service import (
    PDFError,
    extract_text_from_multiple_pdfs,
    extract_text_from_pdf,
)

router = APIRouter(prefix="/api/pdf", tags=["pdf"], dependencies=[Depends(get_current_user)])

settings = get_settings()

# Read from settings so RATE_LIMIT_AI in .env actually takes effect — it was
# previously hard-coded here, which made the environment variable a no-op.
_AI_LIMIT = settings.rate_limit_ai
_SEARCH_LIMIT = settings.rate_limit_default


def _handle(fn, *args, **kwargs):
    """Run a service call, translating domain errors into HTTP errors."""
    try:
        return fn(*args, **kwargs)
    except PDFError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AIError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )


async def _text_single(file: UploadFile) -> str:
    try:
        return await extract_text_from_pdf(file)
    except PDFError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _text_multi(files: list[UploadFile]) -> str:
    try:
        return await extract_text_from_multiple_pdfs(files)
    except PDFError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── Single-file features ──────────────────────────────────────────────────


@router.post("/summarize", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def summarize(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_summary, text))


@router.post("/quiz", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def quiz(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_quiz, text))


@router.post("/quiz-difficulty", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def quiz_difficulty(
    request: Request,
    file: UploadFile = File(...),
    difficulty: str = Form(...),
):
    if difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Difficulty must be easy, medium, or hard.",
        )
    text = await _text_single(file)
    return TextResult(
        filename=file.filename,
        result=_handle(ai_service.generate_quiz_by_difficulty, text, difficulty),
    )


@router.post("/scored-quiz", response_model=ScoredQuizResult)
@limiter.limit(_AI_LIMIT)
async def scored_quiz(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return ScoredQuizResult(
        filename=file.filename or "document.pdf",
        quiz=_handle(ai_service.generate_scored_quiz, text),
    )


@router.post("/flashcards", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def flashcards(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_flashcards, text))


@router.post("/viva", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def viva(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_viva_questions, text))


@router.post("/study-plan", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def study_plan(request: Request, file: UploadFile = File(...)):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_study_plan, text))


@router.post("/notes", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def notes(
    request: Request,
    file: UploadFile = File(...),
    note_type: str = Form(...),
):
    if note_type not in ("short", "detailed", "exam"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="note_type must be short, detailed, or exam.",
        )
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.generate_notes, text, note_type))


@router.post("/chat", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def chat(
    request: Request,
    file: UploadFile = File(...),
    question: str = Form(..., min_length=1, max_length=1000),
):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.chat_with_pdf, text, question))


@router.post("/search", response_model=TextResult)
@limiter.limit(_SEARCH_LIMIT)
async def search(
    request: Request,
    file: UploadFile = File(...),
    keyword: str = Form(..., min_length=1, max_length=200),
):
    text = await _text_single(file)
    return TextResult(filename=file.filename, result=_handle(ai_service.search_inside_text, text, keyword))


# ── Multi-file features ────────────────────────────────────────────────────


@router.post("/multi/summarize", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def multi_summarize(request: Request, files: list[UploadFile] = File(...)):
    text = await _text_multi(files)
    return TextResult(
        files=[f.filename for f in files],
        result=_handle(ai_service.generate_summary, text, True),
    )


@router.post("/multi/quiz", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def multi_quiz(request: Request, files: list[UploadFile] = File(...)):
    text = await _text_multi(files)
    return TextResult(
        files=[f.filename for f in files],
        result=_handle(ai_service.generate_quiz, text, True),
    )


@router.post("/multi/chat", response_model=TextResult)
@limiter.limit(_AI_LIMIT)
async def multi_chat(
    request: Request,
    files: list[UploadFile] = File(...),
    question: str = Form(..., min_length=1, max_length=1000),
):
    text = await _text_multi(files)
    return TextResult(
        files=[f.filename for f in files],
        result=_handle(ai_service.chat_with_pdf, text, question, True),
    )


@router.post("/multi/search", response_model=TextResult)
@limiter.limit(_SEARCH_LIMIT)
async def multi_search(
    request: Request,
    files: list[UploadFile] = File(...),
    keyword: str = Form(..., min_length=1, max_length=200),
):
    text = await _text_multi(files)
    return TextResult(
        files=[f.filename for f in files],
        result=_handle(ai_service.search_inside_text, text, keyword),
    )

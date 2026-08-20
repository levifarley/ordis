import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from backend.config import settings
from backend.auth import (
    Token,
    User,
    authenticate_user,
    create_access_token,
    get_current_user
)
from backend.rag_engine import rag_engine
from backend.vector_store import get_vector_store
from backend.background_worker import background_worker

logger = logging.getLogger("ordis.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ORDIS FastAPI Backend Service...")
    bg_task = asyncio.create_task(background_worker.start_scheduled_worker())
    yield
    bg_task.cancel()

app = FastAPI(
    title=settings.APP_NAME,
    description="FastAPI Backend for ORDIS Cephalon AI",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    prompt: str
    chat_history: Optional[List[Dict[str, Any]]] = None

class HealthResponse(BaseModel):
    status: str
    service: str
    llm_provider: str
    vector_store: str
    ollama_available: bool
    chroma_available: bool
    background_worker: Dict[str, Any]

@app.post("/api/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_ok = authenticate_user(form_data.username, form_data.password)
    if not user_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": form_data.username})
    return Token(access_token=access_token, token_type="bearer")

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    ollama_available = False
    hosts_to_try = [settings.OLLAMA_HOST, "http://localhost:11434", "http://127.0.0.1:11434"]
    for host in hosts_to_try:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{host}/api/tags")
                if res.status_code == 200:
                    ollama_available = True
                    break
        except Exception:
            continue

    chroma_available = False
    try:
        store = get_vector_store()
        store.get_existing_hashes()
        chroma_available = True
    except Exception:
        chroma_available = False

    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        llm_provider=settings.LLM_PROVIDER,
        vector_store=settings.VECTOR_STORE_PROVIDER,
        ollama_available=ollama_available,
        chroma_available=chroma_available,
        background_worker={"is_ingesting": background_worker.is_ingesting}
    )

@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    def event_generator():
        stream_gen, payload = rag_engine.generate_response_stream(
            raw_query=request.prompt,
            chat_history=request.chat_history
        )
        full_text = ""
        if isinstance(stream_gen, list):
            for token in stream_gen:
                full_text += str(token)
                yield str(token)
        else:
            for token in stream_gen:
                full_text += str(token)
                yield str(token)
        
        # Finalize telemetry & post-response hooks after response stream completes
        rag_engine.finalize_telemetry(request.prompt, full_text, payload)

    return StreamingResponse(event_generator(), media_type="text/plain")

@app.post("/api/ingest/trigger")
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    if background_worker.is_ingesting:
        return {"status": "in_progress", "message": "Ingestion process is already running."}
    
    background_tasks.add_task(background_worker.ingest_all_data)
    return {"status": "triggered", "message": "Background data ingestion triggered successfully."}

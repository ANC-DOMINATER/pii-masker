import os
import time
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from pii_masker.model import PIIMasker, MaskResult, EntityMatch
from .schemas import (
    MaskRequest, MaskResponse, EntityMatchSchema,
    BatchMaskRequest, BatchMaskResponse,
    HealthResponse, FileMaskResponse
)

logger = logging.getLogger(__name__)

# Global single instance of PIIMasker
_masker_instance: PIIMasker = None


def get_masker() -> PIIMasker:
    global _masker_instance
    if _masker_instance is None:
        _masker_instance = PIIMasker()
    return _masker_instance


def create_app() -> FastAPI:
    app = FastAPI(
        title="PII Masker Service API",
        description="High-precision Personally Identifiable Information (PII) detection and masking API powered by DeBERTa-v3 & Regex AI Engine.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Enable CORS for cross-origin integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.on_event("startup")
    async def startup_event():
        logger.info("Initializing PII Masker model instance...")
        get_masker()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h1>PII Masker Service API</h1><p>Visit <a href='/docs'>/docs</a> for Swagger UI.</p>")

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
    async def health_check(masker: PIIMasker = Depends(get_masker)):
        supported = list(masker.regex_patterns.keys())
        return HealthResponse(
            status="ok",
            version="0.1.0",
            use_transformer=masker.use_transformer,
            device=masker.device,
            supported_entities=supported
        )

    @app.get("/api/v1/entities", tags=["Entities"])
    async def list_supported_entities():
        return {
            "entities": [
                {"name": "SSN", "description": "Social Security Numbers (USA)", "example": "123-45-6789"},
                {"name": "EMAIL", "description": "Email addresses", "example": "user@example.com"},
                {"name": "PHONE_NUM", "description": "Phone numbers (International & US)", "example": "+1-555-0199"},
                {"name": "CREDIT_CARD", "description": "Credit and debit card numbers", "example": "4532-1234-5678-9012"},
                {"name": "STREET_ADDRESS", "description": "Physical street addresses", "example": "1234 Elm Street"},
                {"name": "IP_ADDRESS", "description": "IPv4 network addresses", "example": "192.168.1.1"},
                {"name": "URL_PERSONAL", "description": "Personal website links & profiles", "example": "https://linkedin.com/in/user"},
                {"name": "USERNAME", "description": "Social handles & usernames", "example": "@johndoe_99"},
                {"name": "API_KEY", "description": "API keys and secret tokens", "example": "sk-proj-123456789"},
                {"name": "ID_NUM", "description": "National ID & License numbers", "example": "ID-992182"}
            ]
        }

    @app.post("/api/v1/mask", response_model=MaskResponse, tags=["Masking"])
    async def mask_text(
        req: MaskRequest,
        masker: PIIMasker = Depends(get_masker)
    ):
        try:
            res: MaskResult = masker.analyze_and_mask(
                input_text=req.text,
                mask_format=req.mask_format or "[{TYPE}]"
            )
            return MaskResponse(
                original_text=res.original_text,
                masked_text=res.masked_text,
                pii_dict=res.pii_dict,
                entities=[EntityMatchSchema(**e.to_dict()) for e in res.entities],
                processing_time_ms=res.processing_time_ms
            )
        except Exception as e:
            logger.error(f"Error during masking: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/mask/batch", response_model=BatchMaskResponse, tags=["Masking"])
    async def mask_batch(
        req: BatchMaskRequest,
        masker: PIIMasker = Depends(get_masker)
    ):
        start_time = time.time()
        results: List[MaskResponse] = []
        
        for text in req.texts:
            res: MaskResult = masker.analyze_and_mask(
                input_text=text,
                mask_format=req.mask_format or "[{TYPE}]"
            )
            results.append(MaskResponse(
                original_text=res.original_text,
                masked_text=res.masked_text,
                pii_dict=res.pii_dict,
                entities=[EntityMatchSchema(**e.to_dict()) for e in res.entities],
                processing_time_ms=res.processing_time_ms
            ))

        total_time = round((time.time() - start_time) * 1000, 2)
        return BatchMaskResponse(
            results=results,
            total_processed=len(results),
            total_time_ms=total_time
        )

    @app.post("/api/v1/mask/file", response_model=FileMaskResponse, tags=["Masking"])
    async def mask_file(
        file: UploadFile = File(...),
        mask_format: str = Form("[{TYPE}]"),
        masker: PIIMasker = Depends(get_masker)
    ):
        start_time = time.time()
        try:
            content_bytes = await file.read()
            text_content = content_bytes.decode("utf-8", errors="ignore")

            res: MaskResult = masker.analyze_and_mask(
                input_text=text_content,
                mask_format=mask_format
            )

            pii_summary = {k: len(v) for k, v in res.pii_dict.items()}
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return FileMaskResponse(
                filename=file.filename or "uploaded_file.txt",
                original_size_bytes=len(content_bytes),
                masked_text=res.masked_text,
                pii_summary=pii_summary,
                entities_found_count=len(res.entities),
                processing_time_ms=elapsed_ms
            )
        except Exception as e:
            logger.error(f"Error processing file upload: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

    return app


app = create_app()

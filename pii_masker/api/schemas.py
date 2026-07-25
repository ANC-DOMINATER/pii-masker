from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class MaskRequest(BaseModel):
    text: str = Field(
        ...,
        description="The input text containing potential Personally Identifiable Information (PII).",
        example="John Doe lives at 1234 Elm St and his SSN is 123-45-6789. Contact at john.doe@example.com or +1-555-0199."
    )
    mask_format: Optional[str] = Field(
        "[{TYPE}]",
        description="Format string for mask replacement token. Supported placeholders: {TYPE}.",
        example="[{TYPE}]"
    )


class EntityMatchSchema(BaseModel):
    entity_type: str = Field(..., description="Category of PII entity (e.g. SSN, EMAIL, PHONE_NUM)")
    value: str = Field(..., description="Original sensitive text value")
    start: int = Field(..., description="Start character offset in original text")
    end: int = Field(..., description="End character offset in original text")
    confidence: float = Field(..., description="Detection confidence score (0.0 to 1.0)")
    source: str = Field(..., description="Detection engine source ('transformer' or 'regex')")


class MaskResponse(BaseModel):
    original_text: str
    masked_text: str
    pii_dict: Dict[str, List[str]] = Field(..., description="Grouped dictionary mapping entity types to detected values")
    entities: List[EntityMatchSchema] = Field(..., description="Detailed list of detected PII entity spans")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class BatchMaskRequest(BaseModel):
    texts: List[str] = Field(
        ...,
        description="List of input text strings to mask in batch.",
        example=[
            "Alice Smith email is alice@company.org",
            "Call Bob at 555-123-4567 or visit https://bob.me"
        ]
    )
    mask_format: Optional[str] = Field("[{TYPE}]", description="Mask format template")


class BatchMaskResponse(BaseModel):
    results: List[MaskResponse]
    total_processed: int
    total_time_ms: float


class HealthResponse(BaseModel):
    status: str = Field("ok", example="ok")
    version: str = Field("0.1.0", example="0.1.0")
    use_transformer: bool = Field(False, description="Whether HuggingFace transformer model weights are active")
    device: str = Field("cpu", example="cpu")
    supported_entities: List[str]


class FileMaskResponse(BaseModel):
    filename: str
    original_size_bytes: int
    masked_text: str
    pii_summary: Dict[str, int]
    entities_found_count: int
    processing_time_ms: float

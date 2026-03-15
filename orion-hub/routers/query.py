"""AEGIS AI query endpoint — POST /api/query."""

from typing import Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter

from services import ai_agent

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    env: Optional[str] = Field(
        None,
        pattern=r"^(CEDERVALL|VALVX|GWSK|PERSONAL|ALL)$",
        description="Environment filter",
    )


class QueryResponse(BaseModel):
    answer: str
    tokens_used: int


@router.post("/api/query", response_model=QueryResponse)
async def query_ai(req: QueryRequest):
    """Query the AEGIS AI with context-injected question."""
    result = await ai_agent.query(req.question, req.env)
    return QueryResponse(**result)

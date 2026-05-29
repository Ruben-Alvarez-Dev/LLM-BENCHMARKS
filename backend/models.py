"""LLM-BENCHMARKS — Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MachineCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    user: str = "admin"
    identity_file: Optional[str] = None


class MachineResponse(MachineCreate):
    id: int
    chip: Optional[str] = None
    ram_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    engines: List[str] = []
    is_local: bool = False
    status: str = "offline"
    last_seen: Optional[str] = None
    created_at: Optional[str] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    format: str
    path: str
    machine_id: int
    machine_name: Optional[str] = None
    size_bytes: Optional[int] = None
    params_b: Optional[float] = None
    context_max: Optional[int] = None
    quant: Optional[str] = None
    discovered_at: Optional[str] = None


class BenchmarkConfig(BaseModel):
    context_len: int = 16384
    kv_format: str = "q4_0"
    flash_attn: bool = True
    max_tokens: int = 256
    temperature: float = 0.0


class BenchmarkCreate(BaseModel):
    model_id: int
    machine_id: int
    config: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
    session_id: Optional[int] = None


class BenchmarkResult(BaseModel):
    id: int
    model_name: Optional[str] = None
    machine_name: Optional[str] = None
    engine: str = ""
    context_len: Optional[int] = None
    kv_format: Optional[str] = None
    flash_attn: Optional[bool] = None
    decode_speed: Optional[float] = None
    prefill_speed: Optional[float] = None
    ram_peak_gb: Optional[float] = None
    status: str
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class ActionLogEntry(BaseModel):
    id: int
    action_id: str
    action_type: str
    status: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    machine_id: Optional[int] = None
    progress_pct: float = 0
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    created_at: Optional[str] = None

"""Módulos de análise de benchmarks — discrepâncias, diffs e validação de pipeline."""

from .audit_six_questions import run_audit
from .diffs import generate_diffs_for_slug
from .etapa_diffs import generate_diffs_for_benchmark
from .pipeline_validator import validate_pipeline_integrity
from .stage_discrepancy_summary import build_summary as build_stage_discrepancy_summary

__all__ = [
    "build_stage_discrepancy_summary",
    "generate_diffs_for_benchmark",
    "generate_diffs_for_slug",
    "validate_pipeline_integrity",
    "run_audit",
]

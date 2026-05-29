# Benchmark Orchestrator — Sistema de pruebas controladas para inferencia local
#
# Modulos:
#   model_registry.py       — Catalogo de modelos con metadatos
#   ram_budget.py           — Calculo de presupuesto RAM
#   test_matrix_generator.py — Matriz cartesiana de tests
#   test_executor.py        — Ejecutor de tests con llama-cli
#   sqlite_writer.py        — Persistencia SQLite + export Markdown
#   main.py                 — Pipeline principal

from .model_registry import ModelSpec, MODEL_REGISTRY, get_model, list_models
from .ram_budget import calculate, BudgetResult, RAM_DISPONIBLE_GB
from .test_matrix_generator import TestConfig, generate_matrix, summary_report
from .test_executor import TestResult, run_single_test, run_test_series, print_result
from .sqlite_writer import get_connection, save_result, get_summary, export_to_markdown

__all__ = [
    "ModelSpec", "MODEL_REGISTRY", "get_model", "list_models",
    "calculate", "BudgetResult", "RAM_DISPONIBLE_GB",
    "TestConfig", "generate_matrix", "summary_report",
    "TestResult", "run_single_test", "run_test_series", "print_result",
    "get_connection", "save_result", "get_summary", "export_to_markdown",
]

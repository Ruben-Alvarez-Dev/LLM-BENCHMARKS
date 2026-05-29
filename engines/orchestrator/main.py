"""Main Pipeline — orquestador completo de tests en serie.

Uso:
    python -m orchestrator.main Qwen2.5-7B-1M
    python -m orchestrator.main --all
    python -m orchestrator.main Qwen2.5-7B-1M --contexts 16384 32768 65536

Filosofia:
    - Serie estricta: un modelo a la vez, un test a la vez
    - Limpieza completa entre tests y entre modelos
    - Fallo temprano: primer error detiene la tanda del modelo (opcional)
    - Cada test se registra inmediatamente en SQLite
"""
import os
import sys
import time
import json
import argparse
from typing import List, Optional
from datetime import datetime

from .model_registry import MODEL_REGISTRY, get_model, list_models
from .test_matrix_generator import generate_matrix, summary_report, TestConfig
from .test_executor import run_single_test, run_test_series, print_result, TestResult
from .sqlite_writer import get_connection, save_result, save_results_batch, get_summary, export_to_markdown, DEFAULT_DB_PATH

DEFAULT_CONTEXTS = [16_384, 32_768, 65_536, 131_072, 262_144]


def run_model_campaign(
    model_name: str,
    contexts: Optional[List[int]] = None,
    kv_formats: Optional[List[str]] = None,
    flash_options: Optional[List[bool]] = None,
    quant: Optional[str] = None,
    include_experimental: bool = False,
    stop_on_error: bool = False,
    db_path: str = DEFAULT_DB_PATH,
    dry_run: bool = False,
) -> List[TestResult]:
    """Ejecuta la campana completa para un modelo.

    Pipeline:
        1. Cargar modelo del registry
        2. Generar matriz de tests
        3. Filtrar por RAM
        4. Mostrar resumen al usuario
        5. Ejecutar tests en serie
        6. Guardar cada resultado en SQLite
        7. Exportar reporte Markdown

    Args:
        model_name: Nombre del modelo en MODEL_REGISTRY
        contexts: Lista de contextos a probar (default: escalation estandar)
        kv_formats: Formatos KV (default: f16, q4_0, q8_0)
        flash_options: Flash attention on/off (default: ambos)
        quant: Cuantizacion (default: primera disponible)
        include_experimental: Incluir planar3 si el modelo lo soporta
        stop_on_error: Detener al primer error
        db_path: Ruta a la BD SQLite
        dry_run: Solo mostrar matriz, no ejecutar

    Returns:
        Lista de TestResult
    """
    model_spec = get_model(model_name)
    if model_spec is None:
        print(f"ERROR: Modelo '{model_name}' no encontrado en el registro.")
        print(f"Modelos disponibles: {', '.join(list_models())}")
        return []

    # Validar que el modelo existe localmente
    if not model_spec.has_local:
        print(f"AVISO: {model_name} no tiene GGUF local. gguf_source: {model_spec.gguf_source}")
        print("  Los tests saltaran por modelo no encontrado.")
    else:
        size_gb = os.path.getsize(model_spec.local_path) / (1024**3)
        print(f"Modelo local: {model_spec.local_path} ({size_gb:.1f} GB)")

    # 1. Generar matriz
    print(f"\nGenerando matriz de tests para {model_name}...")
    configs = generate_matrix(
        model_spec,
        context_steps=contexts,
        kv_formats=kv_formats,
        flash_options=flash_options,
        quant=quant,
        include_experimental_kv=include_experimental,
    )

    ejecutables = [c for c in configs if c.fits]
    no_ejecutables = [c for c in configs if not c.fits]

    print(f"  Total configs: {len(configs)}")
    print(f"  OK (entran en RAM): {len(ejecutables)}")
    print(f"  SKIP (no entran): {len(no_ejecutables)}")

    if no_ejecutables:
        print("  SKIP detalle:")
        for c in no_ejecutables:
            print(f"    - {c.context_len // 1024}K {c.kv_format} "
                  f"{'fa' if c.flash_attn else 'nofa'}: "
                  f"{c.ram_total_gb:.2f} GB > {c.ram_available_gb:.1f} GB")

    if dry_run or len(ejecutables) == 0:
        print(f"\n{'--- DRY RUN ---' if dry_run else '--- Sin tests ejecutables ---'}")
        return []

    # 2. Confirmar (si hay muchos tests)
    total_estimated_min = len(ejecutables) * 0.5  # estimacion minima
    total_estimated_max = len(ejecutables) * 3.0   # estimacion maxima (carga grande)
    print(f"\nTiempo estimado: {total_estimated_min:.0f}-{total_estimated_max:.0f} minutos")
    print(f"Orden de ejecucion: ", end="")
    for c in ejecutables:
        print(f"{c.context_len // 1024}K {c.kv_format} "
              f"{'fa' if c.flash_attn else 'nofa'}", end=" → ")
    print("FIN")

    # 3. Ejecutar
    conn = get_connection(db_path)
    results = []
    total = len(ejecutables)

    for i, cfg in enumerate(ejecutables):
        print(f"\n{'='*60}")
        print(f"Test {i+1}/{total}: {cfg.id}")
        print(f"{'='*60}")

        test_start = time.time()
        result = run_single_test(cfg, model_spec)
        result.ram_estimate_gb = cfg.ram_total_gb
        elapsed = time.time() - test_start

        # Mostrar resultado
        print(print_result(result))
        print(f"  Wall time: {elapsed:.1f}s")

        # Guardar en SQLite inmediatamente
        try:
            save_result(conn, result)
        except Exception as e:
            print(f"  AVISO: Error al guardar en BD: {e}")

        results.append(result)

        # Pequena pausa entre tests
        if i < total - 1:
            print("  Liberando memoria...")
            time.sleep(3)

        # Stop on error
        if stop_on_error and result.status != "ok":
            print(f"\n--- Campana detenida por error en {cfg.id} ---")
            break

    conn.close()

    # 4. Resumen
    passed = sum(1 for r in results if r.status == "ok")
    oom = sum(1 for r in results if r.status == "oom")
    timeout = sum(1 for r in results if r.status == "timeout")
    errors = sum(1 for r in results if r.status == "error")

    print(f"\n{'='*60}")
    print(f"Campana {model_name} completada: {passed} OK, {oom} OOM, "
          f"{timeout} timeout, {errors} error de {len(results)} tests")
    print(f"Reporte: python -m orchestrator.main --report {model_name}")
    print(f"{'='*60}")

    return results


def show_report(model_name: Optional[str] = None, db_path: str = DEFAULT_DB_PATH):
    """Muestra el reporte de resultados almacenados."""
    conn = get_connection(db_path)
    if model_name:
        print(export_to_markdown(conn, model_name))
    else:
        print(get_summary(conn))
        print()
        print(export_to_markdown(conn))
    conn.close()


def export_report(model_name: str, output_path: Optional[str] = None, db_path: str = DEFAULT_DB_PATH):
    """Exporta reporte Markdown a archivo."""
    conn = get_connection(db_path)
    md = export_to_markdown(conn, model_name)
    conn.close()

    if output_path is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "docs", "research", "benchmarks"
        )
        os.makedirs(output_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(output_dir, f"{date_str}-{model_name}-REPORT.md")

    with open(output_path, "w") as f:
        f.write(md)
    print(f"Reporte exportado a: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Orchestrator — tests de inferencia controlados en serie"
    )
    parser.add_argument("model", nargs="?", help="Nombre del modelo (o --all)")
    parser.add_argument("--all", action="store_true", help="Ejecutar todos los modelos disponibles")
    parser.add_argument("--contexts", type=int, nargs="+", help="Contextos a probar")
    parser.add_argument("--kv", choices=["f16", "q4_0", "q8_0", "all"], default="q4_0",
                        help="Formato KV (default: q4_0)")
    parser.add_argument("--flash", choices=["on", "off", "both"], default="both",
                        help="Flash attention (default: both)")
    parser.add_argument("--quant", type=str, default="Q4_K_M", help="Cuantizacion")
    parser.add_argument("--experimental", action="store_true", help="Incluir planar3")
    parser.add_argument("--stop-on-error", action="store_true", help="Detener en primer error")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar matriz, no ejecutar")
    parser.add_argument("--report", nargs="?", const=True, default=False,
                        help="Mostrar reporte (opcional: nombre de modelo)")
    parser.add_argument("--export", type=str, help="Exportar reporte a archivo (requiere --model)")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Ruta a BD SQLite")
    parser.add_argument("--list-models", action="store_true", help="Listar modelos disponibles")

    args = parser.parse_args()

    if args.list_models:
        print("Modelos disponibles:")
        for name in list_models():
            m = get_model(name)
            local = " [LOCAL]" if m and m.has_local else ""
            print(f"  {name}{local}")
        return

    if args.report:
        model_name = args.report if isinstance(args.report, str) else None
        show_report(model_name, args.db)
        return

    if args.export:
        if not args.model:
            print("ERROR: --export requiere --model")
            sys.exit(1)
        export_report(args.model, args.export, args.db)
        return

    if not args.model and not args.all:
        parser.print_help()
        print("\nERROR: Especificar un modelo o --all")
        sys.exit(1)

    # Configurar variables de test
    contexts = args.contexts or DEFAULT_CONTEXTS
    kv_formats = {"f16": ["f16"], "q4_0": ["q4_0"], "q8_0": ["q8_0"], "all": ["f16", "q4_0", "q8_0"]}
    flash_options = {"on": [True], "off": [False], "both": [True, False]}

    models_to_run = list_models() if args.all else [args.model]

    for model_name in models_to_run:
        if model_name not in MODEL_REGISTRY:
            print(f"ERROR: Modelo '{model_name}' no encontrado.")
            print(f"  Disponibles: {', '.join(list_models())}")
            continue

        print(f"\n{'#'*60}")
        print(f"# Campana: {model_name}")
        print(f"{'#'*60}")

        results = run_model_campaign(
            model_name=model_name,
            contexts=contexts,
            kv_formats=kv_formats[args.kv],
            flash_options=flash_options[args.flash],
            quant=args.quant,
            include_experimental=args.experimental,
            stop_on_error=args.stop_on_error,
            db_path=args.db,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            continue

        if results:
            export_report(model_name, db_path=args.db)

        # Limpieza entre modelos
        if model_name != models_to_run[-1]:
            print(f"\nLimpieza entre modelos...")
            time.sleep(5)


if __name__ == "__main__":
    main()

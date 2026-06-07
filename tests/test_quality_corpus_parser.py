"""Tests F1: calidad (puro), corpus determinista (tmp), parser de timings (fixtures)."""
import tempfile
import unittest
from pathlib import Path

from frontier_bench.adapters.corpus.real_corpus import RealCorpus
from frontier_bench.adapters.engines.llamacpp_cli import parse_timings
from frontier_bench.domain.quality import (degeneration, insert_needles, make_needles,
                                           needle_question, needle_recall)


class TestDegeneration(unittest.TestCase):
    def test_healthy_text(self):
        text = ("El sistema de memoria captura eventos en tiempo real y los consolida "
                "en capas progresivas según su importancia semántica para el agente. "
                "Cada capa reduce volumen y aumenta abstracción, igual que un resumen.")
        self.assertFalse(degeneration(text).degenerate)

    def test_repeated_loop_detected(self):
        loop = "la clave es la clave es la clave es la clave es " * 20
        rep = degeneration(loop)
        self.assertTrue(rep.degenerate)
        self.assertTrue(rep.repeated_ngram)

    def test_collapse_detected(self):
        collapse = "sí " * 400
        self.assertTrue(degeneration(collapse).degenerate)


class TestNeedles(unittest.TestCase):
    def test_deterministic_and_recall(self):
        n1, n2 = make_needles(seed=7), make_needles(seed=7)
        self.assertEqual(n1, n2)                      # mismo seed => mismos needles
        text = "\n".join(f"línea de contexto número {i}" for i in range(100))
        with_needles = insert_needles(text, n1)
        for n in n1:
            self.assertIn(n.value, with_needles)
        answer = f"Los valores son {n1[0].value} y {n1[2].value}."
        self.assertEqual(needle_recall(answer, n1), 2)
        self.assertIn(n1[0].key, needle_question(n1))


class TestRealCorpus(unittest.TestCase):
    def test_deterministic_and_nonrepetitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import random as _r
            words = ("sistema núcleo cola evento capa flujo índice vector nodo "
                     "puerto sonda motor celda métrica corpus presupuesto").split()
            for i in range(8):
                rng = _r.Random(i)
                paragraphs = []
                for j in range(12):
                    # párrafo de palabras barajadas con sufijos únicos: ningún
                    # 8-grama puede repetirse entre párrafos por construcción
                    toks = [f"{rng.choice(words)}-{i}{j}{k}" for k in range(45)]
                    paragraphs.append(f"Sección {i}.{j}: " + " ".join(toks) + ".")
                (root / f"doc{i}.md").write_text("\n\n".join(paragraphs))
            corpus = RealCorpus([root])
            a = corpus.text_tokens(2000, seed=42)
            b = corpus.text_tokens(2000, seed=42)
            c = corpus.text_tokens(2000, seed=99)
            self.assertEqual(a, b)                    # determinista
            self.assertNotEqual(a, c)                 # seed cambia el corpus
            # no-repetitivo: el fallo A2 era "frase × n"; aquí los párrafos difieren
            self.assertFalse(degeneration(a[:4000]).repeated_ngram)


OLD_FORMAT = """
llama_print_timings:        load time =    2200.50 ms
llama_print_timings: prompt eval time =   16400.00 ms /  14500 tokens
llama_print_timings:        eval time =    6400.00 ms /    128 runs
"""

NEW_FORMAT = """
llama_perf_context_print:        load time =    1800.00 ms
llama_perf_context_print: prompt eval time =    9000.00 ms /  9000 tokens
llama_perf_context_print:        eval time =    4000.00 ms /   128 tokens
"""


class TestTimingsParser(unittest.TestCase):
    def test_old_format(self):
        t = parse_timings(OLD_FORMAT)
        self.assertAlmostEqual(t["decode_tps"], 128 / 6.4, places=1)
        self.assertAlmostEqual(t["prefill_tps"], 14500 / 16.4, places=0)
        self.assertAlmostEqual(t["ttft_ms"], 2200.5 + 16400.0)
        self.assertEqual(t["prompt_tokens"], 14500)

    def test_new_format(self):
        t = parse_timings(NEW_FORMAT)
        self.assertAlmostEqual(t["decode_tps"], 32.0, places=1)
        self.assertAlmostEqual(t["prefill_tps"], 1000.0, places=0)

    def test_garbage_returns_empty(self):
        self.assertNotIn("decode_tps", parse_timings("sin timings aquí"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from app.security.cwe_list import (
    CWE_CATALOG,
    cwes_for_language,
    detect_language,
    get_cwe,
)


def test_catalog_has_15_entries():
    assert len(CWE_CATALOG) == 15
    ids = {entry.id for entry in CWE_CATALOG}
    assert "CWE-89" in ids
    assert "CWE-79" in ids
    assert "CWE-798" in ids


def test_detect_language_by_extension():
    assert detect_language("app/auth.py") == "python"
    assert detect_language("src/index.ts") == "typescript"
    assert detect_language("src/index.tsx") == "typescript"
    assert detect_language("Main.java") == "java"
    assert detect_language("server.go") == "go"


def test_detect_language_unknown_returns_none():
    assert detect_language("README.md") is None
    assert detect_language("noext") is None


def test_cwes_for_language_python_includes_core_three():
    entries = cwes_for_language("python")
    ids = {e.id for e in entries}
    assert {"CWE-89", "CWE-798", "CWE-79"}.issubset(ids)


def test_cwes_for_language_unknown_returns_empty():
    assert cwes_for_language(None) == []
    assert cwes_for_language("brainfuck") == []


def test_get_cwe_lookup():
    sqli = get_cwe("CWE-89")
    assert sqli is not None
    assert sqli.name == "SQL Injection"
    assert get_cwe("CWE-9999") is None

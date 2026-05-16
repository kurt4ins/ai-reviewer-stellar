from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CweEntry:
    id: str
    name: str
    description: str
    languages: frozenset[str]
    severity_default: str


_ALL_LANGS = frozenset({
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "ruby",
    "php",
    "csharp",
    "cpp",
    "c",
    "rust",
    "kotlin",
    "swift",
})

_WEB_LANGS = frozenset({"javascript", "typescript", "python", "php", "ruby", "java", "csharp"})
_BACKEND_LANGS = frozenset({"python", "java", "go", "ruby", "php", "csharp", "cpp", "c", "rust"})


CWE_CATALOG: tuple[CweEntry, ...] = (
    CweEntry(
        id="CWE-89",
        name="SQL Injection",
        description=(
            "Untrusted input concatenated or interpolated into a SQL query. "
            "Detect string-format / f-string / concat patterns that feed user data into raw SQL."
        ),
        languages=_BACKEND_LANGS,
        severity_default="critical",
    ),
    CweEntry(
        id="CWE-79",
        name="Cross-site Scripting (XSS)",
        description=(
            "User-controlled data rendered into HTML/DOM without proper escaping. "
            "Look for innerHTML, dangerouslySetInnerHTML, document.write, template literals "
            "feeding into HTML, or server-side templates rendering raw user input."
        ),
        languages=_WEB_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-798",
        name="Hardcoded Credentials",
        description=(
            "Secrets (API keys, tokens, passwords, private keys, JWT secrets) literally embedded "
            "in source code rather than read from environment / secret store. "
            "Detect literal strings matching common key formats."
        ),
        languages=_ALL_LANGS,
        severity_default="critical",
    ),
    CweEntry(
        id="CWE-78",
        name="OS Command Injection",
        description=(
            "User input passed into a shell command without quoting or via shell=True. "
            "Look for subprocess/exec/system/popen with concatenated input."
        ),
        languages=_BACKEND_LANGS,
        severity_default="critical",
    ),
    CweEntry(
        id="CWE-22",
        name="Path Traversal",
        description=(
            "User-controlled path joined with a base directory without normalization, allowing "
            "'../' escapes. Look for os.path.join / Path with un-sanitized request input."
        ),
        languages=_BACKEND_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-502",
        name="Deserialization of Untrusted Data",
        description=(
            "pickle.loads / yaml.load(Loader=Loader) / Java ObjectInputStream / "
            "PHP unserialize on user-supplied bytes."
        ),
        languages=_BACKEND_LANGS,
        severity_default="critical",
    ),
    CweEntry(
        id="CWE-94",
        name="Code Injection",
        description=(
            "eval / exec / Function() / Runtime.exec called on input derived from request data."
        ),
        languages=_ALL_LANGS,
        severity_default="critical",
    ),
    CweEntry(
        id="CWE-611",
        name="XML External Entity (XXE)",
        description=(
            "XML parser configured without disabling external entity resolution. "
            "Look for lxml/xml.etree without resolve_entities=False or equivalent."
        ),
        languages=_BACKEND_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-352",
        name="Cross-Site Request Forgery (CSRF)",
        description=(
            "State-changing endpoint without CSRF token / SameSite cookie / origin check. "
            "Flag explicit csrf_exempt decorators or missing protections."
        ),
        languages=_WEB_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-918",
        name="Server-Side Request Forgery (SSRF)",
        description=(
            "HTTP client called with URL derived from user input without allow-listing. "
            "Look for requests.get / fetch / httpx with user-supplied URLs."
        ),
        languages=_BACKEND_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-327",
        name="Use of Broken or Weak Cryptography",
        description=(
            "MD5/SHA1 for security purposes, DES, ECB mode, hardcoded IV, predictable PRNG "
            "(random module for tokens)."
        ),
        languages=_ALL_LANGS,
        severity_default="medium",
    ),
    CweEntry(
        id="CWE-200",
        name="Information Exposure",
        description=(
            "Stack traces, internal paths, secrets, or DB errors returned to the client. "
            "Verbose debug=True in production frameworks."
        ),
        languages=_BACKEND_LANGS,
        severity_default="medium",
    ),
    CweEntry(
        id="CWE-295",
        name="Improper Certificate Validation",
        description=(
            "HTTP client with verify=False, InsecureRequestWarning suppression, "
            "trust-all SSL contexts."
        ),
        languages=_BACKEND_LANGS,
        severity_default="high",
    ),
    CweEntry(
        id="CWE-1004",
        name="Sensitive Cookie Without Secure/HttpOnly",
        description=(
            "set_cookie / Set-Cookie missing Secure, HttpOnly, or SameSite attributes "
            "for session/auth cookies."
        ),
        languages=_WEB_LANGS,
        severity_default="medium",
    ),
    CweEntry(
        id="CWE-377",
        name="Insecure Temporary File",
        description=(
            "tempfile.mktemp / predictable temp file names / /tmp paths with fixed names "
            "vulnerable to race conditions."
        ),
        languages=_BACKEND_LANGS,
        severity_default="medium",
    ),
)


_BY_ID: dict[str, CweEntry] = {entry.id: entry for entry in CWE_CATALOG}


_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".rs": "rust",
    ".swift": "swift",
}


def detect_language(path: str) -> str | None:
    lower = path.lower()
    for ext, lang in _EXTENSION_LANGUAGE.items():
        if lower.endswith(ext):
            return lang
    return None


def cwes_for_language(language: str | None) -> list[CweEntry]:
    if language is None:
        return []
    return [entry for entry in CWE_CATALOG if language in entry.languages]


def get_cwe(cwe_id: str) -> CweEntry | None:
    return _BY_ID.get(cwe_id)

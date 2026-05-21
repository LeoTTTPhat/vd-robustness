"""Conservative source transformations for vulnerability-detector robustness.

These transformations are intentionally simple and low-compute. They are meant
for a pilot robustness benchmark, not for proving semantic equivalence of
arbitrary C/C++ programs.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
RESERVED_WORDS = {
    "auto",
    "break",
    "case",
    "char",
    "class",
    "const",
    "continue",
    "default",
    "delete",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "namespace",
    "new",
    "register",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "template",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}
TYPE_WORDS = (
    r"bool|char|double|float|int|long|short|size_t|ssize_t|uint\d+_t|int\d+_t"
)


@dataclass(frozen=True)
class TransformResult:
    name: str
    code: str
    changed: bool
    validation_note: str


def comment_banner(code: str) -> TransformResult:
    """Insert a harmless block comment before a function body when possible."""
    pos = code.find("{")
    if pos == -1:
        return TransformResult("comment_banner", code, False, "no opening brace")
    transformed = code[: pos + 1] + "\n/* robustness_probe: no semantic effect */" + code[pos + 1 :]
    return TransformResult("comment_banner", transformed, transformed != code, "comment inserted")


def blank_line_expansion(code: str) -> TransformResult:
    """Expand blank lines after semicolons to perturb layout only."""
    transformed = re.sub(r";\s*\n", ";\n\n", code, count=5)
    note = "blank lines inserted after semicolons" if transformed != code else "no semicolon-newline pattern"
    return TransformResult(
        "blank_line_expansion",
        transformed,
        transformed != code,
        note,
    )


def brace_line_shift(code: str) -> TransformResult:
    """Move an opening brace onto its own line for simple function signatures."""
    transformed = re.sub(r"\)\s*\{", ")\n{", code, count=1)
    note = "first function opening brace shifted" if transformed != code else "no simple signature-brace pattern"
    return TransformResult(
        "brace_line_shift",
        transformed,
        transformed != code,
        note,
    )


def dead_branch_after_opening_brace(code: str) -> TransformResult:
    """Insert a syntactically simple unreachable branch after the first brace."""
    pos = code.find("{")
    if pos == -1:
        return TransformResult("dead_branch_after_opening_brace", code, False, "no opening brace")
    payload = "\nif (0) { int rvd_dead_branch = 0; (void)rvd_dead_branch; }\n"
    transformed = code[: pos + 1] + payload + code[pos + 1 :]
    return TransformResult(
        "dead_branch_after_opening_brace",
        transformed,
        transformed != code,
        "unreachable branch inserted",
    )


def _protected_spans(code: str) -> list[tuple[int, int]]:
    """Return spans for comments, strings, character literals, and directives."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(code)
    while i < n:
        if code[i] == "#":
            line_start = code.rfind("\n", 0, i) + 1
            if code[line_start:i].strip() == "":
                end = code.find("\n", i)
                spans.append((i, n if end == -1 else end))
                i = n if end == -1 else end
                continue
        if code.startswith("//", i):
            end = code.find("\n", i)
            spans.append((i, n if end == -1 else end))
            i = n if end == -1 else end
            continue
        if code.startswith("/*", i):
            end = code.find("*/", i + 2)
            spans.append((i, n if end == -1 else end + 2))
            i = n if end == -1 else end + 2
            continue
        if code[i] in ("'", '"'):
            quote = code[i]
            j = i + 1
            escaped = False
            while j < n:
                if escaped:
                    escaped = False
                elif code[j] == "\\":
                    escaped = True
                elif code[j] == quote:
                    j += 1
                    break
                j += 1
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


def _in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _replace_identifier_outside_protected(code: str, old: str, new: str) -> tuple[str, int]:
    spans = _protected_spans(code)
    parts: list[str] = []
    last = 0
    replacements = 0
    for match in IDENTIFIER_RE.finditer(code):
        if match.group(0) != old or _in_spans(match.start(), spans):
            continue
        parts.append(code[last : match.start()])
        parts.append(new)
        last = match.end()
        replacements += 1
    if replacements == 0:
        return code, 0
    parts.append(code[last:])
    return "".join(parts), replacements


def identifier_renaming(code: str) -> TransformResult:
    """Rename one simple local variable or parameter outside comments/strings."""
    if "rvd_id0" in code:
        return TransformResult("identifier_renaming", code, False, "reserved transformed identifier already present")

    candidates: list[str] = []
    local_var_re = re.compile(
        rf"\b(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:{TYPE_WORDS})\s+[*\s]*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|;|,)",
        re.MULTILINE,
    )
    for match in local_var_re.finditer(code):
        name = match.group(1)
        if name not in RESERVED_WORDS and not name.startswith("__"):
            candidates.append(name)

    brace = code.find("{")
    paren = code.rfind("(", 0, brace if brace != -1 else len(code))
    if brace != -1 and paren != -1:
        signature = code[paren + 1 : brace]
        param_re = re.compile(
            rf"\b(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:{TYPE_WORDS}|[A-Za-z_][A-Za-z0-9_:<>]*)\s+[*&\s]*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|$)"
        )
        for match in param_re.finditer(signature):
            name = match.group(1)
            if name not in RESERVED_WORDS and not name.startswith("__"):
                candidates.append(name)

    for candidate in candidates:
        transformed, replacements = _replace_identifier_outside_protected(code, candidate, "rvd_id0")
        if replacements >= 2:
            return TransformResult(
                "identifier_renaming",
                transformed,
                True,
                "renamed simple identifier",
            )
    return TransformResult("identifier_renaming", code, False, "no simple identifier with repeated use")


def control_flow_rewrite(code: str) -> TransformResult:
    """Invert a simple if/else pair where both branches return immediately."""
    pattern = re.compile(
        r"if\s*\((?P<cond>[^{}\n;]+)\)\s*\{\s*return\s+(?P<then>[^;{}]+);\s*\}\s*else\s*\{\s*return\s+(?P<else>[^;{}]+);\s*\}",
        re.MULTILINE,
    )
    match = pattern.search(code)
    if not match:
        return TransformResult("control_flow_rewrite", code, False, "no simple returning if/else pattern")
    cond = match.group("cond").strip()
    then_expr = match.group("then").strip()
    else_expr = match.group("else").strip()
    replacement = f"if (!({cond})) {{\n    return {else_expr};\n}}\nreturn {then_expr};"
    transformed = code[: match.start()] + replacement + code[match.end() :]
    return TransformResult("control_flow_rewrite", transformed, True, "inverted simple returning if/else")


def safe_dead_code_carrier(code: str) -> TransformResult:
    """Insert a compile-time unreachable carrier block after the first brace."""
    pos = code.find("{")
    if pos == -1:
        return TransformResult("safe_dead_code_carrier", code, False, "no opening brace")
    if "rvd_dead_carrier" in code:
        return TransformResult("safe_dead_code_carrier", code, False, "dead-code carrier already present")
    payload = (
        "\nif (sizeof(int) == 0) { "
        "volatile int rvd_dead_carrier = 0; (void)rvd_dead_carrier; }\n"
    )
    transformed = code[: pos + 1] + payload + code[pos + 1 :]
    return TransformResult("safe_dead_code_carrier", transformed, True, "compile-time unreachable carrier inserted")


def code_normalization_abstraction(code: str) -> TransformResult:
    """Parenthesize simple return expressions as a normalization/abstraction."""
    pattern = re.compile(r"\breturn\s+(?P<expr>[^;\n{}]+);")

    def repl(match: re.Match[str]) -> str:
        expr = match.group("expr").strip()
        if expr.startswith("(") and expr.endswith(")"):
            return match.group(0)
        if "," in expr:
            return match.group(0)
        return f"return ({expr});"

    transformed, count = pattern.subn(repl, code, count=5)
    changed = transformed != code
    note = "parenthesized simple return expressions" if changed else "no simple return expression"
    return TransformResult("code_normalization_abstraction", transformed, changed, note)


TRANSFORMS = {
    "comment_banner": comment_banner,
    "blank_line_expansion": blank_line_expansion,
    "brace_line_shift": brace_line_shift,
    "dead_branch_after_opening_brace": dead_branch_after_opening_brace,
    "identifier_renaming": identifier_renaming,
    "control_flow_rewrite": control_flow_rewrite,
    "safe_dead_code_carrier": safe_dead_code_carrier,
    "code_normalization_abstraction": code_normalization_abstraction,
}


def apply_all(code: str, names: list[str] | None = None) -> list[TransformResult]:
    selected = names or list(TRANSFORMS)
    results: list[TransformResult] = []
    for name in selected:
        if name not in TRANSFORMS:
            raise KeyError(f"Unknown transformation: {name}")
        results.append(TRANSFORMS[name](code))
    return results

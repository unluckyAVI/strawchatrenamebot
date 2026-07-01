"""
Parser — now powered by the advanced autorename engine.
Kept for backward compatibility with existing code.
"""

from autorename import autorename, apply_template, build_filename, RenameResult

# Re-export for compatibility
ParsedFile = RenameResult


def parse_filename(raw: str) -> RenameResult:
    return autorename(raw)


def build_output_name(pf: RenameResult, template: str) -> str:
    return build_filename(pf.raw, template)


def apply_format(template: str, pf: RenameResult) -> str:
    return apply_template(template, pf)

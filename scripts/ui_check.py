#!/usr/bin/env python3
"""UI 시각 회귀 검증 (collaboration-prd.md R4 / §7-Q3).

표준 라이브러리만 사용. 수동 실행:

    python scripts/ui_check.py

검사 항목:
  A) 템플릿이 쓰는 class가 app.css에 정의돼 있는지            (차단)
  B) app.css에서 한 class가 2회 이상 정의됐는지 (중복 → drift) (차단)
  C) 토큰 정의부 밖에서 하드코딩 색상(#hex, rgb/rgba)을 쓰는지  (경고·비차단)

종료 코드: 차단(A·B) 위반이 있으면 1, 없으면 0.
정밀 파서가 아닌 휴리스틱이므로 오탐 가능 — PRD 방침대로 우선 수동 게이트.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "src" / "signal_program" / "web"
CSS_PATH = WEB / "static" / "css" / "app.css"
TEMPLATES = WEB / "templates"

# CSS에 정의되지 않아도 되는 클래스 (동적 부여·외부 관행·유틸)
CLASS_ALLOWLIST = {"on", "open", "dimmed", "running", "selected", "tab-active"}

# A검사 제외 템플릿: 클래스를 JS가 동적 생성하는 참조용 매크로 등
TEMPLATE_SKIP = {"partials/signal_card.html"}

# C검사: 순수 흑백(#fff/#000)은 토큰화 면제 (버튼 글자색 등 의도적 사용)
_WHITE_BLACK = re.compile(r"#(fff|000|ffffff|000000)\b", re.IGNORECASE)
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def defined_css_classes(css: str) -> list[str]:
    """셀렉터에 등장하는 .class-name 을 모두 수집 (정의 측)."""
    css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    selectors = []
    for chunk in re.split(r"\}", css_nc):
        head = chunk.split("{", 1)[0]
        selectors.append(head)
    sel_text = "\n".join(selectors)
    return re.findall(r"\.([A-Za-z][\w-]*)", sel_text)


def template_classes(html: str) -> set[str]:
    """class="..." 안의 토큰을 수집. Jinja2 표현식은 정적 토큰만 추출."""
    found: set[str] = set()
    for m in re.finditer(r'class="([^"]*)"', html):
        raw = m.group(1)
        raw = re.sub(r"\{\%.*?\%\}", " ", raw)
        raw = re.sub(r"\{\{.*?\}\}", " ", raw)
        for tok in raw.split():
            if tok and re.fullmatch(r"[A-Za-z][\w-]*", tok):
                found.add(tok)
    return found


def inline_style_classes(html: str) -> set[str]:
    """템플릿 내 <style>...</style> 블록에 정의된 클래스도 정의로 인정."""
    classes: set[str] = set()
    for block in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.DOTALL | re.IGNORECASE):
        classes.update(defined_css_classes(block))
    return classes


def check_a_template_classes_exist(css: str) -> list[str]:
    global_defined = set(defined_css_classes(css)) | CLASS_ALLOWLIST
    problems: list[str] = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        if tpl.relative_to(TEMPLATES).as_posix() in TEMPLATE_SKIP:
            continue
        html = read(tpl)
        # app.css 전역 정의 + 해당 템플릿의 인라인 <style> 정의
        defined = global_defined | inline_style_classes(html)
        used = template_classes(html)
        missing = sorted(c for c in used if c not in defined)
        for c in missing:
            problems.append(f"[A] {tpl.relative_to(WEB)}: class '.{c}' not in app.css")
    return problems


def check_b_duplicate_definitions(css: str) -> list[str]:
    """'.foo {' 형태로 단독 정의된 클래스가 2회 이상이면 경고.

    복합 셀렉터(.a .b, .a.b, .a:hover)는 제외하고 단순 단일 클래스 룰만 센다.
    """
    css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    counts: dict[str, int] = {}
    for m in re.finditer(r"(^|\})\s*\.([A-Za-z][\w-]*)\s*\{", css_nc):
        name = m.group(2)
        counts[name] = counts.get(name, 0) + 1
    return [f"[B] duplicate def: '.{n}' x{c}" for n, c in sorted(counts.items()) if c > 1]


def check_c_hardcoded_colors(css: str) -> list[str]:
    """토큰 정의 블록(:root, [data-theme]) 밖에서 색상 리터럴 사용 검출."""
    lines = css.splitlines()
    in_token_block = False
    depth = 0
    warnings: list[str] = []
    token_block_re = re.compile(r"^(:root|\[data-theme)")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if token_block_re.match(stripped):
            in_token_block = True
        if in_token_block:
            depth += line.count("{") - line.count("}")
            if depth <= 0 and "}" in line:
                in_token_block = False
                depth = 0
            continue
        if stripped.startswith("/*") or not stripped:
            continue
        if _COLOR_RE.search(line):
            without_wb = _WHITE_BLACK.sub("", line)
            if _COLOR_RE.search(without_wb):
                warnings.append(f"[C] {CSS_PATH.name}:{i}: hardcoded color -> use var(--token): {stripped[:70]}")
    return warnings


def main() -> int:
    if not CSS_PATH.exists():
        sys.stderr.write("app.css not found: %s\n" % CSS_PATH)
        return 2
    css = read(CSS_PATH)

    # A/B = blocking, C = warning (non-blocking; PRD section 7 Q3)
    blocking = []
    blocking += check_a_template_classes_exist(css)
    blocking += check_b_duplicate_definitions(css)
    warnings = check_c_hardcoded_colors(css)

    if warnings:
        print("WARN - hardcoded colors: %d (non-blocking)" % len(warnings))
        for w in warnings:
            print("  " + w)
        print("")

    if blocking:
        print("FAIL - blocking issues: %d" % len(blocking))
        for x in blocking:
            print("  " + x)
        return 1
    print("PASS - no blocking issues (A class-match / B duplicate-def).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

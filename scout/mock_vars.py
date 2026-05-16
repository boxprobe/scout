"""Mock variable registry — single source of truth for generation + detection.

Each MockVar defines:
- gen_expr: Python expression used by argus codegen (evaluates to str)
- detect_re: regex used by scout noise detector to recognize generated values

Adding a new $variable? Add it here. Both codegen and noise filtering
pick it up automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MockVar:
    key: str
    gen_expr: str
    detect_re: re.Pattern[str]


# -- Parametric generators (key includes size suffix like $name_8) -----------

_PARAMETRIC: list[tuple[re.Pattern[str], type]] = []


class _NameVar(MockVar):
    """$name or $name_N — generates "test-" + hex."""

    @staticmethod
    def match(key: str) -> MockVar | None:
        m = re.match(r"^\$name(?:_(\d+))?$", key)
        if not m:
            return None
        n = m.group(1) or "6"
        return MockVar(
            key=key,
            gen_expr=f'"test-" + secrets.token_hex({int(n) // 2 + 1})[:{n}]',
            detect_re=MOCK_DETECTORS["mock_name"],
        )


class _NumberVar(MockVar):
    """$number or $number_N or $number_N.F — generates random digits."""

    @staticmethod
    def match(key: str) -> MockVar | None:
        m = re.match(r"^\$number(?:_(\d+)(?:\.(\d+))?)?$", key)
        if not m:
            return None
        digits = int(m.group(1) or "6")
        frac = int(m.group(2) or "0")
        hi = 10**digits - 1
        lo = 10 ** (digits - 1) if digits > 1 else 0
        if frac == 0:
            gen = f"str(random.randint({lo}, {hi}))"
        else:
            frac_hi = 10**frac - 1
            gen = (
                f'str(random.randint({lo}, {hi})) + "." + '
                f"str(random.randint(0, {frac_hi})).zfill({frac})"
            )
        return MockVar(
            key=key,
            gen_expr=gen,
            detect_re=re.compile(""),  # not auto-detectable
        )


class _TextVar(MockVar):
    """$text or $text_N — generates raw hex string."""

    @staticmethod
    def match(key: str) -> MockVar | None:
        m = re.match(r"^\$text(?:_(\d+))?$", key)
        if not m:
            return None
        n = m.group(1) or "16"
        return MockVar(
            key=key,
            gen_expr=f"secrets.token_hex({int(n) // 2 + 1})[:{n}]",
            detect_re=re.compile(""),  # not auto-detectable
        )


PARAMETRIC_MATCHERS = [_NameVar.match, _NumberVar.match, _TextVar.match]

# -- Fixed generators -------------------------------------------------------

FIXED_VARS: dict[str, MockVar] = {}


def _fixed(key: str, gen_expr: str, detect_key: str) -> None:
    FIXED_VARS[key] = MockVar(
        key=key, gen_expr=gen_expr, detect_re=MOCK_DETECTORS.get(detect_key, re.compile(""))
    )


# -- Detection patterns (used by noise.py) -----------------------------------
# These cover the OUTPUT format of each generator.

MOCK_DETECTORS: dict[str, re.Pattern[str]] = {
    # test-{hex}, supports concatenation (e.g. $name + $name → test-abctest-def)
    "mock_name": re.compile(r"^(?:test-[0-9a-f]{4,})+$"),
    # test-{hex}@example.com
    "mock_email": re.compile(r"^test-[0-9a-f]+@example\.com$"),
    # $number and $text intentionally excluded — pure digits/hex cannot be
    # reliably distinguished from real data. Use diff_ignore.fields instead.
}

# Now register fixed generators (after MOCK_DETECTORS is defined)
_FIXED_DEFS: list[tuple[str, str, str]] = [
    ("$email", '"test-" + secrets.token_hex(4) + "@example.com"', "mock_email"),
    ("$uuid", "str(uuid.uuid4())", ""),
    ("$ts", "str(int(time.time()))", ""),
    ("$yyyy", "datetime.now().strftime('%Y')", ""),
    ("$mm", "datetime.now().strftime('%m')", ""),
    ("$dd", "datetime.now().strftime('%d')", ""),
    ("$hh", "datetime.now().strftime('%H')", ""),
    ("$mi", "datetime.now().strftime('%M')", ""),
    ("$ss", "datetime.now().strftime('%S')", ""),
    ("$yyyy-mm-dd", "datetime.now().strftime('%Y-%m-%d')", ""),
    ("$yyyymmdd", "datetime.now().strftime('%Y%m%d')", ""),
    ("$yymmdd", "datetime.now().strftime('%y%m%d')", ""),
]

for _k, _g, _d in _FIXED_DEFS:
    FIXED_VARS[_k] = MockVar(
        key=_k,
        gen_expr=_g,
        detect_re=MOCK_DETECTORS.get(_d, re.compile("")),
    )


def resolve_gen_expr(key: str) -> str | None:
    """Return the Python gen_expr for a $-generator key, or None if unknown.

    Checks fixed vars first, then parametric matchers.
    Used by argus codegen.
    """
    fixed = FIXED_VARS.get(key)
    if fixed:
        return fixed.gen_expr
    for matcher in PARAMETRIC_MATCHERS:
        var = matcher(key)
        if var:
            return var.gen_expr
    return None

"""COBOL OCCURS clause resolution engine.

Determines the relational migration strategy for a field node that bears an
OCCURS clause, based solely on the COBOL AST structure — occurrence counts,
bounds, hierarchy, child field layout, PIC/type information, and REDEFINES
interaction.  No field-name heuristics are used.

Resolution strategies
---------------------
INLINE_ARRAY
    The OCCURS structure can be represented as a PostgreSQL array column
    (e.g. ``INTEGER[]``, ``VARCHAR(10)[]``).  Applies only to simple fixed
    OCCURS on a single leaf field with a safe, uniform PIC type and a small,
    statically-known count (≤ 20).

CHILD_TABLE
    The OCCURS structure represents a repeating record (group with named
    sub-fields).  The relational representation is a separate child table
    keyed by ``(parent_pk, occurrence_index)``.  The parent table retains
    only the non-repeating fields.

REVIEW_REQUIRED
    The structure cannot be safely represented automatically.  This covers:
    - variable-length OCCURS (DEPENDING ON)
    - nested OCCURS (one or more children themselves have OCCURS)
    - OCCURS combined with REDEFINES (complex interaction)
    - very large fixed OCCURS (count > 200) where expansion would be unsafe
    - mixed-type children that cannot be unified into a single array element
    - any node without a resolvable fixed count

Result dictionary keys
----------------------
Every call to ``resolve()`` returns a dict with exactly these keys:

  strategy             str   INLINE_ARRAY | CHILD_TABLE | REVIEW_REQUIRED
  occurs_type          str   FIXED | VARIABLE | UNKNOWN
  min_occurs           int   lower bound (0 for VARIABLE, count for FIXED)
  max_occurs           int   upper bound (count for FIXED, None for VARIABLE)
  is_variable_length   bool  True when DEPENDING ON or bounds differ
  is_group             bool  True when the field has child sub-fields
  nesting_level        int   depth of nested OCCURS inside this subtree
  has_redefines        bool  True when this node or a child has REDEFINES
  child_pic_uniform    bool  True when all leaf children share the same PIC
  child_sql_type       str   The SQL array element type (INLINE_ARRAY only)
  confidence           str   HIGH | MEDIUM | LOW
  reason               str   Human-readable explanation
  needs_manual_review  bool  True when strategy == REVIEW_REQUIRED
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _node_dict(node: Any) -> Dict[str, Any]:
    """FieldSchema is the primary input; dicts remain a legacy adapter."""
    if isinstance(node, dict):
        return node
    if hasattr(node, "model_dump"):
        return node.model_dump()
    return {}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_occurs_value(occurs_raw: Any) -> Tuple[Optional[int], Optional[int], bool, bool]:
    """Parse the raw ``occurs`` field value into (min, max, is_variable, is_unknown).

    The ``occurs`` field in the AST can be:
    - an ``int``         e.g. ``10``                  → fixed, count=10
    - a string digit     e.g. ``"10"``                 → fixed, count=10
    - a string like      ``"10 TIMES"``                → fixed, count=10
    - a string like      ``"1 TO 10 DEPENDING ON X"``  → variable, min=1 max=10
    - a string like      ``"0 TO 50 DEPENDING ON N"``  → variable, min=0 max=50
    - any other string   e.g. ``"TIMES"``               → unknown
    - None / falsy                                       → unknown

    Returns:
        (min_count, max_count, is_variable_length, is_unknown)
    """
    if not occurs_raw and occurs_raw != 0:
        return (None, None, False, True)

    s = str(occurs_raw).strip().upper()

    # Variable: "m TO n DEPENDING ON ..."
    var_match = re.search(r"(\d+)\s+TO\s+(\d+)", s)
    if var_match:
        lo = int(var_match.group(1))
        hi = int(var_match.group(2))
        return (lo, hi, True, False)

    # Fixed: leading integer
    fixed_match = re.search(r"(\d+)", s)
    if fixed_match:
        n = int(fixed_match.group(1))
        return (n, n, False, False)

    return (None, None, False, True)


def _has_depending_on(occurs_raw: Any) -> bool:
    """Return True if the raw occurs value contains a DEPENDING ON clause."""
    if not occurs_raw:
        return False
    return "DEPENDING" in str(occurs_raw).upper()


def _collect_leaf_pics(node: Dict[str, Any]) -> List[str]:
    """Recursively collect PIC clauses from all leaf descendants."""
    pics: List[str] = []

    def walk(n: Dict[str, Any]) -> None:
        children = n.get("children") or []
        if not children:
            p = n.get("pic") or n.get("data_type") or ""
            if p and p.upper() not in ("GROUP", ""):
                pics.append(p.upper())
        else:
            for c in children:
                if isinstance(c, dict):
                    walk(c)

    walk(node)
    return pics


def _has_nested_occurs(node: Dict[str, Any], depth: int = 0) -> int:
    """Return the maximum OCCURS nesting depth inside ``node``'s subtree.

    The root node's own ``occurs`` counts as depth 1; any child with ``occurs``
    increments the depth further.  Returns 0 when no OCCURS is present inside
    the subtree (excluding the root node itself).
    """
    max_depth = 0
    for child in node.get("children") or []:
        if not isinstance(child, dict):
            continue
        child_depth = depth
        if child.get("occurs"):
            child_depth = depth + 1
        sub = _has_nested_occurs(child, child_depth)
        max_depth = max(max_depth, child_depth, sub)
    return max_depth


def _has_redefines_in_subtree(node: Dict[str, Any]) -> bool:
    """Return True if this node or any descendant carries a REDEFINES clause."""
    if node.get("redefines"):
        return True
    for child in node.get("children") or []:
        if isinstance(child, dict) and _has_redefines_in_subtree(child):
            return True
    return False


# Safe SQL array element types — only these PIC mappings are considered
# reliable enough for an INLINE_ARRAY representation.
_SAFE_ARRAY_PICS: Dict[str, str] = {
    # Alphanumeric / alphabetic  → VARCHAR(n)[]
    # Handled dynamically below
}

# Max fixed count for INLINE_ARRAY strategy (configurable threshold)
_INLINE_ARRAY_MAX_COUNT = 20

# Max fixed count before we consider the OCCURS unsafe to represent at all
_UNSAFE_COUNT_THRESHOLD = 200


def _pic_to_array_element_type(pic: str) -> Optional[str]:
    """Map a single PIC clause to its PostgreSQL array element type.

    Returns None when the PIC cannot be safely mapped to a scalar array element.
    """
    p = pic.upper().strip()

    # Alphanumeric / alphabetic
    if p.startswith(("X(", "A(")):
        m = re.search(r"[XA]\((\d+)\)", p)
        length = int(m.group(1)) if m else 1
        return f"VARCHAR({length})"
    if p.startswith("X"):
        return "VARCHAR(1)"
    if p.startswith("A"):
        return "VARCHAR(1)"

    # Numeric with implicit decimal
    if "V" in p:
        parts = p.split("V", 1)
        m1 = re.search(r"9\((\d+)\)", parts[0])
        l1 = int(m1.group(1)) if m1 else parts[0].count("9")
        m2 = re.search(r"9\((\d+)\)", parts[1])
        l2 = int(m2.group(1)) if m2 else parts[1].count("9")
        return f"NUMERIC({l1 + l2},{l2})"

    # COMP types
    if "COMP-3" in p or "PACKED-DECIMAL" in p:
        m = re.search(r"9\((\d+)\)", p)
        l = int(m.group(1)) if m else 4
        return f"NUMERIC({l},0)"
    if "COMP-1" in p:
        return "REAL"
    if "COMP-2" in p:
        return "DOUBLE PRECISION"
    if "COMP" in p or "BINARY" in p:
        m = re.search(r"9\((\d+)\)", p)
        l = int(m.group(1)) if m else 4
        if l <= 4:
            return "SMALLINT"
        if l <= 9:
            return "INTEGER"
        return "BIGINT"

    # Plain numeric
    if "9" in p:
        m = re.search(r"9\((\d+)\)", p)
        l = int(m.group(1)) if m else p.count("9")
        if l <= 4:
            return "SMALLINT"
        if l <= 9:
            return "INTEGER"
        if l <= 18:
            return "BIGINT"
        return f"NUMERIC({l},0)"

    return None  # unsupported


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class OccursResolutionEngine:
    """Resolve a COBOL OCCURS clause to a relational migration strategy.

    All methods are class methods — no instantiation required.

    Usage::

        result = OccursResolutionEngine.resolve(node)

    where ``node`` is the canonical dict representation of a COBOL field
    (as produced by ``canonical_structure._field()`` or ``_flatten_records``).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def resolve(cls, node: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve an OCCURS node into a strategy result dict.

        Parameters
        ----------
        node : dict
            The canonical field dict.  Must have an ``occurs`` key.
            May also have ``children``, ``pic``, ``redefines``, ``level``,
            ``length``.

        Returns
        -------
        dict with keys: strategy, occurs_type, min_occurs, max_occurs,
            is_variable_length, is_group, nesting_level, has_redefines,
            child_pic_uniform, child_sql_type, confidence, reason,
            needs_manual_review
        """
        node = _node_dict(node)
        if not node:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="UNKNOWN",
                min_occurs=None,
                max_occurs=None,
                is_variable_length=False,
                is_group=False,
                nesting_level=0,
                has_redefines=False,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason="Null or missing OCCURS node.",
            )

        # Authoritative FieldSchema stores bounds separately; legacy dicts may
        # only have the original ``occurs`` value.
        occurs_raw = node.get("occurs")
        min_c, max_c, is_variable, is_unknown = _parse_occurs_value(occurs_raw)
        if node.get("occurs_min") is not None:
            min_c = int(node["occurs_min"])
            max_c = int(node.get("occurs_max") or min_c)
            is_unknown = False
        has_odo = bool(node.get("occurs_depending_on"))

        is_group = bool(node.get("children"))
        nesting_level = _has_nested_occurs(node)
        has_redefines = _has_redefines_in_subtree(node)

        occurs_type = (
            "UNKNOWN" if is_unknown
            else "VARIABLE" if is_variable
            else "FIXED"
        )

        # ------------------------------------------------------------------
        # Rule V: OCCURS DEPENDING ON (variable length)
        # Cannot be safely represented without knowing the runtime count.
        # ------------------------------------------------------------------
        if is_variable or has_odo or _has_depending_on(occurs_raw):
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="VARIABLE",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=True,
                is_group=is_group,
                nesting_level=nesting_level,
                has_redefines=has_redefines,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    "OCCURS DEPENDING ON detected: variable-length repeating structure. "
                    "Runtime cardinality cannot be determined statically. "
                    "Manual review required to decide between a normalised child table "
                    "with a variable row count or a JSONB column."
                ),
            )

        # ------------------------------------------------------------------
        # Rule U: Unknown occurrence count
        # ------------------------------------------------------------------
        if is_unknown or min_c is None:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="UNKNOWN",
                min_occurs=None,
                max_occurs=None,
                is_variable_length=False,
                is_group=is_group,
                nesting_level=nesting_level,
                has_redefines=has_redefines,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    "OCCURS count could not be determined from available AST data. "
                    "Manual review required."
                ),
            )

        count = max_c  # fixed OCCURS: min == max

        # ------------------------------------------------------------------
        # Rule N: Nested OCCURS
        # One or more child fields also have OCCURS — multi-dimensional array.
        # Cannot be safely auto-mapped.
        # ------------------------------------------------------------------
        if nesting_level > 0:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=is_group,
                nesting_level=nesting_level,
                has_redefines=has_redefines,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    f"Nested OCCURS detected (nesting_level={nesting_level}). "
                    "Multi-dimensional repeating structures cannot be safely "
                    "auto-mapped to a relational schema. "
                    "Manual review required to flatten or model as JSONB."
                ),
            )

        # ------------------------------------------------------------------
        # Rule R: OCCURS combined with REDEFINES
        # This is already handled by RedefinesResolutionEngine (Rule 2 →
        # SEPARATE_TABLES).  When the OCCURS node itself has a REDEFINES
        # clause, or contains REDEFINES children, mark for review so that
        # the two engines do not produce conflicting metadata.
        # ------------------------------------------------------------------
        if has_redefines:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=is_group,
                nesting_level=nesting_level,
                has_redefines=True,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    "OCCURS node or its children contain a REDEFINES clause. "
                    "The REDEFINES interaction must be resolved first by "
                    "RedefinesResolutionEngine before an OCCURS strategy can be "
                    "determined. Manual review required."
                ),
            )

        # ------------------------------------------------------------------
        # Rule L: Very large fixed OCCURS (unsafe to auto-expand)
        # ------------------------------------------------------------------
        if count > _UNSAFE_COUNT_THRESHOLD:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=is_group,
                nesting_level=nesting_level,
                has_redefines=False,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    f"OCCURS count {count} exceeds the safe auto-mapping threshold "
                    f"({_UNSAFE_COUNT_THRESHOLD}). "
                    "Expansion would produce an unwieldy schema. "
                    "Manual review required — consider a child table or JSONB column."
                ),
            )

        # ------------------------------------------------------------------
        # Rule G: Group OCCURS (field with child sub-fields)
        # Repeated record — the relational representation is a child table.
        # ------------------------------------------------------------------
        if is_group:
            leaf_pics = _collect_leaf_pics(node)
            uniform, common_type = cls._check_pic_uniformity(leaf_pics)
            return cls._result(
                strategy="CHILD_TABLE",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=True,
                nesting_level=nesting_level,
                has_redefines=False,
                child_pic_uniform=uniform,
                child_sql_type=common_type,
                confidence="HIGH" if count <= 100 else "MEDIUM",
                reason=(
                    f"Fixed group OCCURS (count={count}): the repeating group contains "
                    f"{len(leaf_pics)} leaf field(s) and represents a normalised "
                    "child entity. Recommended representation: a separate child table "
                    "with (parent_pk, occurrence_index) composite key. "
                    "Occurrence count and child structure are statically determinable."
                ),
            )

        # ------------------------------------------------------------------
        # Rule A: Simple fixed OCCURS on a leaf field
        # The field itself has no children — it is a scalar repeated N times.
        # ------------------------------------------------------------------
        # Determine the PIC clause for the leaf (the node itself is the leaf)
        pic = node.get("pic") or node.get("data_type") or ""
        if not pic or pic.upper() == "GROUP":
            # No PIC — cannot determine element type
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=False,
                nesting_level=0,
                has_redefines=False,
                child_pic_uniform=False,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    "Simple fixed OCCURS leaf field has no resolvable PIC clause. "
                    "Cannot determine element type for array mapping. "
                    "Manual review required."
                ),
            )

        if node.get("pic_category"):
            from src.validators.postgres_mapper import PostgresMapper
            element_type = PostgresMapper.map_parsed_field(node)[0]
        else:
            element_type = _pic_to_array_element_type(pic)
        if element_type is None:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=False,
                nesting_level=0,
                has_redefines=False,
                child_pic_uniform=True,
                child_sql_type=None,
                confidence="LOW",
                reason=(
                    f"PIC '{pic}' on simple fixed OCCURS leaf cannot be mapped to a "
                    "safe PostgreSQL array element type. Manual review required."
                ),
            )

        if count <= _INLINE_ARRAY_MAX_COUNT:
            return cls._result(
                strategy="INLINE_ARRAY",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=False,
                nesting_level=0,
                has_redefines=False,
                child_pic_uniform=True,
                child_sql_type=f"{element_type}[]",
                confidence="HIGH",
                reason=(
                    f"Simple fixed OCCURS on scalar leaf (count={count}, "
                    f"PIC={pic}). "
                    f"Recommended representation: PostgreSQL array column "
                    f"``{element_type}[]``. "
                    "Count is small and statically known; element type is uniform."
                ),
            )
        else:
            # count > _INLINE_ARRAY_MAX_COUNT but <= _UNSAFE_COUNT_THRESHOLD
            # Still representable as CHILD_TABLE (one row per occurrence)
            return cls._result(
                strategy="CHILD_TABLE",
                occurs_type="FIXED",
                min_occurs=min_c,
                max_occurs=max_c,
                is_variable_length=False,
                is_group=False,
                nesting_level=0,
                has_redefines=False,
                child_pic_uniform=True,
                child_sql_type=element_type,
                confidence="MEDIUM",
                reason=(
                    f"Simple fixed OCCURS on scalar leaf (count={count}, PIC={pic}). "
                    f"Count exceeds the inline-array threshold ({_INLINE_ARRAY_MAX_COUNT}). "
                    "Recommended representation: a child table with "
                    "(parent_pk, occurrence_index, value) columns."
                ),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _check_pic_uniformity(cls, pics: List[str]) -> Tuple[bool, Optional[str]]:
        """Check whether all PIC clauses in a list map to the same SQL type.

        Returns (is_uniform, common_sql_type).
        ``common_sql_type`` is None when pics is empty or types are mixed.
        """
        if not pics:
            return (False, None)
        types = [_pic_to_array_element_type(p) for p in pics]
        # Filter out unmappable ones
        valid = [t for t in types if t is not None]
        if not valid:
            return (False, None)
        unique = set(valid)
        if len(unique) == 1:
            return (True, unique.pop())
        return (False, None)

    @classmethod
    def _result(
        cls,
        *,
        strategy: str,
        occurs_type: str,
        min_occurs: Optional[int],
        max_occurs: Optional[int],
        is_variable_length: bool,
        is_group: bool,
        nesting_level: int,
        has_redefines: bool,
        child_pic_uniform: bool,
        child_sql_type: Optional[str],
        confidence: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Build a canonical result dict with all required keys present."""
        return {
            "strategy": strategy,
            "occurs_type": occurs_type,
            "min_occurs": min_occurs,
            "max_occurs": max_occurs,
            "is_variable_length": is_variable_length,
            "is_group": is_group,
            "nesting_level": nesting_level,
            "has_redefines": has_redefines,
            "child_pic_uniform": child_pic_uniform,
            "child_sql_type": child_sql_type,
            "confidence": confidence,
            "reason": reason,
            "needs_manual_review": strategy == "REVIEW_REQUIRED",
        }

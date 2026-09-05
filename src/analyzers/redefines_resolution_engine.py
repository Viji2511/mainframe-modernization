from typing import Dict, Any, List, Optional


def _node_dict(node: Any) -> Optional[Dict[str, Any]]:
    """Accept FieldSchema directly while retaining legacy-dict callers."""
    if node is None:
        return None
    if isinstance(node, dict):
        return node
    if hasattr(node, "model_dump"):
        return node.model_dump()
    return None


# ---------------------------------------------------------------------------
# Helper: PIC clause length computation (self-contained, no external deps)
# ---------------------------------------------------------------------------

def _pic_byte_length(pic: Optional[str]) -> int:
    """Return the byte storage length of a PIC clause.

    Handles:
      - X(n), A(n), 9(n), S9(n)
      - V   (implicit decimal — no extra storage)
      - COMP-1 (4), COMP-2 (8)
      - COMP / BINARY  (2/4/8 based on digit count)
      - COMP-3 / PACKED-DECIMAL  (ceil((digits+1)/2))
    """
    import re, math

    if not pic:
        return 0
    p = pic.upper().strip()

    # Binary float
    if "COMP-1" in p:
        return 4
    if "COMP-2" in p:
        return 8

    # Strip sign, decimal indicators for digit counting
    digits_only = re.sub(r"[SsVv]", "", p)
    digit_m = re.findall(r"9\((\d+)\)|9", digits_only)
    digit_count = sum(int(g) if g else 1 for g in digit_m)

    if "COMP-3" in p or "PACKED-DECIMAL" in p:
        return math.ceil((digit_count + 1) / 2)

    if "COMP" in p or "BINARY" in p:
        if digit_count <= 4:
            return 2
        if digit_count <= 9:
            return 4
        return 8

    # Alphanumeric / alphabetic / numeric display
    char_m = re.findall(r"[XxAa]\((\d+)\)|[XxAa]", p)
    char_count = sum(int(g) if g else 1 for g in char_m)
    if char_count:
        return char_count

    return digit_count


def _compute_node_length(node: Dict[str, Any]) -> int:
    """Return the byte length of a node, computing from children when absent."""
    if node is None:
        return 0
    explicit = node.get("byte_length") if node.get("byte_length") is not None else node.get("length")
    if explicit:
        return int(explicit)

    children = node.get("children") or []
    if children:
        # Sum children that are not themselves REDEFINES (they share storage)
        seen_offsets: set = set()
        total = 0
        for c in children:
            if c.get("redefines"):
                # Redefining child uses already-counted storage — skip
                continue
            clen = _compute_node_length(c)
            total += clen
        return total

    return _pic_byte_length(node.get("pic"))


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class RedefinesResolutionEngine:
    """Resolve a COBOL REDEFINES pair into a relational migration strategy.

    Strategies (preserved from original + new):
      SAME_TABLE               — simple scalar type-cast; single column retained
      ALTERNATE_REPRESENTATION — alternate group provides meaningful child fields
                                 that can be safely represented as annotated columns
      SEPARATE_TABLES          — alternate layout represents a distinct logical entity
      REVIEW_REQUIRED          — structural ambiguity; mark for manual review

    New output keys (added alongside existing keys):
      alternate_representation : bool  — True when the redefining structure is a
                                         meaningful decomposition of the original field
      safe_children            : list  — leaf child fields judged safe to represent
                                         as relational columns (empty unless
                                         alternate_representation is True)
      original_field_name      : str   — name of the canonical (original) field
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def resolve(cls, original_node: Dict[str, Any], redefining_node: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a REDEFINES relationship.

        Returns a dict with keys:
          strategy, confidence, reason, storage_overlap,
          alternate_representation, safe_children, original_field_name
        """
        original_node, redefining_node = _node_dict(original_node), _node_dict(redefining_node)
        if not original_node or not redefining_node:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                confidence="LOW",
                reason="Missing original or redefining node data.",
                storage_overlap=False,
            )

        orig_stats = cls._analyze_structure(original_node)
        alt_stats = cls._analyze_structure(redefining_node)

        orig_len = orig_stats.get("total_length") or 0
        alt_len = alt_stats.get("total_length") or 0

        # When explicit lengths are absent, recompute from children / PIC
        if not orig_len:
            orig_len = _compute_node_length(original_node)
            orig_stats["total_length"] = orig_len
        if not alt_len:
            alt_len = _compute_node_length(redefining_node)
            alt_stats["total_length"] = alt_len

        storage_overlap = orig_len == alt_len and orig_len > 0

        original_name = original_node.get("name", "")

        # ------------------------------------------------------------------
        # Rule 1: Nested REDEFINES inside the alternate structure
        #         — cannot determine storage layout reliably
        # ------------------------------------------------------------------
        if alt_stats.get("redefines_count", 0) > 0:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                confidence="LOW",
                reason=(
                    "Nested REDEFINES detected. Storage overlap and semantic "
                    "interpretation cannot be determined reliably from available evidence."
                ),
                storage_overlap=storage_overlap,
                original_field_name=original_name,
            )

        # ------------------------------------------------------------------
        # Rule 2: OCCURS inside alternate structure
        #         — distinct repeating entity
        # ------------------------------------------------------------------
        if alt_stats.get("occurs_count", 0) > 0 or alt_stats.get("occurs_depending_on"):
            if redefining_node.get("node_id"):
                return cls._result(
                    strategy="REVIEW_REQUIRED",
                    confidence="LOW",
                    reason=(
                        "Authoritative REDEFINES hierarchy contains OCCURS. The mutually exclusive "
                        "storage layout cannot safely be transformed into a child table automatically."
                    ),
                    storage_overlap=storage_overlap,
                    original_field_name=original_name,
                )
            return cls._result(
                strategy="SEPARATE_TABLES",
                confidence="MEDIUM",
                reason=(
                    "Redefined structure contains an independent nested repeating group "
                    "and represents a distinct logical layout."
                ),
                storage_overlap=storage_overlap,
                original_field_name=original_name,
            )

        # ------------------------------------------------------------------
        # Rule 3: Simple scalar redefines (both nodes have at most 1 leaf)
        #         — direct type-cast, single column
        # ------------------------------------------------------------------
        if orig_stats.get("field_count", 0) <= 1 and alt_stats.get("field_count", 0) <= 1:
            return cls._result(
                strategy="SAME_TABLE",
                confidence="HIGH",
                reason=(
                    "Simple scalar REDEFINES with identical storage length; "
                    "no independent entity or repeating structure detected."
                ),
                storage_overlap=storage_overlap,
                original_field_name=original_name,
            )

        # ------------------------------------------------------------------
        # Rule 4 (NEW): Alternate representation
        #   The original field is a scalar (or small group) and the redefining
        #   node provides a meaningful decomposition of that same storage into
        #   named child fields (e.g. BIRTHDATE → B-M, FILLER, B-D, FILLER, B-Y).
        #
        #   Conditions (all AST/structural, no name heuristics):
        #     a) The redefining node has children (it is a group)
        #     b) The alternate group does NOT introduce more storage than the
        #        original (storage_overlap or alt_len <= orig_len when one side
        #        lacks explicit length)
        #     c) At least one child carries a concrete PIC clause
        #        (i.e. it is not purely structural filler)
        #     d) The redefining node itself has no independent OCCURS
        #        (already excluded by Rule 2)
        #     e) The original is either a scalar leaf OR a small group
        #        (field_count <= 5) — large-vs-large is handled by Rule 5
        #     f) The alternate group is not itself very large (field_count <= 12)
        # ------------------------------------------------------------------
        alt_has_children = bool(redefining_node.get("children"))
        lengths_compatible = (
            storage_overlap
            or (orig_len > 0 and alt_len > 0 and alt_len <= orig_len)
            or (orig_len == 0 or alt_len == 0)  # unknown — give benefit of doubt
        )

        if (
            alt_has_children
            and lengths_compatible
            and orig_stats.get("field_count", 0) <= 5
            and alt_stats.get("field_count", 0) <= 12
        ):
            safe_children = cls._extract_safe_children(redefining_node)
            if safe_children:
                return cls._result(
                    strategy="ALTERNATE_REPRESENTATION",
                    confidence="HIGH" if storage_overlap else "MEDIUM",
                    reason=(
                        "The redefining structure provides a named decomposition of the "
                        "original field's storage. The original field is retained as the "
                        "canonical column; meaningful child fields are preserved as "
                        "annotated alternate-representation columns sharing the same "
                        "physical storage. No duplicate table is created."
                    ),
                    storage_overlap=storage_overlap,
                    alternate_representation=True,
                    safe_children=safe_children,
                    original_field_name=original_name,
                )

        # ------------------------------------------------------------------
        # Rule 5: Large complex REDEFINES on both sides
        #         — entirely alternative record layout
        # ------------------------------------------------------------------
        if alt_stats.get("field_count", 0) > 5 and orig_stats.get("field_count", 0) > 5:
            return cls._result(
                strategy="SEPARATE_TABLES",
                confidence="MEDIUM",
                reason="Large redefined group suggests a completely alternative record layout.",
                storage_overlap=storage_overlap,
                original_field_name=original_name,
            )

        # ------------------------------------------------------------------
        # Rule 6 (NEW): Group redefines a scalar (or vice-versa) but safe
        #               child extraction found nothing useful
        #               — retain original; mark alternate for review
        # ------------------------------------------------------------------
        if alt_has_children and orig_stats.get("field_count", 0) <= 1:
            return cls._result(
                strategy="REVIEW_REQUIRED",
                confidence="LOW",
                reason=(
                    "The redefining structure decomposes a scalar field but no safely "
                    "mappable child fields were found (possible FILLER-only or "
                    "unsafe PIC clauses). Marked for manual review."
                ),
                storage_overlap=storage_overlap,
                original_field_name=original_name,
            )

        # ------------------------------------------------------------------
        # Default fallback (preserves original behavior)
        # ------------------------------------------------------------------
        return cls._result(
            strategy="SAME_TABLE",
            confidence="HIGH",
            reason="Simple alternate representation of the same storage.",
            storage_overlap=storage_overlap,
            original_field_name=original_name,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _result(
        cls,
        *,
        strategy: str,
        confidence: str,
        reason: str,
        storage_overlap: bool,
        alternate_representation: bool = False,
        safe_children: Optional[List[Dict[str, Any]]] = None,
        original_field_name: str = "",
    ) -> Dict[str, Any]:
        """Construct a canonical result dict, always including all keys."""
        return {
            "strategy": strategy,
            "confidence": confidence,
            "reason": reason,
            "storage_overlap": storage_overlap,
            "alternate_representation": alternate_representation,
            "safe_children": safe_children or [],
            "original_field_name": original_field_name,
        }

    @classmethod
    def _extract_safe_children(cls, redefining_node: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return leaf children that carry a concrete PIC clause and are not FILLER.

        Each returned dict is a copy of the child node augmented with:
          - _safe_to_map : True
          - _byte_length : computed byte length
          - _byte_offset : byte offset relative to the redefining node's start

        Only immediate and direct-descendant leaf nodes are considered.
        Nodes that are themselves group containers are skipped; nodes named
        FILLER or with no PIC clause are omitted.

        We deliberately do NOT apply name-based heuristics beyond skipping
        FILLER — the structural criterion (has a PIC, is a leaf, fits within
        the storage) is sufficient.
        """
        children = redefining_node.get("children") or []
        safe: List[Dict[str, Any]] = []
        offset = 0

        for child in children:
            if not isinstance(child, dict):
                continue

            child_name = (child.get("name") or "").upper()

            # Recurse into non-leaf group children to collect their leaves
            child_children = child.get("children") or []
            if child_children:
                # Group node — collect leaves from it recursively
                sub_safe = cls._extract_safe_children(child)
                # Offset them relative to this parent
                for s in sub_safe:
                    s = dict(s)
                    s["_byte_offset"] = offset + s.get("_byte_offset", 0)
                    safe.append(s)
                group_len = _compute_node_length(child)
                if not child.get("redefines"):
                    offset += group_len
                continue

            # Leaf node: must have a PIC clause
            pic = child.get("pic") or child.get("data_type") or ""
            if not pic or pic.upper() in ("GROUP", ""):
                continue

            byte_len = _compute_node_length(child)

            # Skip zero-length leaves (unusual but guard against bad data)
            if byte_len == 0:
                continue

            entry = dict(child)
            entry["_safe_to_map"] = (child_name != "FILLER")
            entry["_byte_length"] = byte_len
            entry["_byte_offset"] = offset

            safe.append(entry)

            # Only advance offset for non-REDEFINES leaves
            if not child.get("redefines"):
                offset += byte_len

        # Return only the truly safe-to-map leaves (skip FILLER)
        return [s for s in safe if s.get("_safe_to_map")]

    @classmethod
    def _analyze_structure(cls, node: Dict[str, Any]) -> Dict[str, Any]:
        """Collect structural statistics for a field node."""
        node_len = (node.get("byte_length") if node and node.get("byte_length") is not None
                    else node.get("length") if node and node.get("length") is not None else 0)
        stats = {
            "field_count": 0,
            "occurs_count": 0,
            "redefines_count": 0,
            "occurs_depending_on": False,
            "total_length": node_len,
        }

        if not node:
            return stats

        def traverse(n: Dict[str, Any]) -> None:
            if not isinstance(n, dict):
                return
            children = n.get("children", [])
            if not children:
                stats["field_count"] += 1
            if n.get("occurs") or n.get("occurs_min"):
                stats["occurs_count"] += 1
                if n.get("occurs_depending_on") or "DEPENDING" in str(n.get("occurs")).upper():
                    stats["occurs_depending_on"] = True
            if n.get("redefines"):
                stats["redefines_count"] += 1
            for c in children:
                if isinstance(c, dict):
                    traverse(c)

        traverse(node)

        # The redefining root's own 'redefines' key is not a "nested" REDEFINES
        if node.get("redefines"):
            stats["redefines_count"] -= 1

        return stats

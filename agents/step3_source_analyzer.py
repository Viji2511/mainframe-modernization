import re
import os
from agents.base_agent import BaseAgent
from models.schemas import VSAMDataset, CopyBook, SourceCodeAnalysis, BusinessRule, Inventory

SYSTEM_PROMPT_TEMPLATE = """
You are a {language} source code analyst. Given a {language} program and its VSAM dataset
context, extract structured information. Return ONLY valid JSON:

{{
  "program_name": "<name>",
  "vsam_dsn": "<dsn>",
  "operations": ["READ", "WRITE"],
  "key_fields": ["FIELD-A"],
  "business_rules": [
    {{
      "field_name": "<name>",
      "usage": "<key|lookup|validation|relationship|output|other>",
      "description": "<one sentence>",
      "found_in": "<program name>"
    }}
  ],
  "related_files": ["OTHER-DSN"]
}}

Rules:
- operations: only verbs actually seen in the source code (e.g. {verbs_hint}).
- key_fields: fields used in key access or index lookups.
- business_rules: focus on validation conditional checks, meaningful assignments, and loop logic.
- Return ONLY the JSON.
"""

class SourceCodeAnalyzerAgent(BaseAgent):
    """
    Analyzes application source files (COBOL, PL/I, Natural, RPG) to detect where and how
    a VSAM dataset is used, extracting access verbs, key fields, and business rules.
    """

    def __init__(self):
        super().__init__("SourceCodeAnalyzerAgent")

    def _extract_program_name(self, source: str, language: str) -> str:
        if language == "COBOL":
            m = re.search(r"PROGRAM-ID\.\s+([A-Z0-9_-]+)", source, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        elif language == "PL/I":
            m = re.search(r"([A-Z0-9_-]+)\s*:\s*PROCEDURE", source, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        elif language == "Natural":
            # Natural program name is usually based on file name or line comments
            m = re.search(r"\bPROGRAM-ID\s+([A-Z0-9_-]+)", source, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        elif language == "RPG":
            m = re.search(r"\bCTL-OPT\s+DFTACTGRP\s*\(.*?\)\s*ACTGRP\s*\(\s*'([A-Z0-9_-]+)'\s*\)", source, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        return "UNKNOWN"

    def _program_uses_dsn(self, source: str, dsn: str, prog_name: str, copybook: CopyBook) -> bool:
        # 1. Try mapping segments to the program prefixes (specific heuristic)
        segments = [s for s in dsn.split(".") if s not in ("AWS", "M2", "VSAM", "KSDS", "PS", "CARDDEMO")]
        segment_to_programs = {
            "ACCTDATA": ["CBACT01", "CBACT04"],
            "CARDDATA": ["CBACT02"],
            "CARDXREF": ["CBACT03"],
            "CUSTDATA": ["CBCUS01"],
            "TRANSACT": ["CBTRN01", "CBTRN02", "CBTRN03"],
        }
        for seg in segments:
            allowed = segment_to_programs.get(seg.upper(), [])
            for p in allowed:
                if p in prog_name.upper():
                    return True

        # 2. Match by copying/including the matched copybook
        if copybook and copybook.filename != "NOT_FOUND":
            cb_base = os.path.splitext(copybook.filename)[0].upper()
            # COBOL COPY, PL/I %INCLUDE, RPG /COPY
            if re.search(rf"\b(?:COPY|%INCLUDE|/COPY|/INCLUDE)\s+{re.escape(cb_base)}\b", source, re.IGNORECASE):
                return True

        # 3. Match DSN segment directly in SELECT/FD or OPEN FILE statements
        for seg in segments:
            # Check for SELECT/ASSIGN statements
            if re.search(rf"\bASSIGN\s+TO\s+{re.escape(seg[:-4] if seg.endswith('DATA') else seg)}", source, re.IGNORECASE):
                return True
            if re.search(rf"\b{re.escape(seg)}\b", source, re.IGNORECASE):
                return True

        return False

    def _extract_operations(self, source: str, language: str) -> list[str]:
        ops = set()
        
        # Check CICS calls first
        cics_verbs = ["READ", "WRITE", "REWRITE", "DELETE"]
        for cv in cics_verbs:
            if re.search(rf"EXEC\s+CICS\s+{cv}\b", source, re.IGNORECASE):
                ops.add(f"EXEC CICS {cv}")

        # Check native verbs
        if language == "COBOL":
            verbs = ["READ", "WRITE", "REWRITE", "DELETE", "START"]
            for v in verbs:
                if re.search(rf"^\s+{v}\b", source, re.MULTILINE | re.IGNORECASE):
                    ops.add(v)
        elif language == "PL/I":
            verbs = ["READ", "WRITE", "REWRITE", "DELETE"]
            for v in verbs:
                if re.search(rf"\b{v}\s+FILE\b", source, re.IGNORECASE):
                    ops.add(f"{v} FILE")
        elif language == "Natural":
            verbs = ["READ", "STORE", "UPDATE", "DELETE", "FIND", "GET"]
            for v in verbs:
                if re.search(rf"\b{v}\b", source, re.IGNORECASE):
                    ops.add(v)
        elif language == "RPG":
            verbs = ["chain", "read", "reade", "update", "write", "delete"]
            for v in verbs:
                if re.search(rf"\b{v}\b", source, re.IGNORECASE):
                    ops.add(v.upper())

        return sorted(list(ops))

    def run(self, vsam: VSAMDataset, copybook: CopyBook, inventory: Inventory) -> list[SourceCodeAnalysis]:
        results = []
        field_names = [f.name for f in copybook.fields] if copybook else []

        # Determine target file mapping based on detected language
        files_to_scan = {}
        if inventory.detected_language == "COBOL":
            files_to_scan = inventory.cobol_files
        elif inventory.detected_language == "PL/I":
            files_to_scan = inventory.pli_files
        elif inventory.detected_language == "Natural":
            files_to_scan = inventory.natural_files
        elif inventory.detected_language == "RPG":
            files_to_scan = inventory.rpg_files
        else:
            # Mixed language: scan everything
            files_to_scan = {
                **inventory.cobol_files,
                **inventory.pli_files,
                **inventory.natural_files,
                **inventory.rpg_files
            }

        # Verbs hint string for prompt formatting
        verbs_hint_map = {
            "COBOL": "READ, WRITE, REWRITE, DELETE, START",
            "PL/I": "READ FILE, WRITE FILE, REWRITE FILE, DELETE FILE",
            "Natural": "READ, STORE, UPDATE, DELETE, FIND, GET",
            "RPG": "CHAIN, READ, READE, UPDATE, WRITE, DELETE",
            "Mixed": "READ, WRITE, REWRITE, DELETE"
        }
        lang = inventory.detected_language
        verbs_hint = verbs_hint_map.get(lang, verbs_hint_map["Mixed"])

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=lang, verbs_hint=verbs_hint)

        for filename, source in files_to_scan.items():
            base_name = os.path.splitext(os.path.basename(filename))[0].upper()
            prog_name = self._extract_program_name(source, lang)
            if prog_name == "UNKNOWN":
                prog_name = base_name

            if not self._program_uses_dsn(source, vsam.dsn, prog_name, copybook):
                continue

            ops_hint = self._extract_operations(source, lang)

            user_msg = f"""
Program   : {prog_name}
Language  : {lang}
VSAM DSN  : {vsam.dsn}
Known fields: {field_names[:100]}  # Limit field context size

Pre-detected operations: {ops_hint}

=== PROGRAM SOURCE ===
{source[:6000]}
{"...(truncated)" if len(source) > 6000 else ""}

Analyze and return JSON.
"""
            data = self._ask_json(system_prompt, user_msg)

            if data.get("_parse_error"):
                results.append(SourceCodeAnalysis(
                    program_name=prog_name,
                    vsam_dsn=vsam.dsn,
                    operations=ops_hint,
                    key_fields=[],
                    business_rules=[],
                    related_files=[],
                ))
                continue

            rules = [BusinessRule(**r) for r in data.get("business_rules", []) if isinstance(r, dict)]
            results.append(SourceCodeAnalysis(
                program_name=data.get("program_name", prog_name),
                vsam_dsn=data.get("vsam_dsn", vsam.dsn),
                operations=data.get("operations", ops_hint),
                key_fields=data.get("key_fields", []),
                business_rules=rules,
                related_files=data.get("related_files", []),
            ))

        return results

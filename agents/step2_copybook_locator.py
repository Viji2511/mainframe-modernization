import os
import re
from agents.base_agent import BaseAgent
from models.schemas import VSAMDataset, CopyBook, COBOLField, Inventory

COBOL_PROMPT = """
You are a COBOL copybook parser. Given raw COBOL copybook text, extract all
field definitions and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<PIC clause or null>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Include ALL levels (01, 05, 10, 15, etc.).
- 01-level group items have pic=null.
- Children list always set to [].
- Return ONLY the JSON, no extra text.
"""

PLI_PROMPT = """
You are a PL/I copybook / DCLGEN structure parser. Given raw PL/I declarations,
extract all field definitions (DECLARE/DCL blocks) and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<Picture or type string>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Include ALL level numbers.
- Map PL/I types to cobol_type equivalents (e.g. CHAR to DISPLAY, BIN FIXED/FLOAT to COMP/COMP-1, DECIMAL FIXED to COMP-3).
- Return ONLY the JSON, no extra text.
"""

NATURAL_PROMPT = """
You are a Natural DDM structure parser. Given raw Natural DDM/record fields,
extract all field definitions and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<Type description>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Map Natural formats (A for DISPLAY, N or P for COMP-3, I or F for COMP) to cobol_type equivalents.
- Return ONLY the JSON, no extra text.
"""

RPG_PROMPT = """
You are an RPG D-spec structure parser. Given raw RPG D-spec lines,
extract all field definitions and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<Type description>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Map RPG types (A for DISPLAY, S/P for COMP-3, I/F for COMP) to cobol_type equivalents.
- Return ONLY the JSON, no extra text.
"""

ASSEMBLER_PROMPT = """
You are an Assembler DSECT parser. Given raw Assembler DSECT declarations,
extract all field definitions and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<Type description>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Map Assembler types (C for DISPLAY, P for COMP-3, F/H for COMP) to cobol_type equivalents.
- Return ONLY the JSON, no extra text.
"""

_FILENAME_HINTS = {
    "cvact01": "ACCTDATA",
    "cvact02": "CARDDATA",
    "cvact03": "CARDXREF",
    "cvcus01": "CUSTDATA",
    "cvtra05": "TRANSACT",
    "cvtra06": "DALYTRAN",
    "acct":    "ACCTDATA",
    "cust":    "CUSTDATA",
    "card":    "CARDDATA",
    "xref":    "CARDXREF",
    "tran":    "TRANSACT",
    "bill":    "BILLING",
}

class CopyBookLocatorAgent(BaseAgent):
    """
    Matches the schema/copybook file representing the record layout of a VSAM Dataset,
    supporting COBOL, PL/I, Natural, RPG, and Assembler formats.
    """

    def __init__(self):
        super().__init__("CopyBookLocatorAgent")

    def _guess_dsn_match(self, filename: str) -> str | None:
        fn = filename.lower()
        for key, dsn_part in _FILENAME_HINTS.items():
            if key in fn:
                return dsn_part
        return None

    def _find_copybook_for_dsn(self, files: dict, dsn: str) -> tuple[str | None, str | None]:
        # Pull all meaningful segments from DSN
        # e.g. AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS → ['ACCTDATA']
        segments = [s for s in dsn.split(".") if s not in ("AWS", "M2", "VSAM", "KSDS", "PS", "CARDDEMO")]

        # Pass 1: filename contains a DSN segment
        for fname, content in files.items():
            fn_upper = os.path.splitext(fname)[0].upper()
            for seg in segments:
                if seg in fn_upper:
                    return fname, content

        # Pass 2: content references a DSN segment
        for fname, content in files.items():
            for seg in segments:
                if re.search(rf"\b{re.escape(seg)}\b", content, re.IGNORECASE):
                    return fname, content

        # Pass 3: filename hint map
        for fname, content in files.items():
            hint = self._guess_dsn_match(fname)
            if hint and any(hint in seg for seg in segments):
                return fname, content

        # Pass 4: LLM fallback logic
        if files:
            candidates_snippet = "\n".join(
                f"- {fname}: {content[:100]}..."
                for fname, content in list(files.items())[:20]  # Limit candidates
            )
            prompt = f"""
Given the VSAM dataset DSN '{dsn}' and a list of copybook filenames and snippets:
{candidates_snippet}

Which copybook filename best represents the record layout schema for this dataset?
Return ONLY the filename (exactly as listed) and nothing else. If none match, return "NONE".
"""
            decision = self._ask("", prompt).strip()
            # Verify selection exists in candidates
            for fname, content in files.items():
                if fname.lower() in decision.lower() or decision.lower() in fname.lower():
                    return fname, content

        return None, None

    def run(self, inventory: Inventory, vsam: VSAMDataset) -> CopyBook:
        fname, raw = self._find_copybook_for_dsn(inventory.copybook_files, vsam.dsn)

        if fname is None:
            return CopyBook(filename="NOT_FOUND", dsn_match=vsam.dsn, fields=[], raw_text="", language="UNKNOWN")

        # Sniff language of matched copybook file
        ext = os.path.splitext(fname.lower())[1]
        language = "COBOL"
        prompt = COBOL_PROMPT

        if ext in ('.pli', '.pl1', '.inc', '.dcl') or any(m in raw.upper() for m in ("DCL ", "DECLARE ")):
            language = "PL/I"
            prompt = PLI_PROMPT
        elif ext in ('.nsl', '.ddm') or "DEFINE DATA" in raw.upper():
            language = "Natural"
            prompt = NATURAL_PROMPT
        elif ext in ('.rpg', '.rpgle') or "dcl-ds" in raw.lower():
            language = "RPG"
            prompt = RPG_PROMPT
        elif ext in ('.asm', '.s') or "DSECT" in raw.upper():
            language = "Assembler"
            prompt = ASSEMBLER_PROMPT

        user_msg = f"""
VSAM DSN  : {vsam.dsn}
Language  : {language}
Copybook  : {fname}

=== COPYBOOK TEXT ===
{raw}

Parse every field definition from this copybook structure.
"""
        data = self._ask_json(prompt, user_msg)

        if data.get("_parse_error"):
            fields = []
        else:
            fields = [COBOLField(**f) for f in data.get("fields", [])]

        return CopyBook(filename=fname, dsn_match=vsam.dsn, fields=fields, raw_text=raw, language=language)

import re
import csv
import io
from abc import ABC, abstractmethod
from agents.base_agent import BaseAgent
from models.schemas import VSAMDataset, VSAMType, Inventory

SYSTEM_PROMPT = """
You are a mainframe VSAM expert. Given raw configuration documents (LISTCAT, JCL, CSV metadata, or program source),
extract VSAM dataset metadata. Return ONLY a valid JSON object with these keys:

{
  "dsn": "<dataset name>",
  "vsam_type": "<KSDS|ESDS|RRDS|LDS|UNKNOWN>",
  "record_length": <integer or null>,
  "key_length": <integer or null>,
  "key_offset": <integer or null>,
  "ci_size": <integer or null>,
  "record_count": <integer or null>,
  "source_jcl": "<filename or null>",
  "notes": "<any important observation>"
}

Rules:
- dsn must be the fully-qualified dataset name.
- vsam_type must be one of KSDS, ESDS, RRDS, LDS, UNKNOWN.
- Use null for fields not found in the input.
- Return ONLY the JSON, no explanation.
"""

class DiscoveryStrategy(ABC):
    @abstractmethod
    def discover(self, dsn: str, inventory: Inventory, agent: BaseAgent) -> VSAMDataset | None:
        pass

class ListcatDiscoveryStrategy(DiscoveryStrategy):
    def _pre_parse_listcat(self, listcat_text: str) -> dict:
        hints = {}
        for line in listcat_text.splitlines():
            u = line.upper()
            if "CLUSTER" in u and "-" in line:
                m = re.search(r"([A-Z0-9#$@][A-Z0-9.#$@]{1,43})", line)
                if m:
                    hints["dsn_hint"] = m.group(1)
            if "LRECL" in u:
                m = re.search(r"LRECL[- ]+(\d+)", u)
                if m:
                    hints["record_length"] = int(m.group(1))
            if "KEYLEN" in u or "KEY-LEN" in u:
                m = re.search(r"KEY[- ]?LEN[- ]+(\d+)", u)
                if m:
                    hints["key_length"] = int(m.group(1))
            if "KEYOFF" in u or "KEY-OFF" in u:
                m = re.search(r"KEY[- ]?OFF[- ]+(\d+)", u)
                if m:
                    hints["key_offset"] = int(m.group(1))
            if "CISIZE" in u or "CI-SIZE" in u:
                m = re.search(r"CI[- ]?SIZE[- ]+(\d+)", u)
                if m:
                    hints["ci_size"] = int(m.group(1))
            if "REC-TOTAL" in u:
                m = re.search(r"REC[- ]?TOTAL[- ]+(\d+)", u)
                if m:
                    hints["record_count"] = int(m.group(1))
            for vtype in ["KSDS", "ESDS", "RRDS", "LDS"]:
                if vtype in u:
                    hints["vsam_type"] = vtype
        return hints

    def _filter_listcat(self, listcat_text: str, target_dsn: str) -> str:
        if not listcat_text or not target_dsn:
            return ""
        
        lines = listcat_text.splitlines()
        blocks = []
        current_block = []
        
        for line in lines:
            upper_line = line.strip().upper()
            if upper_line.startswith(("0CLUSTER", "0NONVSAM", "0DATA", "0INDEX", "0PATH", "0GDG", "0AIX")):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)
                
        if current_block:
            blocks.append(current_block)
            
        filtered_blocks = []
        target_clean = target_dsn.strip().upper()
        for block in blocks:
            block_text = "\n".join(block)
            if target_clean in block_text.upper():
                filtered_blocks.append(block_text)
                
        return "\n\n".join(filtered_blocks)

    def discover(self, dsn: str, inventory: Inventory, agent: BaseAgent) -> VSAMDataset | None:
        listcat_matches = []
        for fname, content in inventory.listcat_files.items():
            filtered = self._filter_listcat(content, dsn)
            if filtered:
                listcat_matches.append((fname, filtered))

        if listcat_matches:
            fname, text = listcat_matches[0]
            hints = self._pre_parse_listcat(text)
            
            user_msg = f"""
Target DSN: {dsn}
Source File: {fname}

=== LISTCAT PORTION ===
{text}

=== PRE-PARSED HINTS (regex pass) ===
{hints}

Extract VSAM dataset metadata for {dsn}.
"""
            data = agent._ask_json(SYSTEM_PROMPT, user_msg)
            if data.get("_parse_error"):
                return VSAMDataset(
                    dsn=dsn,
                    vsam_type=VSAMType(hints.get("vsam_type", "UNKNOWN")),
                    record_length=hints.get("record_length"),
                    key_length=hints.get("key_length"),
                    key_offset=hints.get("key_offset"),
                    ci_size=hints.get("ci_size"),
                    record_count=hints.get("record_count"),
                    notes="Failed LLM parse; filled via regex hints only.",
                    confidence=0.9
                )
            
            return VSAMDataset(
                dsn=data.get("dsn", dsn),
                vsam_type=VSAMType(data.get("vsam_type", hints.get("vsam_type", "UNKNOWN"))),
                record_length=data.get("record_length") or hints.get("record_length"),
                key_length=data.get("key_length") or hints.get("key_length"),
                key_offset=data.get("key_offset") or hints.get("key_offset"),
                ci_size=data.get("ci_size") or hints.get("ci_size"),
                record_count=data.get("record_count") or hints.get("record_count"),
                source_jcl=data.get("source_jcl"),
                notes=data.get("notes", ""),
                confidence=1.0
            )
        return None

class MetadataDiscoveryStrategy(DiscoveryStrategy):
    def _first_int_match(self, row_dict: dict, match_keys: list[str]) -> int | None:
        for k, v in row_dict.items():
            k_u = k.upper().strip()
            if any(mk in k_u for mk in match_keys):
                try:
                    cleaned = re.sub(r'[^\d]', '', str(v))
                    if cleaned:
                        return int(cleaned)
                except ValueError:
                    pass
        return None

    def discover(self, dsn: str, inventory: Inventory, agent: BaseAgent) -> VSAMDataset | None:
        for fname, content in inventory.metadata_files.items():
            reader = csv.reader(io.StringIO(content))
            headers = []
            for row in reader:
                if not row:
                    continue
                if not headers:
                    headers = [h.upper().strip() for h in row]
                    continue
                
                if any(dsn in val.upper() for val in row):
                    row_dict = dict(zip(headers, row))
                    
                    lrecl = self._first_int_match(row_dict, ["LRECL", "RECORD LENGTH", "RECORD_LENGTH", "LENGTH"])
                    keylen = self._first_int_match(row_dict, ["KEYLEN", "KEY LENGTH", "KEY_LENGTH", "KEY LEN"])
                    keyoff = self._first_int_match(row_dict, ["KEYOFF", "KEY OFFSET", "KEY_OFFSET", "KEY OFF"])
                    cisize = self._first_int_match(row_dict, ["CISIZE", "CI SIZE", "CI_SIZE", "CI"])
                    recs = self._first_int_match(row_dict, ["REC-TOTAL", "RECORDS", "RECORD COUNT", "COUNT"])
                    
                    vtype = "UNKNOWN"
                    for k, val in row_dict.items():
                        if "TYPE" in k:
                            val_u = val.upper()
                            for vt in ["KSDS", "ESDS", "RRDS", "LDS"]:
                                if vt in val_u:
                                    vtype = vt
                                    break
                    
                    return VSAMDataset(
                        dsn=dsn,
                        vsam_type=VSAMType(vtype),
                        record_length=lrecl,
                        key_length=keylen,
                        key_offset=keyoff,
                        ci_size=cisize,
                        record_count=recs,
                        notes=f"Extracted from metadata file: {fname}",
                        confidence=0.9
                    )
        return None

class JCLDiscoveryStrategy(DiscoveryStrategy):
    def discover(self, dsn: str, inventory: Inventory, agent: BaseAgent) -> VSAMDataset | None:
        jcl_matches = []
        for fname, content in inventory.jcl_files.items():
            if dsn in content.upper():
                jcl_matches.append((fname, content))

        if jcl_matches:
            fname, content = jcl_matches[0]
            define_block = ""
            m = re.search(rf"(DEFINE\s+CLUSTER\s*\(.*?NAME\({re.escape(dsn)}\).*?\))", content, re.DOTALL | re.IGNORECASE)
            if m:
                define_block = m.group(1)

            user_msg = f"""
Target DSN: {dsn}
Source JCL: {fname}

=== JCL EXTRACT ===
{define_block or content[:4000]}

Extract VSAM dataset metadata from this JCL config.
"""
            data = agent._ask_json(SYSTEM_PROMPT, user_msg)
            if not data.get("_parse_error"):
                return VSAMDataset(
                    dsn=data.get("dsn", dsn),
                    vsam_type=VSAMType(data.get("vsam_type", "UNKNOWN")),
                    record_length=data.get("record_length"),
                    key_length=data.get("key_length"),
                    key_offset=data.get("key_offset"),
                    ci_size=data.get("ci_size"),
                    record_count=data.get("record_count"),
                    source_jcl=fname,
                    notes=data.get("notes", "Extracted from JCL"),
                    confidence=0.8
                )
        return None

class SourceDiscoveryStrategy(DiscoveryStrategy):
    def discover(self, dsn: str, inventory: Inventory, agent: BaseAgent) -> VSAMDataset | None:
        source_matches = []
        for list_files in (inventory.cobol_files, inventory.pli_files, inventory.natural_files, inventory.rpg_files):
            for fname, content in list_files.items():
                dsn_tail = dsn.split(".")[-1]
                if dsn_tail.upper() in content.upper():
                    source_matches.append((fname, content[:4000]))

        if source_matches:
            fname, snippet = source_matches[0]
            user_msg = f"""
Target DSN: {dsn}
Matching Program Source: {fname}

=== SOURCE CODE SNIPPET ===
{snippet}

Infer the VSAM dataset attributes based on variables and definitions referencing {dsn}.
"""
            data = agent._ask_json(SYSTEM_PROMPT, user_msg)
            if not data.get("_parse_error"):
                return VSAMDataset(
                    dsn=data.get("dsn", dsn),
                    vsam_type=VSAMType(data.get("vsam_type", "UNKNOWN")),
                    record_length=data.get("record_length"),
                    key_length=data.get("key_length"),
                    key_offset=data.get("key_offset"),
                    source_jcl=None,
                    notes=data.get("notes", f"Inferred from source: {fname}"),
                    confidence=0.5
                )
        return None


class VSAMDiscoveryAgent(BaseAgent):
    """
    Discovers VSAM dataset metadata dynamically from LISTCAT outputs,
    JCL configurations, CSV/Excel metadata sheets, or source code.
    Utilizes a Strategy Pattern to iteratively test resolution paths.
    """

    def __init__(self):
        super().__init__("VSAMDiscoveryAgent")
        self.strategies = [
            ListcatDiscoveryStrategy(),
            MetadataDiscoveryStrategy(),
            JCLDiscoveryStrategy(),
            SourceDiscoveryStrategy()
        ]

    @staticmethod
    def _pre_parse_listcat(listcat_text: str) -> dict:
        return ListcatDiscoveryStrategy()._pre_parse_listcat(listcat_text)

    def run(self, inventory: Inventory, target_dsn: str = None) -> list[VSAMDataset]:
        datasets = []
        candidates = inventory.vsam_dsn_candidates
        if target_dsn:
            candidates = [c for c in candidates if target_dsn.upper() in c.upper()]
            if not candidates:
                candidates = [target_dsn.upper()]

        for dsn in candidates:
            dataset = None
            for strategy in self.strategies:
                dataset = strategy.discover(dsn, inventory, self)
                if dataset:
                    datasets.append(dataset)
                    break
            
            if not dataset:
                datasets.append(VSAMDataset(
                    dsn=dsn,
                    vsam_type=VSAMType.UNKNOWN,
                    notes="No logs, configs, or source references found to resolve metadata.",
                    confidence=0.2
                ))

        return datasets

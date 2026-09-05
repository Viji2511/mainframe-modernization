import re
from typing import List, Tuple
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence


def _get_logical_lines(content: str) -> List[Tuple[int, str]]:
    """Combines JCL continuation lines into single logical statements."""
    logical_lines = []
    current_line = ""
    start_line_num = 1
    
    for i, line in enumerate(content.splitlines(), start=1):
        stripped = line.rstrip()
        
        # Skip pure JCL comments
        if stripped.startswith("//*"):
            continue
            
        # Non-JCL lines (like instream data)
        if not stripped.startswith("//"):
            if current_line:
                logical_lines.append((start_line_num, current_line))
                current_line = ""
            logical_lines.append((i, stripped))
            continue
            
        # Strip trailing comments. In JCL, parameters end at the first blank space after the operator.
        # But for simplicity, we look for commas to determine continuation.
        if current_line:
            # continuation line: strip the "//" and leading spaces
            text = stripped[2:].lstrip()
            current_line += " " + text
        else:
            current_line = stripped
            start_line_num = i
            
        # If the line ends with a comma, it is continued
        # (JCL allows comments after the comma, but standard format puts comma at the end)
        if not current_line.rstrip().endswith(","):
            logical_lines.append((start_line_num, current_line))
            current_line = ""
            
    if current_line:
        logical_lines.append((start_line_num, current_line))
        
    return logical_lines


def _keyword_value(line: str, keyword: str):
    # Matches KEYWORD=VALUE or KEYWORD=(VAL1,VAL2)
    # Also handles KEYWORD='...' strings
    match = re.search(rf"\b{keyword}\s*=\s*('[^']*'|\([^)]*\)|[^,\s]+)", line, re.IGNORECASE)
    if match:
        val = match.group(1)
        if val.startswith("'") and val.endswith("'"):
            return val[1:-1]
        return val
    return None


class DDExtractor(BaseExtractor):
    target_artifact_type = "JCL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        """Extract DD statements while retaining their JCL source scope.

        DD concatenation is expressed by an unnamed DD statement immediately
        following a named DD.  It belongs to that DD, rather than being an
        independent DD named ``CONCAT``.
        """
        evidence_list = []
        dd_pattern = re.compile(r'^//(?P<name>[A-Z0-9#$@]{0,8})\s+DD\b(?P<params>.*)', re.IGNORECASE)
        job_pattern = re.compile(r'^//[A-Z0-9#$@]+\s+JOB\b', re.IGNORECASE)
        exec_pattern = re.compile(r'^//(?P<name>[A-Z0-9#$@]+)\s+EXEC\b', re.IGNORECASE)
        current_step = None
        current_dd = None
        concat_position = 0
        pending_dd = None

        def emit_pending_dd():
            nonlocal pending_dd
            if pending_dd is None:
                return
            params = pending_dd["params"].strip()
            props = dict(pending_dd["properties"])
            dsn = _keyword_value(params, "DSN") or _keyword_value(params, "DSNAME")
            if dsn:
                props["dataset"] = dsn
                if dsn.startswith("&&"):
                    props["temporary"] = True

            disp = _keyword_value(params, "DISP")
            if disp:
                props["disp"] = disp
                disp_upper = disp.upper()
                if "NEW" in disp_upper or "MOD" in disp_upper:
                    props["type"] = "OUTPUT"
                elif "SHR" in disp_upper or "OLD" in disp_upper:
                    props["type"] = "INPUT"

            for key, keyword in (("space", "SPACE"), ("unit", "UNIT"), ("dcb", "DCB"), ("volume", "VOL")):
                value = _keyword_value(params, keyword)
                if value:
                    props[key] = value
            if "SYSOUT=" in params.upper():
                props["sysout"] = _keyword_value(params, "SYSOUT") or "*"
            if "DUMMY" in params.upper():
                props["dummy"] = True
            if params == "*":
                props["instream"] = True

            value = dsn or props.get("sysout") or ("DUMMY" if props.get("dummy") else "INSTREAM" if props.get("instream") else "UNKNOWN")
            evidence_list.append(Evidence(
                artifact_type="JCL",
                entity_type="DatasetBinding",
                entity_name=pending_dd["name"],
                evidence_type="DD",
                value=value,
                properties=props,
                severity="PRIMARY",
                source_file=file_path,
                source_line=pending_dd["source_line"],
                parser_name="JCLParser",
                parser_version="1.0.0"
            ))
            pending_dd = None

        def begin_dd(line_number, stated_name, params):
            nonlocal current_dd, concat_position, pending_dd
            is_concatenation = not stated_name and current_dd is not None
            dd_name = current_dd["name"] if is_concatenation else stated_name
            if not dd_name:
                # Malformed unnamed DD: retain it as evidence but never invent
                # a synthetic DD name.
                dd_name = "UNNAMED"
            if is_concatenation:
                concat_position += 1
            else:
                concat_position = 0
                current_dd = {"name": dd_name}
            pending_dd = {
                "name": dd_name,
                "source_line": line_number,
                "params": params,
                "properties": {
                    "dd_name": dd_name,
                    "scope": "step" if current_step else "job",
                    "step_name": current_step,
                    "is_concatenation": is_concatenation,
                    "position": concat_position,
                },
            }

        for line_number, source_line in enumerate(content.splitlines(), start=1):
            line = source_line.rstrip()
            if not line.startswith("//") or line.startswith("//*"):
                emit_pending_dd()
                continue

            if job_pattern.match(line):
                emit_pending_dd()
                current_step = None
                current_dd = None
                continue

            exec_match = exec_pattern.match(line)
            if exec_match:
                emit_pending_dd()
                current_step = exec_match.group("name").upper()
                current_dd = None
                continue

            match = dd_pattern.match(line)
            if match:
                emit_pending_dd()
                begin_dd(line_number, match.group("name").strip().upper(), match.group("params").strip())
                continue

            # Continuation cards omit the DD keyword and are only part of the
            # current DD while its parameter list ends in a comma.
            continuation = line[2:]
            if pending_dd is not None and pending_dd["params"].rstrip().endswith(",") and continuation[:1].isspace():
                pending_dd["params"] += " " + continuation.strip()
                continue

            emit_pending_dd()
            # A new JCL control statement ends any possible DD concatenation.
            if line[2:].strip():
                current_dd = None
        emit_pending_dd()
        return evidence_list


class ExecExtractor(BaseExtractor):
    """Extract programs invoked by JCL EXEC statements."""
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^//([A-Z0-9#$@]+)?\s+EXEC\s+(.*)', re.IGNORECASE)
        pgm_pattern = re.compile(r'(?:PGM|PROC)\s*=\s*([A-Z0-9#$@]+)', re.IGNORECASE)
        
        for i, line in _get_logical_lines(content):
            match = pattern.search(line)
            if match:
                step_name = (match.group(1) or "UNASSIGNED").strip().upper()
                params_str = match.group(2)
                
                pgm_match = pgm_pattern.search(params_str)
                kind = "PROC" if "PROC=" in params_str.upper() else "PGM"
                pgm_name = pgm_match.group(1).upper() if pgm_match else "UNKNOWN"
                
                props = {"step_name": step_name, "kind": kind}
                
                parm = _keyword_value(line, "PARM")
                if parm: props["parm"] = parm
                
                cond = _keyword_value(line, "COND")
                if cond: props["cond"] = cond
                
                region = _keyword_value(line, "REGION")
                if region: props["region"] = region

                evidence_list.append(Evidence(
                    artifact_type="JCL",
                    entity_type="Program",
                    entity_name=pgm_name,
                    evidence_type="EXEC",
                    value=pgm_name,
                    properties=props,
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="JCLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list


class JobCardExtractor(BaseExtractor):
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^//([A-Z0-9#$@]+)\s+JOB\s+(.*)', re.IGNORECASE)
        for i, line in _get_logical_lines(content):
            match = pattern.search(line)
            if match:
                evidence_list.append(Evidence(
                    artifact_type="JCL", entity_type="Job", entity_name=match.group(1).upper(),
                    evidence_type="JOB", value=match.group(2).strip(), properties={"job_card": match.group(2).strip()},
                    severity="PRIMARY", source_file=file_path, source_line=i,
                    parser_name="JCLParser", parser_version="1.0.0"
                ))
                break
        return evidence_list


class SymbolicParameterExtractor(BaseExtractor):
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        for i, line in _get_logical_lines(content):
            for parameter in sorted(set(re.findall(r'&([A-Z][A-Z0-9#$@]*)', line, re.IGNORECASE))):
                evidence_list.append(Evidence(
                    artifact_type="JCL", entity_type="SymbolicParameter", entity_name=parameter.upper(),
                    evidence_type="SYMBOL", value=parameter.upper(), properties={}, severity="SUPPORTING",
                    source_file=file_path, source_line=i, parser_name="JCLParser", parser_version="1.0.0"
                ))
        return evidence_list

class JCLParser(BaseParser):
    artifact_type = "JCL"

    def get_extractors(self) -> List[BaseExtractor]:
        return [
            JobCardExtractor(),
            ExecExtractor(),
            DDExtractor(),
            SymbolicParameterExtractor()
        ]

import os
import re
import csv
import zipfile
import tempfile
import openpyxl
from models.schemas import Inventory

class FileIngestionAgent:
    """
    Ingests, extracts (if zipped), walks, and classifies mainframe-related source files,
    logs, configurations, and metadata spreadsheets into a structured Inventory schema.
    """

    def __init__(self):
        pass

    def ingest(self, input_path: str) -> Inventory:
        """
        Accepts a directory path or a .zip file path. Recursively classifies every file and
        extracts potential VSAM DSN candidates.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input path does not exist: {input_path}")

        # If it's a zip file, extract it to a temporary directory
        if os.path.isfile(input_path) and zipfile.is_zipfile(input_path):
            temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            inventory = self._scan_directory(temp_dir)
            inventory.input_dir = input_path  # Keep original path
            return inventory
        elif os.path.isdir(input_path):
            return self._scan_directory(input_path)
        else:
            raise ValueError(f"Input path must be a directory or a valid zip file: {input_path}")

    def _scan_directory(self, directory: str) -> Inventory:
        cobol_files = {}
        pli_files = {}
        natural_files = {}
        rpg_files = {}
        jcl_files = {}
        copybook_files = {}
        listcat_files = {}
        metadata_files = {}
        other_files = {}

        # Walk recursively
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, directory)
                ext = os.path.splitext(file)[1].lower()

                # Read spreadsheet or text
                if ext in ('.xlsx', '.xls'):
                    try:
                        content = self._parse_excel(file_path)
                        metadata_files[rel_path] = content
                    except Exception as e:
                        other_files[rel_path] = f"Error reading excel: {e}"
                elif ext == '.csv':
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        metadata_files[rel_path] = content
                    except Exception as e:
                        other_files[rel_path] = f"Error reading csv: {e}"
                else:
                    # Text/Code file classification
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        
                        classification = self._sniff_file(rel_path, content)
                        if classification == 'cobol':
                            cobol_files[rel_path] = content
                        elif classification == 'pli':
                            pli_files[rel_path] = content
                        elif classification == 'natural':
                            natural_files[rel_path] = content
                        elif classification == 'rpg':
                            rpg_files[rel_path] = content
                        elif classification == 'jcl':
                            jcl_files[rel_path] = content
                        elif classification == 'copybook':
                            copybook_files[rel_path] = content
                        elif classification == 'listcat':
                            listcat_files[rel_path] = content
                        else:
                            other_files[rel_path] = content
                    except Exception as e:
                        # Log binary or unreadable files under other_files
                        other_files[rel_path] = f"Unreadable file: {e}"

        # Sniff overall language
        lang_counts = {
            "COBOL": len(cobol_files),
            "PL/I": len(pli_files),
            "Natural": len(natural_files),
            "RPG": len(rpg_files)
        }
        total_lang_files = sum(lang_counts.values())
        detected_language = "Mixed"
        if total_lang_files > 0:
            for lang, count in lang_counts.items():
                if count / total_lang_files >= 0.8:
                    detected_language = lang
                    break
        elif len(copybook_files) > 0:
            # Fall back to copybook extensions if no programs exist
            ext_counts = [os.path.splitext(f)[1].lower() for f in copybook_files.keys()]
            if any(e in ('.pli', '.inc', '.dcl') for e in ext_counts):
                detected_language = "PL/I"
            elif any(e in ('.ddm', '.nsl') for e in ext_counts):
                detected_language = "Natural"
            else:
                detected_language = "COBOL"

        # DSN candidates extraction
        dsn_candidates = self._extract_dsn_candidates(jcl_files, listcat_files, metadata_files)

        return Inventory(
            input_dir=directory,
            cobol_files=cobol_files,
            pli_files=pli_files,
            natural_files=natural_files,
            rpg_files=rpg_files,
            jcl_files=jcl_files,
            copybook_files=copybook_files,
            listcat_files=listcat_files,
            metadata_files=metadata_files,
            other_files=other_files,
            detected_language=detected_language,
            vsam_dsn_candidates=dsn_candidates
        )

    def _sniff_file(self, rel_path: str, content: str) -> str:
        """Classify file type by extension and content analysis."""
        fn = rel_path.lower()
        ext = os.path.splitext(fn)[1]

        # 1. LISTCAT Sniffing
        if ext in ('.txt', '.lst', '.log', '.out') and any(m in content.upper() for m in ("CLUSTER", "NONVSAM", "IDCAMS", "LISTCAT")):
            if "LISTING FROM CATALOG" in content.upper() or "REC-TOTAL" in content.upper() or "VOLSER" in content.upper():
                return 'listcat'

        # 2. JCL Sniffing
        if ext in ('.jcl', '.job', '.cntl') or content.startswith("//") or "EXEC PGM=" in content.upper():
            return 'jcl'

        # 3. Copybooks are includes by contract, even when a procedure
        # copybook happens to mention "PROCEDURE DIVISION" in its comments.
        # Classifying those files as programs loses their copybook identity
        # before the parser and Structure Viewer ever see them.
        if ext in ('.cpy', '.copy'):
            return 'copybook'

        # 4. COBOL Sniffing
        if ext in ('.cbl', '.cob', '.cobol') or any(m in content.upper() for m in ("IDENTIFICATION DIVISION", "PROCEDURE DIVISION", "DATA DIVISION")):
            return 'cobol'

        # 5. PL/I Sniffing
        if ext in ('.pli', '.pl1', '.inc', '.dcl') or "PROCEDURE OPTIONS(MAIN)" in content.upper() or "DCL " in content.upper() or "DECLARE " in content.upper():
            if ext in ('.inc', '.dcl') or not any(m in content.upper() for m in ("IDENTIFICATION DIVISION", "PROCEDURE DIVISION")):
                # PL/I copybook vs program
                if "DCL " in content.upper() or "DECLARE " in content.upper():
                    return 'copybook'
            return 'pli'

        # 6. Natural Sniffing
        if ext in ('.nsl', '.nsn', '.nsp', '.nsa', '.ddm') or "DEFINE DATA" in content.upper():
            if ext == '.ddm' or "DEFINE DATA PARAMETER" in content.upper():
                return 'copybook'
            return 'natural'

        # 7. RPG Sniffing
        if ext in ('.rpg', '.rpgle', '.sqlrpgle') or any(m in content.lower() for m in ("dcl-s ", "dcl-f ", "dcl-ds ", "dcl-proc ")):
            return 'rpg'

        # 8. Other copybook/include files
        if ext == '.h':
            return 'copybook'

        return 'other'

    def _parse_excel(self, file_path: str) -> str:
        """Parses active Excel sheet rows into a CSV-formatted string."""
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for r in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in r):
                row_str = ",".join(str(cell) if cell is not None else "" for cell in r)
                rows.append(row_str)
        return "\n".join(rows)

    def _extract_dsn_candidates(self, jcl_files: dict, listcat_files: dict, metadata_files: dict) -> list[str]:
        candidates = set()
        
        # DSN pattern regex
        dsn_pattern = re.compile(r'\b(?:DSN|DSNAME)\s*=\s*([A-Z0-9#$@][A-Z0-9.#$@]{1,43})', re.IGNORECASE)
        listcat_cluster_pattern = re.compile(r'(?:CLUSTER|NONVSAM)\s+-+\s+([A-Z0-9#$@][A-Z0-9.#$@]{1,43})', re.IGNORECASE)

        # 1. Extract from JCLs
        for content in jcl_files.values():
            for m in dsn_pattern.finditer(content):
                dsn = m.group(1).upper()
                if not dsn.startswith("&"):  # Exclude temporary JCL datasets
                    candidates.add(dsn)

        # 2. Extract from LISTCAT
        for content in listcat_files.values():
            for m in listcat_cluster_pattern.finditer(content):
                candidates.add(m.group(1).upper())

        # 3. Extract from metadata csv/excel files
        for content in metadata_files.values():
            # Extract anything that matches a typical qualified dataset name structure (A.B.C)
            # DSNs must have 2 to 6 qualifiers separated by dots, where each qualifier is 1-8 chars
            potential_dsns = re.findall(r'\b[A-Z0-9#$@]{1,8}(?:\.[A-Z0-9#$@]{1,8}){2,5}\b', content, re.IGNORECASE)
            for dsn in potential_dsns:
                # Basic check: exclude qualifiers that are all digits (like dates) or have no letters
                qualifiers = dsn.split(".")
                if any(re.search(r'[A-Z#$@]', q, re.IGNORECASE) for q in qualifiers):
                    candidates.add(dsn.upper())

        # Deduplicate and sort
        return sorted(list(candidates))

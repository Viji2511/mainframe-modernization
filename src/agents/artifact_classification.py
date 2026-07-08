import os
from src.metadata.schemas import Inventory

class ArtifactClassificationAgent:
    """
    Deterministically classifies artifacts based on extension and content signature.
    Produces a categorized Inventory.
    """
    def classify(self, raw_files: dict[str, str], input_dir: str) -> Inventory:
        inventory = Inventory(input_dir=input_dir)
        
        for rel_path, content in raw_files.items():
            classification = self._sniff_file(rel_path, content)
            
            if classification == 'cobol':
                inventory.cobol_files[rel_path] = content
            elif classification == 'pli':
                inventory.pli_files[rel_path] = content
            elif classification == 'natural':
                inventory.natural_files[rel_path] = content
            elif classification == 'rpg':
                inventory.rpg_files[rel_path] = content
            elif classification == 'jcl':
                inventory.jcl_files[rel_path] = content
            elif classification == 'copybook':
                inventory.copybook_files[rel_path] = content
            elif classification == 'listcat':
                inventory.listcat_files[rel_path] = content
            elif classification == 'metadata':
                inventory.metadata_files[rel_path] = content
            else:
                inventory.other_files[rel_path] = content
                
        # Set overall language detection logic
        cobol_count = len(inventory.cobol_files)
        if cobol_count > 0:
            inventory.detected_language = "COBOL"
        else:
            inventory.detected_language = "Mixed"
            
        return inventory

    def _sniff_file(self, rel_path: str, content: str) -> str:
        fn = rel_path.lower()
        ext = os.path.splitext(fn)[1]
        
        # CSV/Excel metadata
        if ext in ('.csv', '.xlsx', '.xls'):
            return 'metadata'

        # LISTCAT Sniffing
        if ext in ('.txt', '.lst', '.log', '.out') and any(m in content.upper() for m in ("CLUSTER", "NONVSAM", "IDCAMS", "LISTCAT")):
            return 'listcat'

        # JCL Sniffing
        if ext in ('.jcl', '.job', '.cntl') or content.startswith("//") or "EXEC PGM=" in content.upper():
            return 'jcl'

        # COBOL Sniffing
        if ext in ('.cbl', '.cob', '.cobol') or any(m in content.upper() for m in ("IDENTIFICATION DIVISION", "PROCEDURE DIVISION", "DATA DIVISION")):
            return 'cobol'

        # Copybook
        if ext in ('.cpy', '.copy', '.h'):
            return 'copybook'

        return 'other'

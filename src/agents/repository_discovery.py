import os
import zipfile
import tempfile
from src.security.safety import SecurityValidationError, safe_extract_zip

class RepositoryDiscoveryAgent:
    """
    Walks a repository and discovers all files. 
    Unzips archives if necessary. Does NO classification or parsing.
    Produces a raw dictionary of filepath -> content.
    """
    
    def discover(self, input_path: str) -> dict[str, str]:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
            
        target_dir = input_path
        
        # Unzip if necessary
        if os.path.isfile(input_path) and zipfile.is_zipfile(input_path):
            temp_dir = tempfile.mkdtemp()
            try:
                safe_extract_zip(input_path, temp_dir)
            except SecurityValidationError:
                # Do not leave partial untrusted extraction behind.
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise
            target_dir = temp_dir
            
        raw_files = {}
        for root, _, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, target_dir)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        raw_files[rel_path] = f.read()
                except Exception as e:
                    # Ignore unreadable/binary files for now
                    pass
                    
        return raw_files

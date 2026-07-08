from abc import ABC, abstractmethod
from typing import Any, List, Dict

class ASTParser(ABC):
    """
    Abstract Base Class for Tree-Sitter based AST Parsers.
    
    As the framework matures, regex-based parsing should be replaced 
    by deterministic Abstract Syntax Tree parsing using Tree-Sitter grammars 
    for COBOL, PL/I, RPG, Natural, and Assembler.
    
    Implementations of this class will parse a given source file into an AST, 
    allowing querying of logical blocks (e.g., FD blocks, Paragraphs, Statements) 
    without arbitrary string manipulation.
    """

    @abstractmethod
    def parse(self, source_code: str) -> Any:
        """
        Parses the raw source code and returns the root AST node.
        """
        pass

    @abstractmethod
    def find_file_descriptors(self, ast_root: Any) -> List[Dict[str, Any]]:
        """
        Queries the AST for File Descriptor (FD) blocks.
        Returns a structured dictionary containing internal file names and COPY references.
        """
        pass

    @abstractmethod
    def find_data_operations(self, ast_root: Any, dataset_fields: List[str]) -> List[Any]:
        """
        Queries the AST for operations (READ, WRITE, MOVE, IF) that interact with 
        specific dataset fields.
        Returns AST node slices that can be passed to the LLM semantic analyzer.
        """
        pass

    @abstractmethod
    def extract_slice(self, source_code: str, node: Any) -> str:
        """
        Extracts the literal string text of a given AST node from the source code.
        """
        pass

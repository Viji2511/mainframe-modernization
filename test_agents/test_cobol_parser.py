import unittest
from src.parsers.cobol_parser import COBOLParser
from src.metadata.session import DiscoverySession

class TestCOBOLParser(unittest.TestCase):
    def setUp(self):
        self.parser = COBOLParser()
        self.session = DiscoverySession(repository_id="test-repo")

    def test_select_assign_extractor(self):
        content = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST1.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE ASSIGN TO CUSTFILE.
           SELECT ORDER-FILE    ASSIGN TO ORDFILE.
       DATA DIVISION.
       FILE SECTION.
       FD  CUSTOMER-FILE.
       01  CUSTOMER-RECORD PIC X(100).
       FD  ORDER-FILE.
       01  ORDER-RECORD PIC X(50).
        """
        
        evidence = self.parser.parse("test.cbl", content, self.session)
        
        # We expect 2 SELECTs and 2 FDs = 4 Evidence items
        self.assertEqual(len(evidence), 4)
        
        selects = [e for e in evidence if e.evidence_type == "SELECT"]
        fds = [e for e in evidence if e.evidence_type == "FD"]
        
        self.assertEqual(len(selects), 2)
        self.assertEqual(len(fds), 2)
        
        self.assertEqual(selects[0].entity_name, "CUSTOMER-FILE")
        self.assertEqual(selects[0].value, "CUSTFILE")
        self.assertEqual(selects[0].severity, "PRIMARY")
        self.assertEqual(selects[0].source_file, "test.cbl")
        self.assertEqual(selects[0].parser_name, "COBOLParser")
        
        self.assertEqual(selects[1].entity_name, "ORDER-FILE")
        self.assertEqual(selects[1].value, "ORDFILE")
        
        # Verify FDs
        self.assertEqual(fds[0].entity_name, "CUSTOMER-FILE")
        self.assertEqual(fds[0].severity, "SECONDARY")

if __name__ == "__main__":
    unittest.main()

"""
Offline unit tests (no LLM call needed).
Tests the regex pre-parsers and model construction.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.step1_vsam_discovery import VSAMDiscoveryAgent
from agents.step2_copybook_locator import _find_copybook_for_dsn, _guess_dsn_match
from models import VSAMType

LISTCAT_SAMPLE = """
CLUSTER ------- AWS.CARDDEMO.ACCTFILE
  KSDS
  LRECL-----------300
  KEYLEN-----------11
  KEYOFF------------0
  CISIZE-----------4096
  REC-TOTAL---------50000
"""

def test_pre_parse_listcat():
    hints = VSAMDiscoveryAgent._pre_parse_listcat(LISTCAT_SAMPLE)
    assert hints["record_length"] == 300
    assert hints["key_length"] == 11
    assert hints["key_offset"] == 0
    assert hints["ci_size"] == 4096
    assert hints["record_count"] == 50000
    assert hints["vsam_type"] == "KSDS"
    print("test_pre_parse_listcat PASSED")

def test_guess_dsn_match():
    assert _guess_dsn_match("CVACT01Y.cpy") == "ACCTFILE"
    assert _guess_dsn_match("CVTRA05Y.cpy") == "TRANSACT"
    assert _guess_dsn_match("CVCARD.cpy") == "CARDFILE"
    print("test_guess_dsn_match PASSED")

def test_find_copybook():
    files = {"CVACT01Y.cpy": "01 ACCOUNT-RECORD.\n  05 ACCT-ID PIC 9(11)."}
    fname, content = _find_copybook_for_dsn(files, "AWS.CARDDEMO.ACCTFILE")
    assert fname == "CVACT01Y.cpy"
    print("test_find_copybook PASSED")

if __name__ == "__main__":
    test_pre_parse_listcat()
    test_guess_dsn_match()
    test_find_copybook()
    print("\nAll tests passed.")
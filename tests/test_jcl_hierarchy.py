from pathlib import Path

from api.repository_api import _artifact_structure_view
from src.agents.artifact_classification import ArtifactClassificationAgent
from src.metadata.session import DiscoverySession
from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
from src.parsers.jcl_parser import JCLParser


ROOT = Path(__file__).resolve().parents[1]


def _build_jcl_view(path, content=None):
    content = content if content is not None else path.read_text(encoding="utf-8")
    relative_path = path.name
    inventory = ArtifactClassificationAgent().classify({relative_path: content}, str(path.parent))
    session = DiscoverySession(repository_id="jcl-hierarchy-test", artifact_inventory=inventory)
    parser = JCLParser()
    # Call extractors directly: this is the parser output consumed by the
    # knowledge builder, without persistence side effects.
    for extractor in parser.get_extractors():
        session.extracted_evidence.extend(extractor.extract(relative_path, content))
    knowledge = RepositoryKnowledgeBuilder(session).build()
    artifact_id = next(iter(knowledge.jcl_jobs))
    canonical = knowledge.canonical_structures[f"JCL:{artifact_id}"]
    return _artifact_structure_view(canonical, {"type": "JCL", "name": artifact_id}), session.extracted_evidence


def _child(node, name):
    return next(item for item in node["children"] if item["name"] == name)


def test_jcl_parser_preserves_step_ownership_and_dd_concatenation(tmp_path):
    source = tmp_path / "TESTJOB.jcl"
    content = """//TESTJOB JOB CLASS=A
//JOBLIB DD DSN=A,DISP=SHR
//       DD DSN=B,DISP=SHR
//STEP1 EXEC PGM=AAA
//STEPLIB DD DSN=C,DISP=SHR
//        DD DSN=D,DISP=SHR
//SYSPRINT DD SYSOUT=*
//STEP2 EXEC PGM=BBB
//STEPLIB DD DSN=E,DISP=SHR
"""
    view, evidence = _build_jcl_view(source, content)
    assert not any(item.entity_name == "CONCAT" for item in evidence)

    job = view["nodes"][0]
    job_dds = _child(job, "JOB-level DDs")
    joblib = _child(job_dds, "JOBLIB")
    assert [item["name"] for item in joblib["children"]] == ["A", "B"]
    assert joblib["children"][1]["properties"]["is_concatenation"] is True

    step1 = _child(job, "STEP1")
    assert _child(step1, "EXEC")["properties"]["program"] == "AAA"
    assert [item["name"] for item in _child(step1, "STEPLIB")["children"]] == ["C", "D"]
    sysprint = _child(step1, "SYSPRINT")
    assert sysprint["properties"]["sysout"] == "*"
    assert not sysprint["children"]

    step2 = _child(job, "STEP2")
    assert [item["name"] for item in _child(step2, "STEPLIB")["children"]] == ["E"]


def test_jcl_exec_proc_symbols_and_malformed_dd_are_preserved(tmp_path):
    source = tmp_path / "PROCJOB.jcl"
    content = """//PROCJOB JOB CLASS=A
//JOBLIB DD DSN=&LBNM..CNTL(DB2FREE),DISP=SHR
//PSTEP EXEC PROC=MYPROC,PARM='TEST'
//OUT DD SYSOUT=*
// DD DSN=ORPHAN,DISP=SHR
"""
    view, evidence = _build_jcl_view(source, content)
    job = view["nodes"][0]
    assert _child(_child(job, "JOB-level DDs"), "JOBLIB")["children"][0]["name"] == "&LBNM..CNTL(DB2FREE)"
    step = _child(job, "PSTEP")
    assert _child(step, "EXEC")["properties"]["kind"] == "PROC"
    assert _child(step, "EXEC")["properties"]["program"] == "MYPROC"
    out = _child(step, "OUT")
    assert out["properties"]["sysout"] == "*"
    assert [item["name"] for item in out["children"]] == ["ORPHAN"]
    assert all(item.entity_name != "CONCAT" for item in evidence)


def test_legacy_jcl_dd_states_never_become_dataset_nodes():
    canonical = {
        "identity": {"artifact_type": "JCL", "name": "LEGACY"},
        "structure": {
            "exec_statements": [{"step_name": "STEP1", "program": "IEBGENER"}],
            "dd_statements": [
                {"dd_name": "SYSPRINT", "step_name": "STEP1", "scope": "step", "dataset": "UNKNOWN", "sysout": "*"},
                {"dd_name": "SYSIN", "step_name": "STEP1", "scope": "step", "dataset": "DUMMY", "dummy": True},
                {"dd_name": "SYSTSIN", "step_name": "STEP1", "scope": "step", "dataset": "INSTREAM", "instream": True},
            ],
        },
    }
    view = _artifact_structure_view(canonical, {"type": "JCL", "name": "LEGACY"})
    job = view["nodes"][0]
    step = _child(job, "STEP1")
    assert not any(item["name"] == "DD Statements" for item in job["children"])
    for dd_name, property_name in (("SYSPRINT", "sysout"), ("SYSIN", "dummy"), ("SYSTSIN", "instream")):
        dd = _child(step, dd_name)
        assert dd["properties"][property_name]
        assert not dd["children"]


def test_real_creadb21_and_cbadmcdj_keep_hierarchical_dds():
    creadb21 = next((path for path in (ROOT / "uploads").rglob("CREADB21.jcl")), None)
    assert creadb21, "Expected the current repository's CREADB21 JCL file"
    view, _evidence = _build_jcl_view(creadb21)
    job = view["nodes"][0]
    joblib = _child(_child(job, "JOB-level DDs"), "JOBLIB")
    assert [item["name"] for item in joblib["children"]] == [
        "OEM.DB2.&DB2S..SDSNLOAD", "OEM.DB2.&DB2S..SDSNLOAD", "CEE.SCEERUN"
    ]
    freepln = _child(job, "FREEPLN")
    assert [item["name"] for item in _child(freepln, "STEPLIB")["children"]] == [
        "OEM.DB2.DAZ1.SDSNEXIT", "OEMA.DB2.VERSIONA.SDSNLOAD"
    ]
    assert _child(freepln, "SYSTSIN")["children"][0]["name"] == "&LBNM..CNTL(DB2FREE)"
    assert not any(item["name"] == "DD Statements" for item in job["children"])

    cbadmcdj = next((path for path in (ROOT / "uploads").rglob("CBADMCDJ.jcl")), None)
    assert cbadmcdj, "Expected the current repository's CBADMCDJ JCL file"
    second_view, _evidence = _build_jcl_view(cbadmcdj)
    assert second_view["available"]
    assert second_view["nodes"][0]["type"] == "job"


def test_real_tranextr_has_no_global_or_fake_dataset_nodes():
    tranextr = next((path for path in (ROOT / "uploads").rglob("TRANEXTR.jcl")), None)
    assert tranextr, "Expected the current repository's TRANEXTR JCL file"
    view, _evidence = _build_jcl_view(tranextr)
    job = view["nodes"][0]
    assert not any(item["name"] == "DD Statements" for item in job["children"])

    step10 = _child(job, "STEP10")
    assert _child(step10, "SYSUT1")["children"][0]["name"] == "&HLQ..TRANTYPE.PS"
    assert _child(step10, "SYSUT2")["children"][0]["name"] == "&HLQ..TRANTYPE.BKUP(+1)"
    assert not _child(step10, "SYSPRINT")["children"]
    assert not _child(step10, "SYSIN")["children"]

    step30 = _child(job, "STEP30")
    assert _child(step30, "DD01")["children"][0]["name"] == "&HLQ..TRANTYPE.PS"
    assert _child(step30, "DD02")["children"][0]["name"] == "&HLQ..TRANCATG.PS"

    for step_name, expected_dsn in (("STEP40", "&HLQ..TRANTYPE.PS"), ("STEP50", "&HLQ..TRANCATG.PS")):
        step = _child(job, step_name)
        steplib = _child(step, "STEPLIB")
        assert [item["name"] for item in steplib["children"]] == [
            "OEM.DB2.DAZ1.RUNLIB.LOAD", "OEMA.DB2.VERSIONA.SDSNLOAD"
        ]
        assert _child(step, "SYSREC00")["children"][0]["name"] == expected_dsn
        assert not _child(step, "SYSPRINT")["children"]
        assert not _child(step, "SYSPUNCH")["children"]
        assert not _child(step, "SYSIN")["children"]

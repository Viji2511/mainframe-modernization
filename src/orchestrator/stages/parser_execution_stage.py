import logging
from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.parsers.registry import parser_registry
from src.orchestrator.pipeline_debug import log as debug_log
from src.metadata.audit import AuditTrail
import os

logger = logging.getLogger(__name__)

class ParserExecutionStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            inventory = context.session.artifact_inventory
            if not inventory:
                return
                
            parsers_run = 0
            audit = AuditTrail(context.session)
            if not parser_registry._parsers:
                parser_registry.discover_parsers()
            
            def parse_files(parser, parser_name, files, artifact_type):
                for path, content in files.items():
                    artifact_id = os.path.basename(path).rsplit(".", 1)[0].upper()
                    audit.record(stage="PARSING", component=parser_name, action="select_parser", event_type="parser_selected",
                                 artifact_id=artifact_id, artifact_name=path, source_file=path,
                                 summary=f"{parser_name} selected for {path}.")
                    audit.record(stage="PARSING", component=parser_name, action="parse", event_type="parser_started",
                                 artifact_id=artifact_id, artifact_name=path, source_file=path,
                                 summary=f"Parsing started for {path}.")
                    try:
                        evidence = parser.parse(path, content, context.session)
                        context.session.extracted_evidence.extend(evidence)
                        evidence_ids = [item.evidence_id for item in evidence]
                        line_numbers = [item.source_line for item in evidence if item.source_line is not None]
                        audit.record(stage="PARSING", component=parser_name, action="parse", event_type="parser_completed",
                                     artifact_id=artifact_id, artifact_name=path, source_file=path,
                                     source_line=min(line_numbers) if line_numbers else None,
                                     source_end_line=max(line_numbers) if line_numbers else None,
                                     evidence_ids=evidence_ids, summary=f"{parser_name} parsed {path}.",
                                     details={"artifact_type": artifact_type, "evidence_count": len(evidence)})
                        if evidence:
                            audit.record(stage="PARSING", component=parser_name, action="extract_evidence", event_type="evidence_extracted",
                                         artifact_id=artifact_id, artifact_name=path, source_file=path,
                                         source_line=min(line_numbers) if line_numbers else None,
                                         source_end_line=max(line_numbers) if line_numbers else None,
                                         evidence_ids=evidence_ids, summary=f"Extracted {len(evidence)} evidence record(s) from {path}.",
                                         details={"evidence_types": sorted({item.evidence_type for item in evidence})})
                        debug_log("Parser Execution", f"{parser_name} completed {path}: {len(evidence)} metadata objects")
                    except Exception as exc:
                        logger.exception(f"Error parsing {artifact_type} {path}: {exc}")
                        audit.record(stage="PARSING", component=parser_name, action="parse", event_type="parser_failed",
                                     status="FAILED", severity="ERROR", artifact_id=artifact_id, artifact_name=path,
                                     source_file=path, summary=f"{parser_name} failed to parse {path}.", details={"reason": str(exc)})
                        # A malformed member is an artifact-level failure, not
                        # a reason to discard the rest of an uploaded repository.
                        continue

            # We process COBOL
            if inventory.cobol_files:
                cobol_parser = parser_registry.get_parser("COBOL")
                if cobol_parser:
                    parsers_run += 1
                    parse_files(cobol_parser, "COBOLParser", inventory.cobol_files, "COBOL")
    
            # We process JCL
            if inventory.jcl_files:
                jcl_parser = parser_registry.get_parser("JCL")
                if jcl_parser:
                    parsers_run += 1
                    parse_files(jcl_parser, "JCLParser", inventory.jcl_files, "JCL")

            if inventory.copybook_files:
                copybook_parser = parser_registry.get_parser("COPYBOOK")
                if copybook_parser:
                    parsers_run += 1
                    parse_files(copybook_parser, "CopybookParser", inventory.copybook_files, "COPYBOOK")
                            
            # IDCAMS control statements are repository artifacts in their own
            # right and must not be silently left in the generic inventory.
            if inventory.idcams_files:
                idcams_parser = parser_registry.get_parser("IDCAMS")
                if idcams_parser:
                    parsers_run += 1
                    parse_files(idcams_parser, "IDCAMSParser", inventory.idcams_files, "IDCAMS")

            # LISTCAT files are classified separately from generic text files.
            # Run the catalog parser so their extracted catalog entries flow
            # through evidence and repository knowledge like every other type.
            if inventory.listcat_files:
                catalog_parser = parser_registry.get_parser("CATALOG")
                if catalog_parser:
                    parsers_run += 1
                    parse_files(catalog_parser, "CatalogParser", inventory.listcat_files, "CATALOG")
            
            context.metrics['parsers_executed'] = parsers_run
            debug_log("Parser Execution", f"Parsers executed: {parsers_run}; evidence extracted: {len(context.session.extracted_evidence)}")
        except Exception as e:
            logger.exception("Exception occurred in ParserExecutionStage")
            raise

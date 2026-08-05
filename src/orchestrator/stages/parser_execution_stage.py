import logging
from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.parsers.registry import parser_registry
from src.orchestrator.pipeline_debug import log as debug_log

logger = logging.getLogger(__name__)

class ParserExecutionStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            inventory = context.session.artifact_inventory
            if not inventory:
                return
                
            parsers_run = 0
            if not parser_registry._parsers:
                parser_registry.discover_parsers()
            
            # We process COBOL
            if inventory.cobol_files:
                cobol_parser = parser_registry.get_parser("COBOL")
                if cobol_parser:
                    parsers_run += 1
                    for path, content in inventory.cobol_files.items():
                        try:
                            evidence = cobol_parser.parse(path, content, context.session)
                            context.session.extracted_evidence.extend(evidence)
                            debug_log("Parser Execution", f"COBOLParser completed {path}: {len(evidence)} metadata objects")
                        except Exception as e:
                            logger.exception(f"Error parsing COBOL {path}: {e}")
                            raise
    
            # We process JCL
            if inventory.jcl_files:
                jcl_parser = parser_registry.get_parser("JCL")
                if jcl_parser:
                    parsers_run += 1
                    for path, content in inventory.jcl_files.items():
                        try:
                            evidence = jcl_parser.parse(path, content, context.session)
                            context.session.extracted_evidence.extend(evidence)
                            debug_log("Parser Execution", f"JCLParser completed {path}: {len(evidence)} metadata objects")
                        except Exception as e:
                            logger.exception(f"Error parsing JCL {path}: {e}")
                            raise
                            
            # IDCAMS control statements are repository artifacts in their own
            # right and must not be silently left in the generic inventory.
            if inventory.idcams_files:
                idcams_parser = parser_registry.get_parser("IDCAMS")
                if idcams_parser:
                    parsers_run += 1
                    for path, content in inventory.idcams_files.items():
                        try:
                            evidence = idcams_parser.parse(path, content, context.session)
                            context.session.extracted_evidence.extend(evidence)
                            debug_log("Parser Execution", f"IDCAMSParser completed {path}: {len(evidence)} metadata objects")
                        except Exception as e:
                            logger.exception(f"Error parsing IDCAMS {path}: {e}")
                            raise
            
            context.metrics['parsers_executed'] = parsers_run
            debug_log("Parser Execution", f"Parsers executed: {parsers_run}; evidence extracted: {len(context.session.extracted_evidence)}")
        except Exception as e:
            logger.exception("Exception occurred in ParserExecutionStage")
            raise

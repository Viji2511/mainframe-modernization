import logging
from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.parsers.registry import parser_registry

logger = logging.getLogger(__name__)

class ParserExecutionStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        inventory = context.session.artifact_inventory
        if not inventory:
            return
            
        parsers_run = 0
        
        # We process COBOL
        if inventory.cobol_files:
            cobol_parser = parser_registry.get_parser("COBOL")
            if cobol_parser:
                parsers_run += 1
                for path, content in inventory.cobol_files.items():
                    try:
                        cobol_parser.parse(path, content, context.session)
                    except Exception as e:
                        logger.error(f"Error parsing COBOL {path}: {e}")

        # We process JCL
        if inventory.jcl_files:
            jcl_parser = parser_registry.get_parser("JCL")
            if jcl_parser:
                parsers_run += 1
                for path, content in inventory.jcl_files.items():
                    try:
                        jcl_parser.parse(path, content, context.session)
                    except Exception as e:
                        logger.error(f"Error parsing JCL {path}: {e}")
                        
        # We process IDCAMS (if categorized)
        # Note: In standard inventory, IDCAMS might fall into other_files or listcat depending on how it was sniffed.
        # But we'd parse it here if there's a specific parser. We check the registry dynamically.
        # For this prototype we'll assume the registry handles known mappings.
        
        context.metrics['parsers_executed'] = parsers_run

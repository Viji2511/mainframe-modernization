import os
import json
import logging
from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.store.supabase_client import supabase_db
from src.orchestrator.pipeline_debug import log as debug_log

logger = logging.getLogger(__name__)

class ArtifactStructureBuilderStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            repo_id = context.session.repository_id
            evidence_list = context.session.extracted_evidence
            
            if not evidence_list and not context.session.artifact_inventory:
                logger.info("No extracted evidence or inventory to build structure for.")
                return
                
            # Fetch all files to link file_id
            files = supabase_db.select("Files", {"repository_id": repo_id})
            file_map = {os.path.basename(f["path"]).upper(): f["file_id"] for f in files}
            
            from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
            builder = RepositoryKnowledgeBuilder(context.session)
            knowledge = builder.build()
            context.session.repository_knowledge = knowledge

            output_dir = context.session.execution_metadata.get("output_dir")
            if output_dir:
                builder.save(output_dir)
                debug_log(
                    "Storage",
                    "Knowledge store saved: %s (programs=%d, copybooks=%d, jcl=%d, idcams=%d, datasets=%d, relationships=%d)"
                    % (
                        os.path.join(output_dir, "knowledge_store.json"),
                        len(knowledge.programs),
                        len(knowledge.copybooks),
                        len(knowledge.jcl_jobs),
                        len(knowledge.idcams_definitions),
                        len(knowledge.datasets),
                        len(knowledge.relationships),
                    ),
                )
            debug_log("Metadata Summary", json.dumps(knowledge.summary.model_dump() if hasattr(knowledge.summary, "model_dump") else knowledge.summary.dict(), sort_keys=True))
            
            def insert_artifacts(items, category):
                for key, item in items.items():
                    artifact_id = key.upper()
                    storage_id = f"{category.upper()}:{artifact_id}"
                    
                    if hasattr(item, 'filepath') and item.filepath:
                        filename_key = os.path.basename(item.filepath).upper()
                    else:
                        filename_key = artifact_id
                        
                    file_id = file_map.get(filename_key) or file_map.get(filename_key + ".CBL") or file_map.get(filename_key + ".CPY") or filename_key
                    
                    structure_data = knowledge.canonical_structures.get(storage_id) or (
                        item.model_dump() if hasattr(item, 'model_dump') else item.dict() if hasattr(item, 'dict') else vars(item)
                    )
                    
                    try:
                        existing = supabase_db.select("ArtifactMetadata", {"artifact_id": storage_id})
                        if existing:
                            supabase_db.update(
                                "ArtifactMetadata", 
                                {"artifact_id": storage_id},
                                {"structure": json.dumps(structure_data)}
                            )
                        else:
                            supabase_db.insert(
                                "ArtifactMetadata", 
                                {
                                    "artifact_id": storage_id,
                                    "file_id": file_id, 
                                    "structure": json.dumps(structure_data)
                                }
                            )
                    except Exception as ex:
                        logger.warning(f"Failed to insert ArtifactMetadata for {artifact_id}: {ex}")

            insert_artifacts(knowledge.programs, "COBOL")
            insert_artifacts(knowledge.copybooks, "COPYBOOK")
            insert_artifacts(knowledge.jcl_jobs, "JCL")
            insert_artifacts(knowledge.idcams_definitions, "IDCAMS")
            insert_artifacts(knowledge.datasets, "DATASET")
            
        except Exception as e:
            logger.exception("Exception occurred in ArtifactStructureBuilderStage")
            raise

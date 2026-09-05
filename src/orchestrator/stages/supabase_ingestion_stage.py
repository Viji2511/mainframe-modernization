import os
import logging
from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.store.supabase_client import supabase_db
from src.metadata.audit import AuditTrail

logger = logging.getLogger(__name__)

class SupabaseIngestionStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            inventory = context.session.artifact_inventory
            if not inventory:
                return
            
            repo_id = context.session.repository_id
            supabase_db.clear_errors()
            repo_name = os.path.basename(repo_id) if repo_id else "default_repo"
            
            # Insert Repository
            supabase_db.insert("Repository", {
                "repository_id": repo_id,
                "repository_name": repo_name
            })
            
            # Helper to insert file and related entity
            def insert_file_and_entity(file_dict, artifact_type):
                for path in file_dict.keys():
                    filename = os.path.basename(path)
                    entity_id = filename.split(".")[0].upper()
                    
                    # Insert File
                    supabase_db.insert("Files", {
                        "file_id": path,
                        "repository_id": repo_id,
                        "filename": filename,
                        "path": path,
                        "artifact_type": artifact_type
                    })
                    
                    # Insert specific entity
                    if artifact_type == "COBOL":
                        supabase_db.insert("Programs", {
                            "program_id": entity_id,
                            "file_id": path,
                            "program_name": entity_id
                        })
                    elif artifact_type == "COPYBOOK":
                        supabase_db.insert("Copybooks", {
                            "copybook_id": entity_id,
                            "file_id": path,
                            "copybook_name": entity_id
                        })

            # Process COBOL, COPYBOOK, JCL, IDCAMS
            insert_file_and_entity(inventory.cobol_files, "COBOL")
            insert_file_and_entity(inventory.copybook_files, "COPYBOOK")
            insert_file_and_entity(inventory.jcl_files, "JCL")
            
            if hasattr(inventory, 'idcams_files'):
                insert_file_and_entity(inventory.idcams_files, "IDCAMS")
                
            # Process VSAM DSN Candidates (as Datasets)
            for dsn in inventory.vsam_dsn_candidates:
                supabase_db.insert("Datasets", {
                    "dataset_id": dsn,
                    "dataset_name": dsn,
                    "dataset_type": "UNKNOWN"
                })

            if supabase_db.errors:
                AuditTrail(context.session).record(
                    stage="VALIDATION", component="SupabaseIngestionStage", action="persist_metadata",
                    event_type="validation_warning", status="REVIEW_REQUIRED", severity="WARNING",
                    summary="Remote metadata persistence reported errors; repository-scoped local knowledge remains the audit source of record.",
                    details={"error_count": len(supabase_db.errors), "operations": supabase_db.errors[:20]},
                    metadata={"recommended_next_action": "Restore Supabase connectivity and re-run persistence validation."},
                )

        except Exception as e:
            logger.exception("Exception occurred in SupabaseIngestionStage")
            raise

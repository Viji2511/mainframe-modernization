import json
import logging
from src.store.supabase_client import supabase_db

logger = logging.getLogger(__name__)

class ContextBuilder:
    """
    Acts as an intermediary between the Supabase Database and the LLM.
    Ensures that the LLM only receives a minimal, grounded context based on the user's query.
    """
    def __init__(self, repository_id=None):
        self.repository_id = repository_id
        
    def build_context_for_intent(self, intent: str, query: str) -> str:
        """
        Parses the query and returns a JSON string representing the minimal required context based on intent.
        """
        try:
            query_upper = query.upper()
            context_items = {}
            
            # Fetch base repository files to avoid fetching data from other jobs
            file_ids = None
            if self.repository_id:
                files = supabase_db.select("Files", {"repository_id": self.repository_id})
                file_ids = {f["file_id"] for f in files}
                
            def _filter_files(items):
                if file_ids is None: return items
                return [item for item in items if item.get("file_id") in file_ids]
            
            if intent == "Repository Summary":
                repos = supabase_db.select("Repository")
                files = supabase_db.select("Files")
                progs = _filter_files(supabase_db.select("Programs"))
                cbs = _filter_files(supabase_db.select("Copybooks"))
                ds = supabase_db.select("Datasets")
                
                context_items["RepositorySummary"] = {
                    "repositories": repos,
                    "total_files": len(files),
                    "total_programs": len(progs),
                    "total_copybooks": len(cbs),
                    "total_datasets": len(ds)
                }
                
            elif intent == "Program Analysis":
                progs = _filter_files(supabase_db.select("Programs"))
                for prog in progs:
                    if prog["program_id"] in query_upper:
                        context_items[f"Program:{prog['program_id']}"] = prog
                        # Fetch Relationships
                        rels = supabase_db.select("Relationships", {"source_id": prog["program_id"]})
                        context_items[f"Program:{prog['program_id']}_Relationships"] = rels
                        
                        # Fetch Datasets used
                        for rel in rels:
                            if rel["target_type"] == "Dataset":
                                ds = supabase_db.select("Datasets", {"dataset_id": rel["target_id"]})
                                if ds:
                                    context_items[f"Dataset:{rel['target_id']}"] = ds[0]

            elif intent == "Copybook Analysis":
                cbs = _filter_files(supabase_db.select("Copybooks"))
                for cb in cbs:
                    if cb["copybook_id"] in query_upper:
                        context_items[f"Copybook:{cb['copybook_id']}"] = cb
                        fields = supabase_db.select("Fields", {"dataset_id": cb["copybook_id"]})
                        context_items[f"Copybook:{cb['copybook_id']}_Fields"] = fields

            elif intent == "Dataset Analysis":
                if "LIST" in query_upper or "WHICH" in query_upper or "ALL" in query_upper:
                    context_items["Datasets"] = supabase_db.select("Datasets")
                else:
                    datasets = supabase_db.select("Datasets")
                    for ds in datasets:
                        if ds["dataset_id"] in query_upper or (ds.get("dataset_name") and ds["dataset_name"].upper() in query_upper):
                            context_items[f"Dataset:{ds['dataset_id']}"] = ds
                            
            elif intent == "Relationship Analysis":
                rels = supabase_db.select("Relationships")
                filtered_rels = []
                for rel in rels:
                    if rel["source_id"] in query_upper or rel["target_id"] in query_upper:
                        filtered_rels.append(rel)
                
                # If they just ask generally "Which programs access CUSTOMER?"
                if not filtered_rels:
                    for rel in rels:
                        if rel["target_id"] in query_upper or "CUSTOMER" in rel["target_id"]:
                            filtered_rels.append(rel)
                            
                context_items["Relationships"] = filtered_rels

            elif intent == "Schema Questions":
                schemas = supabase_db.select("GeneratedSchema")
                filtered_schemas = []
                for s in schemas:
                    if s["schema_id"] in query_upper or "CUSTOMER" in s["schema_id"]:
                        filtered_schemas.append(s)
                if not filtered_schemas:
                    filtered_schemas = schemas
                context_items["DatabaseSchema"] = filtered_schemas
                
                # Fetch programs just in case they asked for a program schema
                progs = supabase_db.select("Programs")
                for prog in progs:
                    if prog["program_id"] in query_upper:
                        context_items[f"Program:{prog['program_id']}"] = prog
                        rels = supabase_db.select("Relationships", {"source_id": prog["program_id"]})
                        context_items[f"Program:{prog['program_id']}_Relationships"] = rels

            elif intent == "Business Rules":
                context_items["BusinessRules"] = supabase_db.select("BusinessRules")

            else:
                # Semantic / Keyword search over everything (Unknown intent)
                cbs = _filter_files(supabase_db.select("Copybooks"))
                progs = _filter_files(supabase_db.select("Programs"))
                datasets = supabase_db.select("Datasets")
                
                for cb in cbs:
                    if cb["copybook_id"] in query_upper:
                        context_items[f"Copybook:{cb['copybook_id']}"] = cb
                for prog in progs:
                    if prog["program_id"] in query_upper:
                        context_items[f"Program:{prog['program_id']}"] = prog
                for ds in datasets:
                    if ds["dataset_id"] in query_upper:
                        context_items[f"Dataset:{ds['dataset_id']}"] = ds
                        
                # If we still haven't found anything specific, return a general summary
                # so the assistant can answer general questions like "explain the given files"
                if not context_items:
                    rels = supabase_db.select("Relationships")
                    summary_progs = []
                    for p in progs:
                        p_rels = [r for r in rels if r["source_id"] == p["program_id"]]
                        summary_progs.append({
                            "program_name": p["program_name"],
                            "datasets_accessed": [r["target_id"] for r in p_rels if r["target_type"] == "Dataset"],
                            "copybooks_used": [r["target_id"] for r in p_rels if r["target_type"] == "Copybook"]
                        })
                        
                    context_items["GeneralSummary"] = {
                        "Programs": summary_progs,
                        "Copybooks": [c["copybook_name"] for c in cbs],
                        "Datasets": [d.get("dataset_name", d["dataset_id"]) for d in datasets]
                    }

            return json.dumps(context_items, indent=2, default=str)
        except Exception as e:
            logger.exception("Exception occurred in ContextBuilder.build_context_for_intent")
            raise

    def build_context_for_query(self, query: str) -> str:
        return self.build_context_for_intent("Unknown", query)

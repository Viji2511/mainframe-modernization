import json
import logging
from typing import Dict, Any, List
from src.models.knowledge_store import RepositoryKnowledge

logger = logging.getLogger(__name__)

class ContextBuilder:
    """
    Acts as an intermediary between the Repository Knowledge Store and the LLM.
    Ensures that the LLM only receives a minimal, grounded context based on the user's query.
    """
    def __init__(self, knowledge_store: RepositoryKnowledge):
        self.knowledge = knowledge_store
        
    def build_context_for_intent(self, intent: str, query: str) -> str:
        """
        Parses the query and returns a JSON string representing the minimal required context based on intent.
        """
        try:
            query_upper = query.upper()
            context_items = {}
            
            if intent == "Repository Summary":
                context_items["RepositorySummary"] = self.knowledge.summary.dict() if hasattr(self.knowledge.summary, 'dict') else self.knowledge.summary
                
            elif intent == "Program Analysis":
                for prog_id, prog in self.knowledge.programs.items():
                    if prog_id in query_upper:
                        context_items[f"Program:{prog_id}"] = prog.dict() if hasattr(prog, 'dict') else prog
                        for dsn in (prog.datasets_accessed if hasattr(prog, 'datasets_accessed') else []):
                            if dsn in self.knowledge.datasets:
                                ds = self.knowledge.datasets[dsn]
                                context_items[f"Dataset:{dsn}"] = ds.dict() if hasattr(ds, 'dict') else ds
                        for cb in (prog.copybooks_used if hasattr(prog, 'copybooks_used') else []):
                            if cb in self.knowledge.copybooks:
                                copybook = self.knowledge.copybooks[cb]
                                context_items[f"Copybook:{cb}"] = copybook.dict() if hasattr(copybook, 'dict') else copybook
                                
            elif intent == "Copybook Analysis":
                for cb_id, cb in self.knowledge.copybooks.items():
                    if cb_id in query_upper:
                        context_items[f"Copybook:{cb_id}"] = cb.dict() if hasattr(cb, 'dict') else cb

            elif intent == "Dataset Analysis":
                if "LIST" in query_upper or "WHICH" in query_upper:
                    context_items["Datasets"] = [
                        ds.dict() if hasattr(ds, 'dict') else ds 
                        for ds in self.knowledge.datasets.values()
                    ]
                else:
                    for dsn, ds in self.knowledge.datasets.items():
                        if dsn in query_upper:
                            context_items[f"Dataset:{dsn}"] = ds.dict() if hasattr(ds, 'dict') else ds
                            
            elif intent == "Relationship Analysis":
                # Find program in query to filter relationships
                target_prog = None
                for prog_id in self.knowledge.programs.keys():
                    if prog_id in query_upper:
                        target_prog = prog_id
                        break
                
                relevant_rels = []
                for rel in self.knowledge.relationships:
                    if target_prog:
                        if rel.source_id == target_prog or rel.target_id == target_prog:
                            relevant_rels.append(rel.dict() if hasattr(rel, 'dict') else rel)
                    else:
                        relevant_rels.append(rel.dict() if hasattr(rel, 'dict') else rel)
                        
                context_items["Relationships"] = relevant_rels

            elif intent == "Schema Questions":
                context_items["DatabaseSchema"] = self.knowledge.database_schema

            elif intent == "Business Rules":
                context_items["BusinessRules"] = [br.dict() if hasattr(br, 'dict') else br for br in self.knowledge.business_rules.values()]

            else:
                # Semantic / Keyword search over everything (Unknown intent)
                for cb_id, cb in self.knowledge.copybooks.items():
                    if cb_id in query_upper:
                        context_items[f"Copybook:{cb_id}"] = cb.dict() if hasattr(cb, 'dict') else cb
                for prog_id, prog in self.knowledge.programs.items():
                    if prog_id in query_upper:
                        context_items[f"Program:{prog_id}"] = prog.dict() if hasattr(prog, 'dict') else prog
                for dsn, ds in self.knowledge.datasets.items():
                    if dsn in query_upper:
                        context_items[f"Dataset:{dsn}"] = ds.dict() if hasattr(ds, 'dict') else ds

            return json.dumps(context_items, indent=2, default=str)
        except Exception as e:
            logger.exception("Exception occurred in ContextBuilder.build_context_for_intent")
            raise

    def build_context_for_query(self, query: str) -> str:
        # Fallback for old API if needed
        return self.build_context_for_intent("Unknown", query)

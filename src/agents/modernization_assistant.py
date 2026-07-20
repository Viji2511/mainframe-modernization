import logging
import json
from src.models.knowledge_store import RepositoryKnowledge
from src.agents.context_builder import ContextBuilder
from src.ai.base_agent import BaseAgent

logger = logging.getLogger(__name__)

class ModernizationAssistant:
    def __init__(self, repository_id=None):
        self.context_builder = ContextBuilder(repository_id=repository_id)
        self.llm = BaseAgent(name="ModernizationAssistant")
        
    def _detect_intent(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["schema", "ddl", "create table", "sql", "er diagram", "diagram", "relational"]):
            return "Schema Questions"
        if any(w in q for w in ["summarize", "statistics", "overview", "health"]):
            return "Repository Summary"
        if any(w in q for w in ["access", "depend", "call graph", "used by", "which programs", "which copybooks"]):
            return "Relationship Analysis"
        if any(w in q for w in ["program", "cbl", "cobol", "does"]):
            return "Program Analysis"
        if any(w in q for w in ["copybook", "fields", "layout", "cpy"]):
            return "Copybook Analysis"
        if any(w in q for w in ["dataset", "vsam", "ksds", "esds"]):
            return "Dataset Analysis"
        if any(w in q for w in ["rule", "validation", "logic"]):
            return "Business Rules"
        return "Unknown"

    def chat(self, user_query: str) -> str:
        """
        Receives a user query, detects intent, extracts targeted context, and interacts with an LLM.
        """
        intent = self._detect_intent(user_query)
        logger.info(f"Detected Intent: {intent} for query: {user_query}")
        
        context = self.context_builder.build_context_for_intent(intent, user_query)
        
        if not context or context == "{}" or context == "[]":
            return "I couldn't find any relevant context in the Knowledge Store for that query."
            
        system_prompt = (
            "You are a mainframe modernization assistant.\n"
            "You MUST ONLY use the provided Repository Knowledge Store Context to answer the user's question.\n"
            "If the answer is not in the context, explicitly state that it is missing rather than inventing an answer.\n\n"
            f"Context:\n{context}"
        )
        
        try:
            response = self.llm._ask(system_prompt, user_query)
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Fallback if LLM isn't configured or fails
            return f"System encountered an error calling the LLM. Intent detected: {intent}.\n\nContext extracted:\n{context[:500]}..."

import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
logger = logging.getLogger(__name__)

class SupabaseStore:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL", "")
        key: str = os.environ.get("SUPABASE_KEY", "")
        
        if not url or not key:
            logger.warning("SUPABASE_URL or SUPABASE_KEY not found in environment variables. Database interactions will fail.")
            self.client = None
        else:
            self.client: Client = create_client(url, key)

    def insert(self, table: str, data: dict) -> dict:
        table = table.lower()
        if not self.client:
            logger.error(f"Cannot insert into {table} - Supabase client not initialized.")
            return {}
        try:
            response = self.client.table(table).insert(data).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error inserting into {table}: {e}")
            return {}

    def select(self, table: str, query: dict = None) -> list:
        table = table.lower()
        if not self.client:
            logger.error(f"Cannot select from {table} - Supabase client not initialized.")
            return []
        try:
            req = self.client.table(table).select("*")
            if query:
                for k, v in query.items():
                    req = req.eq(k, v)
            response = req.execute()
            return response.data
        except Exception as e:
            logger.error(f"Error selecting from {table}: {e}")
            return []

    def update(self, table: str, match: dict, data: dict) -> dict:
        table = table.lower()
        if not self.client:
            logger.error(f"Cannot update {table} - Supabase client not initialized.")
            return {}
        try:
            req = self.client.table(table).update(data)
            for k, v in match.items():
                req = req.eq(k, v)
            response = req.execute()
            return response.data
        except Exception as e:
            logger.error(f"Error updating {table}: {e}")
            return {}

supabase_db = SupabaseStore()

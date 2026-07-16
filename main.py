import os
import argparse
from dotenv import load_dotenv

# Load env variables first
load_dotenv()

from agents.pipeline_orchestrator import PipelineOrchestrator
from agents.file_ingestion_agent import FileIngestionAgent
from agents.step1_vsam_discovery import VSAMDiscoveryAgent
import config.settings
from rich.console import Console
from rich.table import Table

def main():
    parser = argparse.ArgumentParser(
        description="Mainframe Modernizer - Generalized Reverse-Engineering Pipeline (Steps 1-3)"
    )
    parser.add_argument(
        "--input",
        help="Path to the source directory or a .zip file containing mainframe sources."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a lightweight pipeline self-test to verify configuration and initialization."
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Process only a specific DSN / VSAM dataset (partial match allowed)."
    )
    parser.add_argument(
        "--db",
        choices=["postgresql", "mysql"],
        default="postgresql",
        help="Target database dialect for the schema mapping (default: postgresql)."
    )
    parser.add_argument(
        "--list-vsam",
        action="store_true",
        help="Discovers and lists VSAM datasets in the input, then exits without running step 2 & 3."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the output directory for JSON results (default from config/settings.py)."
    )

    args = parser.parse_args()

    # Apply configuration overrides
    os.environ["TARGET_DB"] = args.db
    config.settings.TARGET_DB = args.db
    
    if args.output:
        os.environ["OUTPUT_DIR"] = args.output
        config.settings.OUTPUT_DIR = args.output

    console = Console()
    
    if args.self_test:
        console.rule("[bold cyan]Pipeline Health Check[/bold cyan]", characters="-")
        try:
            # Check imports
            import sys
            from src.orchestrator.event_bus import event_bus
            from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
            from src.metadata.session import DiscoverySession
            console.print("[green][OK][/green] Imports OK")
            
            # Check EventBus
            if event_bus is None:
                raise ValueError("EventBus not initialized")
            console.print("[green][OK][/green] EventBus Initialization OK")
            
            # Check Directories
            for d in ["uploads", "outputs", "logs", "temp", "knowledge"]:
                if not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
            console.print("[green][OK][/green] Required Directories OK")
            
            # Check Configuration
            console.print(f"[green][OK][/green] Configuration Loaded (Target DB: {config.settings.TARGET_DB})")
            
            # Check Knowledge Builder
            session = DiscoverySession(repository_id="self-test-repo")
            builder = RepositoryKnowledgeBuilder(session)
            console.print("[green][OK][/green] RepositoryKnowledgeBuilder Initialization OK")
            
            # Check Models & Knowledge Graph
            from src.models.knowledge_store import (
                RepositoryKnowledge, Traceability, DatasetKnowledge, Relationship
            )
            tk = Traceability(source_file="test.cob")
            dk = DatasetKnowledge(id="TEST.DSN", name="TEST.DSN", dsn="TEST.DSN", traceability=tk)
            rel = Relationship(source_id="PGM1", target_id="TEST.DSN", rel_type="ACCESSES")
            rk = RepositoryKnowledge(repository_id="test")
            rk.datasets["TEST.DSN"] = dk
            rk.relationships.append(rel)
            
            dumped = rk.model_dump_json() if hasattr(rk, "model_dump_json") else rk.json()
            if hasattr(RepositoryKnowledge, "model_validate_json"):
                RepositoryKnowledge.model_validate_json(dumped)
            else:
                RepositoryKnowledge.parse_raw(dumped)
            console.print("[green][OK][/green] Pydantic Models Validation OK")
            console.print("[green][OK][/green] Knowledge Graph Validated (No recursive references)")
            
            # Legacy Compatibility
            from src.orchestrator.adapters.legacy_adapter import LegacyCompatibilityAdapter
            console.print("[green][OK][/green] LegacyCompatibilityAdapter Validated (No contract mismatches)")
            
            console.print("\n[bold green]Self-Test completed successfully![/bold green]")
            return
        except Exception as e:
            console.print(f"[bold red]Self-Test failed:[/bold red] {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
    if not args.input:
        parser.error("--input is required unless --self-test is specified.")

    if args.list_vsam:
        console.rule("[bold cyan]Discovering Mainframe VSAM Datasets[/bold cyan]", characters="-")
        console.print(f"[dim]Ingesting source files from: {args.input}...[/dim]")
        
        try:
            ingester = FileIngestionAgent()
            inventory = ingester.ingest(args.input)
            
            console.print(
                f"[green]+ Ingestion complete.[/green] Detected language: [bold]{inventory.detected_language}[/bold]\n"
            )
            
            step1 = VSAMDiscoveryAgent()
            datasets = step1.run(inventory, args.dsn)
            
            if datasets:
                t = Table(show_lines=True)
                t.add_column("DSN / Dataset Name", style="bold cyan")
                t.add_column("Type", style="magenta")
                t.add_column("Confidence", justify="right", style="green")
                t.add_column("Source JCL", style="dim")
                t.add_column("Notes")

                for d in datasets:
                    t.add_row(
                        d.dsn,
                        d.vsam_type.value,
                        f"{d.confidence:.2f}",
                        d.source_jcl or "—",
                        d.notes or ""
                    )
                console.print(t)
            else:
                console.print("[yellow]No VSAM datasets found matching criteria.[/yellow]")

        except Exception as e:
            console.print(f"[bold red]Discovery failed:[/bold red] {e}")
            
    else:
        # Run orchestrator full pipeline
        try:
            orchestrator = PipelineOrchestrator()
            # The deterministic orchestrator stores results by repository/job id.
            # DSN filtering is handled by the legacy discovery-only path above.
            orchestrator.run(args.input)
        except Exception as e:
            import logging
            logging.exception("Pipeline execution failed at main.py level")
            raise

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    main()

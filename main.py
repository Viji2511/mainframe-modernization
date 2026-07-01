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
        required=True,
        help="Path to the source directory or a .zip file containing mainframe sources."
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
        orchestrator = PipelineOrchestrator()
        orchestrator.run(args.input, args.dsn)

if __name__ == "__main__":
    main()

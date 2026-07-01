import os
import json
from rich.console import Console
from rich.table import Table
from config.settings import OUTPUT_DIR
from agents.file_ingestion_agent import FileIngestionAgent
from agents.step1_vsam_discovery import VSAMDiscoveryAgent
from agents.step2_copybook_locator import CopyBookLocatorAgent
from agents.step3_source_analyzer import SourceCodeAnalyzerAgent
from models.schemas import PipelineResult

class PipelineOrchestrator:
    """
    Coordinates file ingestion, VSAM discovery, copybook parsing, and source code reference
    analysis for single-target or multi-target batch dataset migrations.
    """

    def __init__(self):
        self.console = Console()
        self.ingestion_agent = FileIngestionAgent()
        self.step1_agent = VSAMDiscoveryAgent()
        self.step2_agent = CopyBookLocatorAgent()
        self.step3_agent = SourceCodeAnalyzerAgent()

    def run(self, input_path: str, target_dsn: str = None) -> list[PipelineResult]:
        """
        Runs the full modernization pipeline on the specified input directory or zip file.
        """
        self.console.rule("[bold cyan]Starting Mainframe Modernizer Pipeline[/bold cyan]", characters="-")
        
        # 1. File Ingestion
        self.console.print(f"[dim]Ingesting source files from: {input_path}...[/dim]")
        try:
            inventory = self.ingestion_agent.ingest(input_path)
            self.console.print(
                f"[green]+ Ingestion complete.[/green] Detected language: [bold]{inventory.detected_language}[/bold]\n"
                f"  Loaded: {len(inventory.cobol_files)} COBOL | {len(inventory.pli_files)} PL/I | "
                f"{len(inventory.natural_files)} Natural | {len(inventory.rpg_files)} RPG | "
                f"{len(inventory.jcl_files)} JCL | {len(inventory.copybook_files)} Copybooks\n"
            )
        except Exception as e:
            self.console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
            return []

        # 2. Step 1: VSAM Discovery
        self.console.print("[dim]Running Step 1: VSAM Discovery...[/dim]")
        try:
            discovered_datasets = self.step1_agent.run(inventory, target_dsn)
            self.console.print(f"[green]+ Discovered {len(discovered_datasets)} VSAM dataset candidates.[/green]\n")
        except Exception as e:
            self.console.print(f"[bold red]VSAM Discovery failed:[/bold red] {e}")
            return []

        # Create output directory if it doesn't exist
        out_dir = OUTPUT_DIR
        os.makedirs(out_dir, exist_ok=True)

        results = []

        # 3 & 4. Step 2 & 3: Iterate and analyze
        for i, vsam in enumerate(discovered_datasets, start=1):
            self.console.rule(f"[yellow]Analyzing Dataset {i}/{len(discovered_datasets)}: {vsam.dsn}[/yellow]", characters="-")
            
            try:
                # Step 2: Copybook mapping
                self.console.print(f"  [dim]Step 2: Locating copybook schema...[/dim]")
                copybook = self.step2_agent.run(inventory, vsam)
                if copybook.filename != "NOT_FOUND":
                    self.console.print(f"  [green]+ Found copybook [bold]{copybook.filename}[/bold] ({copybook.language}) with {len(copybook.fields)} fields.[/green]")
                else:
                    self.console.print(f"  [yellow]! No copybook found for DSN: {vsam.dsn}[/yellow]")

                # Step 3: Source Reference Analysis
                self.console.print(f"  [dim]Step 3: Extracting business rules and programs...[/dim]")
                source_analyses = self.step3_agent.run(vsam, copybook, inventory)
                self.console.print(f"  [green]+ Matched {len(source_analyses)} referencing program(s).[/green]")

                # Combine results
                result = PipelineResult(
                    vsam_dataset=vsam,
                    copybook=copybook,
                    source_analyses=source_analyses,
                    ready_for_schema_design=len(copybook.fields) > 0 and len(source_analyses) > 0
                )
                results.append(result)

                # Save JSON
                dsn_safe_name = vsam.dsn.replace(".", "_")
                out_path = os.path.join(out_dir, f"{dsn_safe_name}_result.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(result.model_dump_json(indent=2))
                self.console.print(f"  [dim]Saved result -> {out_path}[/dim]\n")

            except Exception as e:
                self.console.print(f"  [bold red]* Error analyzing {vsam.dsn}: {e}. Skipping to next...[/bold red]\\n")

        # 5. Print summary table
        if results:
            self.console.rule("[bold green]Pipeline Execution Summary[/bold green]", characters="-")
            t = Table(show_lines=True)
            t.add_column("DSN / Dataset Name", style="bold cyan")
            t.add_column("Type", style="magenta")
            t.add_column("Fields", justify="right")
            t.add_column("Programs", justify="right")
            t.add_column("Confidence", justify="right", style="green")
            t.add_column("Ready", justify="center")

            for res in results:
                dsn = res.vsam_dataset.dsn
                vtype = res.vsam_dataset.vsam_type.value
                fields = len(res.copybook.fields) if res.copybook else 0
                programs = len(res.source_analyses)
                conf = f"{res.vsam_dataset.confidence:.2f}"
                ready = "[bold green]YES[/bold green]" if res.ready_for_schema_design else "[bold red]NO[/bold red]"
                t.add_row(dsn, vtype, str(fields), str(programs), conf, ready)

            self.console.print(t)
            self.console.print(f"\n[bold green]Pipeline finished.[/bold green] All structured schema outputs saved in [bold]{out_dir}/[/bold]")
        else:
            self.console.print("[bold yellow]No datasets were processed successfully.[/bold yellow]")

        return results

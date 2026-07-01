# Mainframe Modernizer - System Architecture

This document provides a deep technical analysis of the Mainframe Modernizer architecture, component interactions, LLM prompt engineering strategies, algorithms, and data models.

---

## 1. System Data Flow

The pipeline executes sequentially. The ingestion agent builds an in-memory inventory, which is passed through successive processing layers to generate the final relational target models:

```
[Raw Dir / Zip] ──> (FileIngestionAgent) 
                         │
                         ▼
                    [Inventory]
                         │
                         ▼
             (VSAMDiscoveryAgent) ──> Extracts candidates via multi-route
                         │
                         ▼
               [list[VSAMDataset]]
                         │
                         ▼
            (CopyBookLocatorAgent) ──> Resolves schema structures (Pass 1-4)
                         │
                         ▼
                    [CopyBook]
                         │
                         ▼
            (SourceCodeAnalyzerAgent) ──> Analyzes access verbs & business rules
                         │
                         ▼
             [list[SourceCodeAnalysis]]
                         │
                         ▼
               (PipelineOrchestrator) ──> Writes outputs & Console summary
```

---

## 2. Component Details

### BaseAgent (`agents/base_agent.py`)
Provides connection wrappers to the Groq API utilizing the `llama-3.3-70b-versatile` model. Implements automated token limit handling, socket reset retry loops with exponential backoff, and JSON output formatting parsing constraints.

### FileIngestionAgent (`agents/file_ingestion_agent.py`)
A non-LLM Python agent that handles directory walking, zip extraction, and content classification. Evaluates files based on extensions and structural sniffing rules to assign assets to specific language bins (COBOL, PL/I, RPG, Natural). Also parses spreadsheet metadata files and performs regex sweeps to isolate candidate DSN values.

### VSAMDiscoveryAgent (`agents/step1_vsam_discovery.py`)
Processes candidate DSN values to extract dataset parameters. Uses four sequential routes: LISTCAT dumps, metadata tables, JCL IDCAMS commands, or source code fallback. Automatically assigns confidence metrics based on the extraction channel used.

### CopyBookLocatorAgent (`agents/step2_copybook_locator.py`)
Maps the logical records structure to physical files. Contains search templates for COBOL, PL/I, Natural, RPG, and Assembler formats. Employs a 4-pass matching logic (segment matching, content parsing, filename hints mapping, or LLM selection fallback) to identify copybooks.

### SourceCodeAnalyzerAgent (`agents/step3_source_analyzer.py`)
Scans program repositories to construct data access records. Extracts verbs, key definitions, and business logic using language-specific syntax rules.

### PipelineOrchestrator (`agents/pipeline_orchestrator.py`)
Executes the modernizer process flow. Catches data-specific exceptions to avoid stopping the batch, writes JSON outputs to folder paths, and formats console summary tables.

---

## 3. Pydantic Models & Field Reference

### `VSAMDataset`
Represents the structural configuration of a physical VSAM file.
* `dsn` (`str`): Fully qualified Dataset Name.
* `vsam_type` (`VSAMType`): KSDS, ESDS, RRDS, LDS, or UNKNOWN.
* `record_length` (`Optional[int]`): Record size in bytes.
* `key_length` (`Optional[int]`): Key size in bytes (only for KSDS).
* `key_offset` (`Optional[int]`): Key offset start position (only for KSDS).
* `ci_size` (`Optional[int]`): Control Interval size.
* `record_count` (`Optional[int]`): Allocated records count.
* `source_jcl` (`Optional[str]`): Source file JCL name.
* `notes` (`str`): Remarks.
* `confidence` (`float`): Accuracy estimate (0.0 to 1.0).

### `COBOLField`
Represents a schema field structure mapped recursively.
* `level` (`int`): Structural hierarchy number (e.g. 01, 05, 10).
* `name` (`str`): Field variable name.
* `pic` (`Optional[str]`): Picture clause definition.
* `cobol_type` (`str`): Storage class (e.g. DISPLAY, COMP, COMP-3).
* `occurs` (`Optional[int]`): Loop count.
* `redefines` (`Optional[str]`): Redefined field variable name.
* `offset` (`Optional[int]`): Offset in record.
* `length` (`Optional[int]`): Length in bytes.
* `children` (`list[COBOLField]`): Sub-level nested record structures.

### `CopyBook`
* `filename` (`str`): File name containing layout schema.
* `dsn_match` (`Optional[str]`): Dataset name mapped.
* `fields` (`list[COBOLField]`): Parsed schema fields list.
* `raw_text` (`str`): Original file content.
* `language` (`str`): Layout dialect.

### `BusinessRule`
* `field_name` (`str`): Field referenced in rule.
* `usage` (`Literal`): Role in logic (`key`, `lookup`, `validation`, `relationship`, `output`, `other`).
* `description` (`str`): Meaning description.
* `found_in` (`str`): Program name.

### `SourceCodeAnalysis`
* `program_name` (`str`): Program analyzed.
* `vsam_dsn` (`str`): Dataset mapped.
* `operations` (`list[str]`): IO verbs detected.
* `key_fields` (`list[str]`): Key columns mapped.
* `business_rules` (`list[BusinessRule]`): Extracted logic rules.
* `related_files` (`list[str]`): Associated files.

### `Inventory`
* `input_dir` (`str`): Source files parent directory.
* `cobol_files` / `pli_files` / `natural_files` / `rpg_files` (`dict[str, str]`): File names to content mappings.
* `jcl_files` / `copybook_files` / `listcat_files` / `metadata_files` / `other_files` (`dict[str, str]`): Utility file content mappings.
* `detected_language` (`str`): Dominant language code.
* `vsam_dsn_candidates` (`list[str]`): Candidates extracted.

---

## 4. Prompt Engineering Strategy

System prompts are dynamically built in Step 2 and Step 3 based on the language of the source file.

```
+-------------------------------------------------------------+
|                     Step 2/3 Orchestrator                   |
+-------------------------------------------------------------+
                               │
               Determines language of the copybook/code
                               │
       ┌───────────────┬───────┴───────┬───────────────┐
       ▼               ▼               ▼               ▼
   [COBOL]          [PL/I]         [Natural]         [RPG]
       │               │               │               │
  COBOL_PROMPT    PLI_PROMPT    NATURAL_PROMPT    RPG_PROMPT
  (PIC Clauses) (DCL Declares)   (DDM Formats)    (D-Specs)
```

Each prompt enforces strict rules mapping the language's native data types (e.g., `PIC S9(9) COMP-3` in COBOL, `FIXED DEC(9,2)` in PL/I, `P9.2` in Natural, or zoned decimal specs in RPG) into the generic `COBOLField` fields (`pic`, `cobol_type`, `length`), enabling standardized downstream schema design.

---

## 5. Algorithms & Strategies

### Multi-Pass DSN Matcher (Step 2)
To align datasets to layout files without hardcoding name patterns:
* **Pass 1: Filename Segments**: Matches DSN elements against file name tokens (e.g., `ACCTDATA` segment matching file `CVACT01Y.cpy`).
* **Pass 2: Content Parsing**: Scans copybooks for variable segments.
* **Pass 3: Hint Map**: Resolves abbreviations (`acct` -> `ACCTDATA`).
* **Pass 4: LLM Fallback**: If multiple files match or names are completely non-standard, sends copybook names and content snippets to the LLM to choose the best match.

### Confidence Scoring Heuristic (Step 1)
Discovery reliability varies depending on the input source:
* **Confidence = 1.0 (LISTCAT)**: Exact database configurations.
* **Confidence = 0.9 (Metadata spreadsheets/CSV)**: Centralized database mappings.
* **Confidence = 0.8 (JCL IDCAMS)**: Configuration statements.
* **Confidence = 0.5 (Source Code Fallback)**: Inferred from program layouts.
* **Confidence = 0.2 (Unknown)**: Default fallback.

---

## 6. Extension Guide: Adding a Mainframe Language

To add support for a new language (e.g., **Assembler**):
1. **File Ingestion**: In `FileIngestionAgent._sniff_file`, add extension detection (`.asm`) and signature check for instruction layout format to assign to `other_files` or a new class.
2. **Step 2 (Locator)**: Define `ASSEMBLER_PROMPT` containing specific rules to map DSECT definitions (`DS`, `DC`, `CL4`, `PL8`) into `COBOLField` equivalents, and select this prompt in `CopyBookLocatorAgent.run` when an `.asm` copybook matches.
3. **Step 3 (Analyzer)**: Add Assembler IO verbs (e.g., `GET`, `PUT`, `READ`, `WRITE`) and register them in `SourceCodeAnalyzerAgent._extract_operations`.

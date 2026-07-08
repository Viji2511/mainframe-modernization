# Mainframe Modernizer

An agentic AI pipeline designed to automate the reverse-engineering and modernization of mainframe VSAM datasets into relational databases (PostgreSQL/MySQL). 

---

## 1. Project Overview & Research Context

Mainframe migrations are traditionally hindered by the tightly coupled nature of legacy code and data. Specifically, database schemas are not stored centrally in a database catalog but are instead embedded directly within application variables (COBOL copybooks, PL/I includes, RPG D-specs, etc.) and job controllers (JCL). 

Current academic research and commercial tooling leave significant gaps:
* **LLM Code Generators** (e.g., *XMainframe*, *COBOL-Coder*) focus on translation to Java/C# but ignore database schema extraction and relational mapping.
* **Conceptual Studies** (e.g., *Khandelwal*, *Khemka & Majumdar*) identify the complexity of VSAM data migration but offer no automated pipeline implementations.
* **Commercial Legacy Tools** (e.g., *Modern Systems*, *Astadia*) rely on rigid, rule-based systems that break when encountering custom, non-standard naming conventions or undocumented business logic.

**Our Novel Contribution**: The first generalized, multi-pass agentic LLM pipeline that ingests raw mainframe assets, automatically classifies dialects (COBOL, PL/I, Natural, RPG, Assembler), recovers VSAM file schemas, matches relevant application programs, extracts data-access business rules, and outputs a complete, relationally-mapped schema model.

---

## 2. System Architecture

Below is the conceptual architecture of the modernizer pipeline showing the sequential flow of inputs and agents:

```
+--------------------------------------------------------------------------------+
|                                 SOURCE ASSETS                                  |
|            (JCL, Source Programs, Copybooks, LISTCAT dumps, Excel/CSVs)         |
+--------------------------------------------------------------------------------+
                                       |
                                       v
```
mainframe-modernizer/
├── src/
│   ├── ingestion/       # Parses raw ZIP uploads and organizes mainframe files by language
│   ├── discovery/       # Dynamic dataset resolution via Strategy Pattern (JCL, LISTCAT, Source)
│   ├── parsers/         # Resolves Copybook dependencies and future AST parsing
│   ├── analyzers/       # AI-driven semantic rule extraction and code slicing
│   ├── relationships/   # Explicit graph edge construction for enterprise metadata
│   ├── orchestrator/    # Pipeline state management mapping across all phases
│   ├── metadata/        # Canonical graph models (Repository, Relationship, Program)
│   └── ai/              # Base LLM interaction layer
├── agents/              # Facade proxies for backward compatibility
├── models/              # Facade proxies for backward compatibility
├── docs/                # Architecture Decision Records (ADR)
├── config/              # Centralized settings and overrides
├── api/                 # FastAPI routes for async background processing
```

## 🏗️ Architecture

MainframeAI has transitioned from a linear heuristic script to an **enterprise-ready, modular graph architecture**:
- **Strategy Pattern Discovery:** Extensible discovery classes dynamically test `LISTCAT`, JCL, or Source to map datasets without hardcoded assumptions.
- **Dependency-Based Resolution:** Follows the true data-flow (`SELECT` -> `FD` -> `COPY`) to mathematically link code to schemas.
- **Code Slicing:** Extracts targeted logical paragraphs for AI analysis to eliminate token limits and hallucinations on 100k+ line legacy monolithic apps.
- **Graph Metadata Engine:** Automatically generates deterministic Graph edges (`Program -> INCLUDES -> Copybook`, `JCL -> ALLOCATES -> Dataset`) to build the foundation for export to Neo4j.
- **Future-Proof AST Parsing (ADR-001):** The framework is laying the groundwork to replace Regex with deterministic Tree-Sitter AST grammars.

---

## 3. Installation & Run Guide

### Prerequisites
* Python 3.10 or higher
* Node.js and npm (for the frontend UI)
* Groq API Key (with `llama-3.3-70b-versatile` access)

### Setup
1. Clone the repository and navigate to the project directory:
   ```bash
   cd mainframe-modernizer
   ```

2. Install core Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with your Groq API credentials:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   TARGET_DB=postgresql
   OUTPUT_DIR=outputs
   ```

---

## 4. Running the Web Application Dashboard

You can interact with the pipeline via a web dashboard. Run both the backend API and frontend dev server:

### A. Start the API Service (FastAPI)
```bash
# Install server-specific packages
pip install -r api/requirements.txt

# Start the uvicorn service
uvicorn api.main:app --reload --port 8000
```
* **API Documentation**: Live at [http://localhost:8000/docs](http://localhost:8000/docs)

### B. Start the Web Client (React + Vite)
In a new terminal window:
```bash
# Install frontend packages
npm install

# Start the Vite server
npm run dev
```
* **Dashboard App**: Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 5. Usage Examples

The tool uses standard arguments via `main.py` at the project root:

```bash
# Basic run on a directory (processes all discovered datasets)
python main.py --input data/carddemo_samples

# Run on a zipped archive
python main.py --input carddemo_samples.zip

# Run for a single target VSAM dataset (partial match supported)
python main.py --input data/carddemo_samples --dsn ACCTDATA

# Specify target database dialect (postgresql or mysql)
python main.py --input data/carddemo_samples --db mysql

# Override the output directory for JSON results
python main.py --input data/carddemo_samples --output custom_outputs/

# List discovered VSAM datasets and candidate DSNs without executing full analysis
python main.py --input data/carddemo_samples --list-vsam
```

### CLI Flag Reference
* `--input` (Required): Path to directory or `.zip` file containing assets.
* `--dsn` (Optional): Process only datasets matching this DSN string.
* `--db` (Optional): Relational database target dialect (`postgresql` or `mysql`). Default is `postgresql`.
* `--list-vsam` (Optional): Discovery-only mode. Prints discovered files and exits.
* `--output` (Optional): Path to write JSON results (overrides default `./outputs`).

---

## 6. Pipeline Flow & Steps

| Step | Component | Main Inputs | Main Outputs | Description |
| :--- | :--- | :--- | :--- | :--- |
| **0** | **FileIngestionAgent** | Directory / ZIP | `Inventory` | Extracts files, sniffs extension/contents, and lists DSN candidates using regex. |
| **1** | **VSAMDiscoveryAgent** | `Inventory` | `list[VSAMDataset]` | Runs multi-route parsing (LISTCAT, JCL, CSV, or Source fallback) to extract file configurations with confidence scores. |
| **2** | **CopyBookLocatorAgent** | `Inventory`, `VSAMDataset` | `CopyBook` | Identifies the schema copybook, extracts structure definitions, and maps data types. |
| **3** | **SourceCodeAnalyzerAgent** | `Inventory`, `VSAMDataset`, `CopyBook` | `list[SourceCodeAnalysis]` | Identifies referencing programs, extracts CRUD operations, and maps business validation rules. |
| **End** | **PipelineOrchestrator** | Results | Console Summary & JSONs | Aggregates all steps and writes safe results under `outputs/`. |

---

## 7. Supported Mainframe Environments

### Languages & Data Structures
| Mainframe Language | Copybook/Schema Representation | Access Verbs & Opcodes Supported |
| :--- | :--- | :--- |
| **COBOL** | `.cpy`, `.copy` | `READ`, `WRITE`, `REWRITE`, `DELETE`, `START` |
| **PL/I** | `.inc`, `.dclgen` | `READ FILE`, `WRITE FILE`, `REWRITE FILE`, `DELETE FILE` |
| **Natural** | `.nsl`, `.ddm` | `READ`, `STORE`, `UPDATE`, `DELETE`, `FIND`, `GET` |
| **RPG** | `.rpgle`, `.sqlrpgle` (D-specs) | `CHAIN`, `READ`, `READE`, `UPDATE`, `WRITE`, `DELETE` |
| **CICS Commands** | Embedded Statements | `EXEC CICS READ`, `EXEC CICS WRITE`, `EXEC CICS REWRITE`, `EXEC CICS DELETE` |
| **Assembler** | `.asm` (DSECT structures) | System macros and storage reference instructions |

### Source Metadata Formats
* **IBM IDCAMS LISTCAT**: Standard dataset catalog listings.
* **JCL DD Statements**: Direct job step declarations (`DSN=`, `DSNAME=`).
* **CSV Exports**: Structural dumps containing database mapping columns.
* **Excel Spreadsheets**: Layout data sheets (`.xlsx`, `.xls`) processed via `openpyxl`.

---

## 8. Output Format

Each dataset run creates a detailed JSON result file in `outputs/` named `{dsn_safe_name}_result.json` aligning with the `PipelineResult` model:

```json
{
  "vsam_dataset": {
    "dsn": "AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS",
    "vsam_type": "KSDS",
    "record_length": 300,
    "key_length": 11,
    "key_offset": 0,
    "ci_size": 18432,
    "record_count": 50,
    "source_jcl": "ACCTFILE.jcl",
    "notes": "Indexed file configuration",
    "confidence": 1.0
  },
  "copybook": {
    "filename": "CVACT01Y.cpy",
    "dsn_match": "AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS",
    "fields": [
      {
        "level": 5,
        "name": "ACCT-ID",
        "pic": "9(11)",
        "cobol_type": "DISPLAY",
        "occurs": null,
        "redefines": null,
        "offset": 0,
        "length": 11,
        "children": []
      }
    ],
    "raw_text": "...",
    "language": "COBOL"
  },
  "source_analyses": [
    {
      "program_name": "CBACT01C",
      "vsam_dsn": "AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS",
      "operations": ["READ", "WRITE"],
      "key_fields": ["ACCT-ID"],
      "business_rules": [
        {
          "field_name": "ACCT-ID",
          "usage": "key",
          "description": "Validation check of account active status before data processing.",
          "found_in": "CBACT01C"
        }
      ],
      "related_files": []
    }
  ],
  "ready_for_schema_design": true
}
```

---

## 9. Known Limitations
* **Large Codebase Scaling**: Scanning large mainframe repos (> 1,000 code files) can hit LLM rate limits without token limits overrides.
* **Redefined Structures**: Overlapping `REDEFINES` in copybooks require advanced offset calculation support.
* **Natural/RPG Implicit Schemas**: Variable mappings defined inline without DDMs require source code inference, reducing discovery confidence.

---

## 10. References & Papers
1. **XMainframe** (Dau et al., 2024) — *COBOL LLMs for translation, lacks schema migration mappings.*
2. **COBOL-Coder** (Dau et al., 2026) — *Refactoring and code generation without relational schema support.*
3. **Khandelwal** (2025) — *Identifying VSAM migration hurdles.*
4. **Khemka & Majumdar** (2025) — *AI-driven conceptual modernization frameworks.*

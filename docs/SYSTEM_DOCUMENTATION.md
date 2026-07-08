# Mainframe Modernizer: System & Prompts Documentation

This document serves as the comprehensive technical guide for the Mainframe Modernizer framework, detailing its generalized architecture, the validation and confidence engine, and the exact LLM system prompts used in the AI agents.

---

## 1. Generalized Architecture

The framework has been redesigned into an enterprise-ready, modular graph architecture located entirely in the `src/` directory.

### Core Modules:
- **`src/ingestion`**: Scans zip files or directories, parsing file extensions to categorize mainframes source code (COBOL, PL/I, RPG, Natural, JCL, LISTCAT).
- **`src/discovery`**: Replaces hardcoded assumptions with a `Strategy Pattern`. Datasets are dynamically discovered by tracing LISTCAT dumps, JCL DD allocations, or inline source declarations.
- **`src/parsers`**: Implements true dependency-based data flow resolution. Instead of guessing schema associations, the framework links Datasets to schemas via compiler-like syntax tracing: `SELECT -> FD -> COPY`.
- **`src/analyzers`**: Uses dynamic Code Slicing to parse massive legacy applications. Rather than hitting context window limits, the agent only extracts logical blocks (e.g. Paragraphs) interacting with specific fields.
- **`src/relationships`**: Extracts and structures explicit graph edges (`Program -> READS -> Dataset`, `Dataset -> FORMATTED_BY -> Copybook`) to prepare for Graph Database ingestion.
- **`src/validators`**: Ensures absolute trust via the Confidence Engine and Validation Framework.

---

## 2. Validation & Confidence Engine

Every stage of the pipeline evaluates its own output before continuing. 

**Configuration-Driven**: Scoring logic is decoupled into `config/validation_config.json`.
- Discovered in LISTCAT? `+40 points`.
- Verified via JCL? `+20 points`.
- Direct `COPY` statement found? `+80 points`.

**Validation Classes**:
- `DatasetValidator`: Validates organizational structure and dataset name validity.
- `CopybookValidator`: Verifies that a layout was accurately parsed and maps back to a valid DSN.
- `SchemaValidator`: Emits warnings for overlapping bytes or missing PIC clauses.
- `RelationshipValidator`: Grades edges based on concrete syntactic evidence versus LLM inference.

At the end of processing, a **Repository Validation Report** is printed, yielding PASS/WARNING/FAIL distributions and a weighted overall confidence score.

---

## 3. LLM AI System Prompts

The framework leverages several specialized system prompts, formatted below.

### Phase 1: VSAM Discovery (`src/discovery/step1_vsam_discovery.py`)
```text
You are a mainframe VSAM expert. Given raw configuration documents (LISTCAT, JCL, CSV metadata, or program source),
extract VSAM dataset metadata. Return ONLY a valid JSON object with these keys:

{
  "dsn": "<dataset name>",
  "vsam_type": "<KSDS|ESDS|RRDS|LDS|UNKNOWN>",
  "record_length": <integer or null>,
  "key_length": <integer or null>,
  "key_offset": <integer or null>,
  "ci_size": <integer or null>,
  "record_count": <integer or null>,
  "source_jcl": "<filename or null>",
  "notes": "<any important observation>"
}

Rules:
- dsn must be the fully-qualified dataset name.
- vsam_type must be one of KSDS, ESDS, RRDS, LDS, UNKNOWN.
- Use null for fields not found in the input.
- Return ONLY the JSON, no explanation.
```

### Phase 2: Copybook Parsers (`src/parsers/step2_copybook_locator.py`)
Depending on the source language discovered, one of the following prompts is selected to extract the canonical `COBOLField` layout.

**COBOL:**
```text
You are a COBOL copybook parser. Given raw COBOL copybook text, extract all
field definitions and return ONLY valid JSON in this exact shape:

{
  "fields": [
    {
      "level": <int>,
      "name": "<FIELD-NAME>",
      "pic": "<PIC clause or null>",
      "cobol_type": "<DISPLAY|COMP|COMP-3|COMP-1|COMP-2|INDEX>",
      "occurs": <int or null>,
      "redefines": "<field name or null>",
      "offset": <byte offset int or null>,
      "length": <byte length int or null>,
      "children": []
    }
  ]
}

Rules:
- Include ALL levels (01, 05, 10, 15, etc.).
- 01-level group items have pic=null.
- Children list always set to [].
- Return ONLY the JSON, no extra text.
```

*(Additional prompts exist dynamically mapped for `PL/I`, `Natural`, `RPG`, and `Assembler` following this exact JSON contract, substituting type mapping instructions like "Map Natural format N or P for COMP-3".)*

### Phase 3: Source Code Analyzer (`src/analyzers/step3_source_analyzer.py`)
This prompt is dynamically formatted at runtime by Python, injecting the detected `{language}` and contextual `{verbs_hint}` (e.g. `READ, WRITE, REWRITE` for COBOL).

```text
You are a {language} source code analyst. Given a {language} program and its VSAM dataset
context, extract structured information. Return ONLY valid JSON:

{
  "program_name": "<name>",
  "vsam_dsn": "<dsn>",
  "operations": ["READ", "WRITE"],
  "key_fields": ["FIELD-A"],
  "business_rules": [
    {
      "field_name": "<name>",
      "usage": "<key|lookup|validation|relationship|output|other>",
      "description": "<one sentence>",
      "found_in": "<program name>"
    }
  ],
  "related_files": ["OTHER-DSN"]
}

Rules:
- operations: only verbs actually seen in the source code (e.g. {verbs_hint}).
- key_fields: fields used in key access or index lookups.
- business_rules: focus on validation conditional checks, meaningful assignments, and loop logic.
- Return ONLY the JSON.
```

---

## 4. Future AST Transition (ADR-001)
As dictated by `ADR-001`, future iterations of this pipeline will deprecate these LLM heuristic extraction paths in favor of deterministic Tree-sitter AST parsing. The `ASTParser` abstract base class has been defined in `src/parsers/ast_parser.py` to facilitate this migration.

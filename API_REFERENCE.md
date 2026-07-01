# Mainframe Modernizer - API Reference

This document covers all public classes, methods, inputs/outputs, schemas, and usage examples.

---

## 1. Pipeline Agents

### `BaseAgent`
Base class providing connectivity, retry loops, and JSON formatting via Groq.

* **`_ask(self, system: str, user: str) -> str`**
  * **Parameters**:
    * `system` (`str`): System guidelines prompt context.
    * `user` (`str`): Target content query block.
  * **Returns**: `str` (Raw response text).
  * **Example**:
    ```python
    agent = BaseAgent("MyAgent")
    raw = agent._ask("System prompt", "User query")
    ```

* **`_ask_json(self, system: str, user: str) -> dict`**
  * **Parameters**:
    * `system` (`str`): System instruction schema context.
    * `user` (`str`): Query content.
  * **Returns**: `dict` (Parsed JSON result or `{"_parse_error": True}`).

---

### `FileIngestionAgent`
Recursively walks folder structures or zip files, classifies files, parses CSV/Excel, and extracts candidate DSN values.

* **`ingest(self, input_path: str) -> Inventory`**
  * **Parameters**:
    * `input_path` (`str`): Folder or zip path.
  * **Returns**: `Inventory` (Extracted metadata container).
  * **Example**:
    ```python
    ingester = FileIngestionAgent()
    inventory = ingester.ingest("data/carddemo_samples")
    ```

---

### `VSAMDiscoveryAgent`
Resolves metadata definitions for candidate datasets.

* **`run(self, inventory: Inventory, target_dsn: str = None) -> list[VSAMDataset]`**
  * **Parameters**:
    * `inventory` (`Inventory`): Scanned files database.
    * `target_dsn` (`str`, optional): Specific dataset filter.
  * **Returns**: `list[VSAMDataset]` (Extracted datasets metadata).
  * **Example**:
    ```python
    agent = VSAMDiscoveryAgent()
    datasets = agent.run(inventory, "ACCTDATA")
    ```

---

### `CopyBookLocatorAgent`
Maps dataset schemas to copybooks and parses them recursively.

* **`run(self, inventory: Inventory, vsam: VSAMDataset) -> CopyBook`**
  * **Parameters**:
    * `inventory` (`Inventory`): Scanned files metadata.
    * `vsam` (`VSAMDataset`): Discovered dataset.
  * **Returns**: `CopyBook` (Matched and parsed layout schema).
  * **Example**:
    ```python
    locator = CopyBookLocatorAgent()
    copybook = locator.run(inventory, vsam)
    ```

---

### `SourceCodeAnalyzerAgent`
Scans codebase files for references to trace access verbs and rules.

* **`run(self, vsam: VSAMDataset, copybook: CopyBook, inventory: Inventory) -> list[SourceCodeAnalysis]`**
  * **Parameters**:
    * `vsam` (`VSAMDataset`): Discovered dataset attributes.
    * `copybook` (`CopyBook`): Matched layout model schema.
    * `inventory` (`Inventory`): Ingested codebase assets.
  * **Returns**: `list[SourceCodeAnalysis]` (Analyses per program).
  * **Example**:
    ```python
    analyzer = SourceCodeAnalyzerAgent()
    analyses = analyzer.run(vsam, copybook, inventory)
    ```

---

### `PipelineOrchestrator`
Coordinates pipeline stages, saves results, and prints execution summaries.

* **`run(self, input_path: str, target_dsn: str = None) -> list[PipelineResult]`**
  * **Parameters**:
    * `input_path` (`str`): Target source assets path (folder or zip).
    * `target_dsn` (`str`, optional): Filter specific dataset DSN.
  * **Returns**: `list[PipelineResult]` (Aggregated migration configurations).
  * **Example**:
    ```python
    orchestrator = PipelineOrchestrator()
    results = orchestrator.run("data/carddemo_samples", "ACCTDATA")
    ```

---

## 2. Pydantic Models Reference

### `VSAMDataset`
* `dsn` (`str`): Fully qualified Dataset Name.
* `vsam_type` (`VSAMType`): KSDS, ESDS, RRDS, LDS, UNKNOWN.
* `record_length` (`Optional[int]`): Record size in bytes.
* `key_length` (`Optional[int]`): Key size in bytes.
* `key_offset` (`Optional[int]`): Key offset start position.
* `ci_size` (`Optional[int]`): Control Interval size.
* `record_count` (`Optional[int]`): Allocated records count.
* `source_jcl` (`Optional[str]`): Source file JCL name.
* `notes` (`str`): Observations.
* `confidence` (`float`): Accuracy estimate (0.0 to 1.0).

### `COBOLField`
* `level` (`int`): Hierarchy layout level.
* `name` (`str`): Field variable name.
* `pic` (`Optional[str]`): Picture clause definition.
* `cobol_type` (`str`): Storage class (e.g. DISPLAY, COMP, COMP-3).
* `occurs` (`Optional[int]`): Array count.
* `redefines` (`Optional[str]`): Overlapped field.
* `offset` (`Optional[int]`): Offset in record.
* `length` (`Optional[int]`): Size in bytes.
* `children` (`list[COBOLField]`): Sub-fields list.

### `CopyBook`
* `filename` (`str`): File containing layout schema.
* `dsn_match` (`Optional[str]`): Target DSN mapped.
* `fields` (`list[COBOLField]`): Parsed field schemas list.
* `raw_text` (`str`): Copybook raw text.
* `language` (`str`): Mapped copybook dialect (COBOL, PL/I, RPG, Natural, Assembler).

### `BusinessRule`
* `field_name` (`str`): Layout field variable name.
* `usage` (`str`): Role in program logic (`key`, `lookup`, `validation`, `relationship`, `output`, `other`).
* `description` (`str`): Descriptive definition.
* `found_in` (`str`): Reference program.

### `SourceCodeAnalysis`
* `program_name` (`str`): Reference program name.
* `vsam_dsn` (`str`): Target DSN mapped.
* `operations` (`list[str]`): IO verbs detected.
* `key_fields` (`list[str]`): Key columns mapped.
* `business_rules` (`list[BusinessRule]`): Extracted logic rules.
* `related_files` (`list[str]`): Linked datasets.

### `PipelineResult`
* `vsam_dataset` (`VSAMDataset`): Discovered dataset attributes.
* `copybook` (`Optional[CopyBook]`): Schema field layouts.
* `source_analyses` (`list[SourceCodeAnalysis]`): Referencing files results.
* `ready_for_schema_design` (`bool`): Flag indicating compatibility for automated relational schema translation.

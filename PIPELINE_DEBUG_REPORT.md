# Repository Understanding Platform — Pipeline Debug Report

## Root cause

The active pipeline (`src/orchestrator/pipeline_orchestrator.py`) discovered and parsed artifacts, but the final knowledge graph was not persisted. The API (`api/repository_api.py`) consequently queried Supabase only. When Supabase was unavailable, summary and explorer endpoints returned empty arrays; when it contained older data, unscoped global tables mixed stale COBOL and relationship counts with the current repository's zero files. This explains `JCL Jobs=0`, `Total Files=0`, and `No repository artifacts found` despite successful parsing.

Additional pipeline defects were:

- `Inventory` had no IDCAMS bucket, so IDCAMS members could be lost in generic/JCL handling.
- The parser stage executed COBOL and JCL only; IDCAMS parsers were never invoked.
- `RepositoryKnowledgeBuilder._finalize_summary` counted only entity dictionaries, excluding other discovered files and some artifact categories.
- JCL `EXEC` statements were not extracted into job metadata.
- The structure builder called the Supabase update method with match/data arguments reversed.
- The explorer rendered only COBOL programs and copybooks, even when backend structures contained other categories.

## Fixes applied

- The artifact inventory now records IDCAMS files and classification rule/reason details.
- Classification checks IDCAMS signatures before generic JCL classification and preserves recursive relative paths.
- Parser execution invokes `IDCAMSParser` and extracts JCL `EXEC PGM=` metadata in addition to DD metadata.
- Knowledge building creates JCL/IDCAMS objects, attaches allocated datasets and executed programs, records defined clusters, and calculates total files from the complete inventory.
- The structure stage persists the canonical `knowledge_store.json` under the repository output directory and records storage metrics in debug mode.
- Repository APIs load that repository-scoped store first. Supabase fallback queries now scope programs, copybooks, datasets, relationships, and rules to the requested repository.
- Structure, datasets, relationships, schema, and result endpoints now return the persisted repository data.
- Repository Explorer now renders JCL Jobs, IDCAMS Scripts, and Datasets; Artifact Structure renders JCL and IDCAMS metadata.
- Corrected `ArtifactMetadata` update argument ordering.
- Added opt-in `DEBUG_PIPELINE=true` diagnostics for upload/discovery, classification rules, parser completion/evidence counts, metadata summary, storage, and completion status.
- Artifact keys are collision-safe for duplicate basenames in nested directories, while source paths remain in traceability metadata.
- Canonical storage IDs are type-qualified (`COBOL:CBIMPORT`, `JCL:CBIMPORT`, etc.) so identical basenames across artifact types cannot overwrite one another.

## Verification

Synthetic four-JCL check:

```
total_files=6, cobol_programs=1, copybooks=1, jcl_jobs=4
```

End-to-end `data/carddemo_samples` run:

```
discovered files: 100
COBOL programs: 32
copybooks: 29
JCL jobs: 18
IDCAMS scripts: 20
datasets: 27
relationships: 98
migration readiness: Ready for modernization review
```

The API returned the same counts and structure category sizes (`32/29/18/20/27`). Python compilation, the existing COBOL parser unit test, and the Vite production build passed. Supabase network writes were unavailable in the sandbox; the canonical local store is now the repository-scoped source used by the API, while Supabase remains the optional persistence path.

## Canonical File Structure Viewer

The stored knowledge now includes `canonical_structures`, with a common IR for COBOL, COPYBOOK, JCL, IDCAMS, and DATASET artifacts. Each structure contains identity, source path, metadata, hierarchy, fields/variables, datasets, dependencies, relationships, business rules, and statistics. `ArtifactMetadata` receives this same JSON structure, and the UI's Canonical File Structure panel renders it directly without reparsing source files.

Phase 2 extends that IR with explicit `general_information`, `structure`, `components`, and `relationship_tree` nodes. The viewer renders these nodes as collapsible tree sections for program divisions/paragraphs, copybook records/fields, JCL steps/EXEC/DD flow, IDCAMS components, and dataset record layouts/references.

The semantic IR now additionally exposes `identity`, `semantic_structure`, `entities`, `attributes`, `semantic_relationships`, and `constraints`. Relationship verbs are normalized to semantic terms such as `READS`, `USES`, `EXECUTES`, and `REFERENCES`; artifact-specific entities include programs, records, fields, execution steps, VSAM definitions, and datasets.

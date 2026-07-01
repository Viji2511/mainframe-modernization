# Mainframe Modernizer - Academic Research Gaps & Novelty Analysis

This document evaluates current academic research papers and commercial rule-based tools in the legacy modernization space to establish the novelty and specific contributions of this agentic AI pipeline.

---

## 1. Research Gaps Evaluation

| Research Paper / Tool | What It Does (Capabilities) | What It Lacks (Limitations) | How This Pipeline Fills the Gap |
| :--- | :--- | :--- | :--- |
| **XMainframe** *(Dau et al., 2024)* | Evaluates LLM capability for basic COBOL translation and dead code elimination. | Does not address file schema extraction, catalog analysis, or database migration layouts. | Automates the complete discovery and mapping of VSAM file schemas from JCL/LISTCAT to design target layouts. |
| **COBOL-Coder** *(Dau et al., 2026)* | Translates COBOL syntax routines to Java/C# classes. | Lacks a data access layer migration engine; ignores VSAM and embedded file layouts. | Extracts read/write access verbs, keys, and schemas, allowing data storage modernizations to match translated code. |
| **Khandelwal** *(2025)* | Analyzes operational challenges of legacy migrations, emphasizing VSAM migration complexity. | Conceptual paper only; provides no code, parsers, or concrete automation implementation. | Delivers a complete, functional Python tool that extracts metadata and processes assets automatically. |
| **Khemka & Majumdar** *(2025)* | Formulates a high-level theoretical AI framework for mainframe modernization. | Does not define agent steps, prompt templates, or file classification heuristics. | Implements a concrete 4-step pipeline (Ingestion, Discovery, Schema mapping, Usage analysis). |
| **Goel et al.** *(2024)* | Extracts variable logic rules from COBOL programs using LLM prompting. | Restricts focus to source variables; ignores physical dataset definitions and structural metadata. | Connects code-level business rules directly to physical VSAM attributes and copybook layouts. |
| **IBM Research (watsonx Code Assistant)** *(2023)* | AI-powered code translation assistant for mainframe assets. | Primarily acts as a co-pilot for code syntax, lacking generalized automated batch schema conversion. | Operates autonomously as a headless pipeline that processes directory outputs without manual code editing. |
| **Bhatia et al.** *(2025)* | Reconstructs relational models from legacy source code variable assignments. | Assumes DB2 or standard relational source metadata; cannot handle raw VSAM or JCL configurations. | Ingests LISTCAT, JCL, and metadata CSVs to rebuild physical record constraints for VSAM files. |
| **Silva et al.** *(2024)* | Mapped translation heuristics specifically targeting RPG layouts. | Limited to RPG systems; does not scale to mixed environments or complex JCL configurations. | Supports multi-language detection and prompt styling (COBOL, PL/I, RPG, Natural, Assembler). |
| **Modern Systems** *(Astadia/Advanced)* | Commercial rule-based transpilation utilities. | Relies on hardcoded templates. Breaks when naming styles deviate or comments are complex. | Uses LLM fallbacks and content-based heuristics to resolve naming mismatch anomalies. |
| **Micro Focus Enterprise Suite** | Simulates mainframe runtime configurations on target servers. | Retains VSAM files in emulation packages rather than migrating layouts to relational database schemas. | Reverse-engineers legacy records to relational PostgreSQL/MySQL database designs. |

---

## 2. Novelty Contribution Statement

The Mainframe Modernizer introduces the **first generalized agentic pipeline** capable of reverse-engineering legacy storage structures across multiple mainframe languages (COBOL, PL/I, RPG, Natural, Assembler) and formats without structural hardcoding.

By integrating:
1. **Dynamic Extension Sniffing**: Multi-mode classification of files based on layout syntax rather than naming rules.
2. **Multi-Route Metadata Resolution**: Cascading discovery channels (LISTCAT -> Spreadsheet -> JCL -> Source code inference) ensuring robust parameter extraction.
3. **Multi-Pass Scheme Association**: Resolving schema layouts via segment matches, references, hints, or LLM selection fallbacks.

This project bridges the gap between manual re-platforming and automated data migration, providing developers and architects with a complete, structured catalog to design target PostgreSQL/MySQL relational tables.

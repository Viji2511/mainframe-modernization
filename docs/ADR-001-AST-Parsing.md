# ADR-001: Transition to Tree-Sitter AST Parsing

## Status
Accepted

## Context
The initial prototype of the Mainframe Modernizer relied heavily on Regular Expressions (Regex) to parse COBOL, PL/I, RPG, and Natural code. While Regex was sufficient for simple heuristic-based analysis on smaller codebases like AWS CARDDEMO, it poses significant risks for generalized enterprise usage:

1. **Brittle Parsing**: Regex cannot accurately understand deeply nested structures, line continuations, or edge cases in legacy language dialects.
2. **Context Loss**: Simple text matching loses the hierarchical relationship of the code (e.g., determining if an operation is nested inside a deeply nested `IF` condition).
3. **Language Complexity**: COBOL and PL/I have massive grammars that are impossible to fully represent via regex.

To ensure enterprise-grade reliability, the framework must transition to deterministic parsing algorithms.

## Decision
We will replace all regex-based code slicing and tracing with **Tree-sitter** Abstract Syntax Tree (AST) parsing.

1. **Tree-sitter Grammars**: The framework will adopt open-source Tree-sitter grammars for COBOL (`tree-sitter-cobol`), PL/I, RPG, etc.
2. **`ASTParser` Interface**: A new interface `src/parsers/ast_parser.py` has been created. All future parsing logic MUST implement this interface.
3. **Query Language**: Information extraction (e.g., finding all `READ` statements inside a paragraph) will be performed using Tree-sitter's S-expression query language, guaranteeing 100% syntactic accuracy.

## Consequences
### Positive
* **Accuracy**: Zero false positives/negatives in parsing structural blocks like `FD` or `SELECT`.
* **Reliability**: Eliminates edge-cases caused by unique formatting or comment placements.
* **LLM Optimization**: We can slice the AST to feed the LLM *only* the specific nodes relevant to the business logic, drastically reducing token usage and hallucination risks.

### Negative
* **Complexity**: Developing and maintaining Tree-sitter queries requires a deeper understanding of language ASTs compared to writing simple regex strings.
* **Dependency Overhead**: Compiling Tree-sitter bindings for Windows/Linux/Mac introduces native dependency requirements to the project installation.

## Implementation Strategy
Phase 9 introduces the `ASTParser` stub. Future sprints will implement `CobolTreeSitterParser` and incrementally deprecate the regex patterns found in `src/analyzers/step3_source_analyzer.py` and `src/parsers/step2_copybook_locator.py`.

-- Repository
CREATE TABLE IF NOT EXISTS Repository (
    repository_id TEXT PRIMARY KEY,
    repository_name TEXT,
    upload_timestamp TIMESTAMP DEFAULT NOW()
);

-- Files
CREATE TABLE IF NOT EXISTS Files (
    file_id TEXT PRIMARY KEY,
    repository_id TEXT REFERENCES Repository(repository_id),
    filename TEXT,
    path TEXT,
    artifact_type TEXT -- COBOL, COPYBOOK, JCL, IDCAMS, CATALOG
);

-- Programs
CREATE TABLE IF NOT EXISTS Programs (
    program_id TEXT PRIMARY KEY,
    file_id TEXT REFERENCES Files(file_id),
    program_name TEXT
);

-- Copybooks
CREATE TABLE IF NOT EXISTS Copybooks (
    copybook_id TEXT PRIMARY KEY,
    file_id TEXT REFERENCES Files(file_id),
    copybook_name TEXT
);

-- Datasets
CREATE TABLE IF NOT EXISTS Datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT,
    dataset_type TEXT,
    record_length INTEGER,
    key_length INTEGER,
    canonical_id TEXT -- Used for Auto Reconciliation Engine to group aliases
);

-- Fields
CREATE TABLE IF NOT EXISTS Fields (
    field_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES Datasets(dataset_id),
    field_name TEXT,
    picture_clause TEXT,
    sql_type TEXT,
    length INTEGER,
    nullable BOOLEAN DEFAULT TRUE
);

-- Relationships
CREATE TABLE IF NOT EXISTS Relationships (
    relationship_id TEXT PRIMARY KEY,
    source_type TEXT,
    source_id TEXT,
    target_type TEXT,
    target_id TEXT,
    relationship_type TEXT
);

-- BusinessRules
CREATE TABLE IF NOT EXISTS BusinessRules (
    rule_id TEXT PRIMARY KEY,
    program_id TEXT REFERENCES Programs(program_id),
    description TEXT
);

-- ArtifactMetadata
CREATE TABLE IF NOT EXISTS ArtifactMetadata (
    artifact_id TEXT PRIMARY KEY,
    file_id TEXT REFERENCES Files(file_id),
    structure JSONB
);

import React, { useEffect, useMemo, useState } from 'react';
import PropTypes from 'prop-types';
import {
  ChevronDown,
  ChevronRight,
  Database,
  FileCode2,
  FileText,
  Folder,
  Search,
} from 'lucide-react';

const asArray = (value) => (Array.isArray(value) ? value : []);

const present = (value) => value !== null && value !== undefined && value !== '';

const displayName = (value, fallback = 'Unnamed') => {
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (!value || typeof value !== 'object') return fallback;
  return String(value.name || value.id || value.step_name || value.dd_name || value.program || fallback);
};

const details = (item, keys) => keys
  .filter((key) => present(item?.[key]))
  .map((key) => `${key.replace(/_/g, ' ')}: ${item[key]}`);

const metadata = (items) => items.filter(Boolean);

const leafNodes = (items, type, label) => asArray(items).map((item, index) => ({
  id: `${type}-${displayName(item, index)}-${index}`,
  name: label ? `${label} ${displayName(item, index)}` : displayName(item, `${type} ${index + 1}`),
  type,
  meta: typeof item === 'object' ? details(item, ['program', 'dsn', 'value', 'organization']) : [],
}));

const propertyNode = (id, name, value) => {
  if (!present(value) || (typeof value === 'object' && !Object.keys(value).length)) return null;
  const valueDetails = typeof value === 'object' && !Array.isArray(value)
    ? Object.entries(value).filter(([, item]) => present(item)).map(([key, item]) => `${key.replace(/_/g, ' ')}: ${item}`)
    : [String(value)];
  return { id, name, type: 'property', meta: valueDetails };
};

const copybookTree = (artifact, root) => {
  const hierarchy = artifact.hierarchy || artifact.semantic_structure?.record_definition || {};
  const records = asArray(hierarchy.records || hierarchy.field_hierarchy);
  const fields = records.length ? records : asArray(artifact.fields);
  const toFieldNode = (field, path) => ({
    id: `${path}-${field.name || 'field'}`,
    name: field.name || 'UNNAMED FIELD',
    type: asArray(field.children).length ? 'group' : 'field',
    meta: metadata([
      present(field.level) && `Level ${String(field.level).padStart(2, '0')}`,
      field.pic && `PIC ${field.pic}`,
      present(field.length) && `Length ${field.length}`,
      field.usage && `Usage ${field.usage}`,
      field.occurs && `Occurs ${field.occurs}`,
      field.redefines && `Redefines ${field.redefines}`,
    ]),
    children: asArray(field.children).map((child, index) => toFieldNode(child, `${path}-${index}`)),
  });

  return {
    ...root,
    children: fields.length
      ? [{
          id: `${root.id}-record-definition`,
          name: 'Record Definition',
          type: 'record',
          children: fields.map((field, index) => toFieldNode(field, `${root.id}-${index}`)),
        }]
      : [],
  };
};

const programTree = (artifact, root) => {
  const hierarchy = artifact.hierarchy || artifact.structure || {};
  const divisions = asArray(hierarchy.divisions);
  const sections = asArray(hierarchy.sections);
  const variables = artifact.variables || {};
  const procedureChildren = [
    { id: `${root.id}-paragraphs`, name: 'Paragraphs', type: 'group', children: leafNodes(hierarchy.paragraphs, 'paragraph') },
    { id: `${root.id}-sections`, name: 'Sections', type: 'group', children: leafNodes(sections, 'section') },
    { id: `${root.id}-calls`, name: 'CALL Statements', type: 'group', children: leafNodes(artifact.dependencies?.called_programs, 'program') },
    { id: `${root.id}-copies`, name: 'COPY Statements', type: 'group', children: leafNodes(artifact.dependencies?.copybooks_used, 'copybook') },
    { id: `${root.id}-files`, name: 'File References', type: 'group', children: leafNodes(artifact.datasets?.read, 'dataset') },
  ].filter((node) => node.children.length);
  const divisionNodes = divisions.map((division) => {
    const normalized = String(division).replace(/ DIVISION$/i, '').toUpperCase();
    const children = normalized === 'DATA'
      ? [
          { id: `${root.id}-data-file`, name: 'FILE SECTION', type: 'section', children: leafNodes(variables.file_records, 'field') },
          { id: `${root.id}-data-working`, name: 'WORKING-STORAGE', type: 'section', children: leafNodes(variables.working_storage, 'field') },
          { id: `${root.id}-data-linkage`, name: 'LINKAGE SECTION', type: 'section', children: leafNodes(variables.linkage, 'field') },
          { id: `${root.id}-data-local`, name: 'LOCAL-STORAGE', type: 'section', children: leafNodes(variables.local, 'field') },
        ].filter((node) => node.children.length)
      : normalized === 'PROCEDURE'
        ? procedureChildren
        : [];
    return { id: `${root.id}-division-${normalized}`, name: `${normalized} DIVISION`, type: 'division', children };
  });
  if (!divisions.some((division) => String(division).replace(/ DIVISION$/i, '').toUpperCase() === 'PROCEDURE') && procedureChildren.length) {
    divisionNodes.push({ id: `${root.id}-procedure-components`, name: 'Procedure Components', type: 'group', children: procedureChildren });
  }
  return { ...root, children: divisionNodes };
};

const jclTree = (artifact, root) => {
  const structure = artifact.structure?.job || {};
  const steps = asArray(structure.steps || artifact.components?.steps);
  const jobCard = artifact.metadata?.job_card;
  return {
    ...root,
    children: [
      propertyNode(`${root.id}-job-card`, 'JOB Card', jobCard),
      {
        id: `${root.id}-exec-steps`, name: 'EXEC Steps', type: 'group', children: steps.map((step, index) => ({
          id: `${root.id}-step-${step.step_name || index}`,
          name: step.step_name || step.program || `STEP${index + 1}`,
          type: 'step',
          meta: details(step, ['program', 'procedure']),
        })),
      },
      { id: `${root.id}-dds`, name: 'DD Statements', type: 'group', children: leafNodes(artifact.hierarchy?.dd_statements || artifact.components?.dd_statements, 'dd', 'DD') },
      { id: `${root.id}-programs`, name: 'Referenced Programs', type: 'group', children: leafNodes(artifact.dependencies?.programs_executed, 'program') },
      { id: `${root.id}-datasets`, name: 'Referenced Datasets', type: 'group', children: leafNodes(artifact.datasets?.references, 'dataset') },
    ].filter((node) => node && (!node.children || node.children.length)),
  };
};

const idcamsTree = (artifact, root) => {
  const components = artifact.components || {};
  const cluster = asArray(components.cluster)[0] || artifact.metadata?.cluster_name;
  return {
    ...root,
    children: [{
      id: `${root.id}-define-cluster`, name: cluster ? `DEFINE CLUSTER ${cluster}` : 'DEFINE CLUSTER', type: 'cluster', children: [
        propertyNode(`${root.id}-cluster`, 'CLUSTER', cluster),
        propertyNode(`${root.id}-index`, 'INDEX', components.index_component),
        propertyNode(`${root.id}-data`, 'DATA', components.data_component),
        propertyNode(`${root.id}-keys`, 'KEYS', components.key_definition),
        propertyNode(`${root.id}-recordsize`, 'RECORDSIZE', components.storage_allocation?.recordsize || components.storage_allocation?.record_size),
        propertyNode(`${root.id}-shareoptions`, 'SHAREOPTIONS', components.storage_allocation?.shareoptions || components.storage_allocation?.share_options),
      ].filter(Boolean),
    }],
  };
};

const datasetTree = (artifact, root) => {
  const metadata = artifact.metadata || artifact.general_information || {};
  const structure = artifact.structure?.dataset || {};
  const constraints = artifact.constraints || {};
  const name = metadata.dataset_name || artifact.name || artifact.id || 'DATASET';
  const associatedCopybooks = artifact.dependencies?.copybooks || artifact.components?.copybooks_defining;
  const referencedBy = artifact.dependencies?.programs || artifact.components?.programs_using || artifact.relationships;
  return {
    ...root,
    children: [{
      id: `${root.id}-dataset`, name, type: 'dataset', children: [
        propertyNode(`${root.id}-type`, 'Dataset Type', metadata.dataset_type),
        propertyNode(`${root.id}-organization`, 'Organization', metadata.organization),
        propertyNode(`${root.id}-key-length`, 'Key Length', metadata.key_length ?? constraints.key_length),
        propertyNode(`${root.id}-record-length`, 'Record Length', metadata.record_length ?? constraints.record_length),
        {
          id: `${root.id}-copybooks`, name: 'Associated Copybook', type: 'group',
          children: leafNodes(associatedCopybooks, 'copybook'),
        },
        {
          id: `${root.id}-referenced-by`, name: 'Referenced By', type: 'group',
          children: leafNodes(referencedBy, 'reference'),
        },
      ].filter((node) => !node.children || node.children.length),
    }],
  };
};

const normalizeNode = (node) => ({
  id: node.id,
  label: node.label || node.name,
  type: node.type,
  metadata: node.metadata || node.meta || [],
  children: asArray(node.children).map(normalizeNode),
});

const createTree = (artifact) => {
  const artifactType = String(artifact?.artifact_type || artifact?.type || (artifact?.fields ? 'COPYBOOK' : 'DATASET')).toUpperCase();
  const artifactNode = {
    id: `${artifactType}-${artifact.id || artifact.name || 'artifact'}`,
    name: artifact.source_file || artifact.filepath || artifact.name || artifact.id || artifactType,
    type: artifactType.toLowerCase(),
    children: [],
  };
  const tree = artifactType === 'COPYBOOK' ? copybookTree(artifact, artifactNode)
    : artifactType === 'COBOL' ? programTree(artifact, artifactNode)
      : artifactType === 'JCL' ? jclTree(artifact, artifactNode)
        : artifactType === 'IDCAMS' ? idcamsTree(artifact, artifactNode)
          : datasetTree(artifact, artifactNode);
  const labels = { COBOL: 'Program', COPYBOOK: 'Copybook', JCL: 'JCL', IDCAMS: 'IDCAMS', DATASET: 'Dataset' };
  return normalizeNode({
    id: `artifact-type-${tree.id}`,
    name: labels[artifactType] || 'Artifact',
    type: 'artifact',
    children: [tree],
  });
};

const matches = (node, query) => node.label.toLowerCase().includes(query)
  || asArray(node.metadata).some((value) => String(value).toLowerCase().includes(query))
  || asArray(node.children).some((child) => matches(child, query));

const collectBranchIds = (node, query, ids = new Set()) => {
  if (matches(node, query)) ids.add(node.id);
  asArray(node.children).forEach((child) => collectBranchIds(child, query, ids));
  return ids;
};

const NodeIcon = ({ node, hasChildren }) => {
  if (node.type === 'dataset') return <Database size={13} className="shrink-0 text-zinc-500" />;
  if (hasChildren) return <Folder size={13} className="shrink-0 text-zinc-500" />;
  return node.type === 'field' || node.type === 'property'
    ? <FileText size={13} className="shrink-0 text-zinc-400" />
    : <FileCode2 size={13} className="shrink-0 text-zinc-400" />;
};

const TreeNode = ({ node, depth, expandedIds, onToggle, query }) => {
  const children = asArray(node.children);
  const hasChildren = children.length > 0;
  const isOpen = expandedIds.has(node.id);
  const isMatch = query && node.label.toLowerCase().includes(query);
  if (query && !matches(node, query)) return null;
  return (
    <div role="treeitem" aria-expanded={hasChildren ? isOpen : undefined}>
      <button
        type="button"
        onClick={() => hasChildren && onToggle(node.id)}
        className={`group flex w-full items-center gap-1.5 border-l border-transparent py-1 pr-2 text-left font-mono text-[11px] leading-5 hover:bg-zinc-100 focus:outline-none focus-visible:bg-zinc-100 ${hasChildren ? 'cursor-pointer' : 'cursor-default'} ${isMatch ? 'bg-zinc-100' : ''}`}
        style={{ paddingLeft: `${depth * 16 + 7}px` }}
      >
        <span className="flex h-4 w-3 shrink-0 items-center justify-center text-zinc-500">
          {hasChildren && (isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />)}
        </span>
        <NodeIcon node={node} hasChildren={hasChildren} />
        <span className="min-w-0 truncate text-zinc-800">{node.label}</span>
        {asArray(node.metadata).map((item) => <span key={item} className="ml-1 shrink-0 text-[9px] text-zinc-500">• {item}</span>)}
      </button>
      {hasChildren && isOpen && children.map((child) => (
        <TreeNode key={child.id} node={child} depth={depth + 1} expandedIds={expandedIds} onToggle={onToggle} query={query} />
      ))}
    </div>
  );
};

TreeNode.propTypes = {
  node: PropTypes.object.isRequired,
  depth: PropTypes.number.isRequired,
  expandedIds: PropTypes.instanceOf(Set).isRequired,
  onToggle: PropTypes.func.isRequired,
  query: PropTypes.string.isRequired,
};

const RepositoryStructureViewer = ({ artifact }) => {
  const [query, setQuery] = useState('');
  const tree = useMemo(() => (artifact ? createTree(artifact) : null), [artifact]);
  const [expandedIds, setExpandedIds] = useState(new Set());
  const normalizedQuery = query.trim().toLowerCase();

  useEffect(() => {
    if (tree) setExpandedIds(collectBranchIds(tree, ''));
  }, [tree]);

  const visibleExpandedIds = useMemo(() => {
    if (!tree || !normalizedQuery) return expandedIds;
    return new Set([...expandedIds, ...collectBranchIds(tree, normalizedQuery)]);
  }, [expandedIds, normalizedQuery, tree]);

  const toggleNode = (id) => setExpandedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  if (!artifact || !tree) {
    return <div className="flex h-full items-center justify-center px-6 text-center font-mono text-xs text-zinc-500">Select an artifact from Repository Explorer to inspect its structure.</div>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col font-mono">
      <div className="relative mb-3 shrink-0">
        <Search size={13} className="pointer-events-none absolute left-2.5 top-2.5 text-zinc-400" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter structure..."
          className="w-full border border-zinc-300 bg-white py-1.5 pl-8 pr-2 text-[11px] text-zinc-800 outline-none placeholder:text-zinc-400 focus:border-zinc-600"
          aria-label="Filter repository structure"
        />
      </div>
      <div role="tree" aria-label="Repository artifact structure" className="min-h-0 flex-1 overflow-auto border border-zinc-200 bg-white py-1">
        <TreeNode node={tree} depth={0} expandedIds={visibleExpandedIds} onToggle={toggleNode} query={normalizedQuery} />
        {normalizedQuery && !matches(tree, normalizedQuery) && <p className="px-3 py-2 text-[11px] text-zinc-500">No matching nodes.</p>}
      </div>
    </div>
  );
};

RepositoryStructureViewer.propTypes = { artifact: PropTypes.object };
RepositoryStructureViewer.defaultProps = { artifact: null };

export default RepositoryStructureViewer;

import React, { useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

const TreeNode = ({ label, children, defaultOpen = true }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  
  if (!children) {
    return <div className="pl-4 py-1">{label}</div>;
  }
  
  return (
    <div className="flex flex-col">
      <div 
        className="flex items-center gap-1 py-1 cursor-pointer hover:bg-zinc-100 rounded px-1"
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? <ChevronDown size={14} className="text-zinc-400" /> : <ChevronRight size={14} className="text-zinc-400" />}
        <span className="font-semibold text-zinc-700 font-mono text-[12px]">{label}</span>
      </div>
      {isOpen && (
        <div className="pl-4 border-l border-zinc-200 ml-2">
          {children}
        </div>
      )}
    </div>
  );
};

const asArray = (value) => (Array.isArray(value) ? value : []);

const copybookPayload = (data) => {
  const raw = data?.raw_structure || data;
  // Artifact details can contain the complete canonical artifact, while older
  // repositories return the copybook structure directly. Support both shapes.
  if (raw?.structure && (raw.structure.fields || raw.structure.records || raw.structure.hierarchy)) {
    return raw.structure;
  }
  return raw || {};
};

const fieldLengthFromPicture = (picture) => {
  if (!picture) return null;
  const value = String(picture)
    .replace(/^\s*PIC(?:TURE)?\s+/i, '')
    .replace(/\s+(?:COMP(?:-[1235])?|BINARY|DISPLAY|PACKED-DECIMAL).*$/i, '');
  let length = 0;
  let match;
  const characterPattern = /[AX9Z*](?:\((\d+)\))?/gi;
  while ((match = characterPattern.exec(value))) length += Number(match[1] || 1);
  // A leading plus is represented as a physical sign character in legacy layouts.
  if (value.includes('+')) length += 1;
  return length || null;
};

const pictureLabel = (picture) => String(picture || '')
  .replace(/^\s*PIC(?:TURE)?\s+/i, '')
  .trim();

const buildFieldHierarchy = (fields) => {
  const flatFields = asArray(fields);
  if (!flatFields.length) return [];

  // Most parsers return a flat level-number sequence. Rebuild its hierarchy so
  // each copybook has the same expandable view, even if it was parsed before
  // canonical structures were introduced.
  const hasLevelNumbers = flatFields.every((field) => Number.isFinite(Number(field?.level)));
  if (!hasLevelNumbers) return flatFields;

  const roots = [];
  const stack = [];
  flatFields.forEach((source) => {
    const field = { ...source, level: Number(source.level), children: [] };
    while (stack.length && stack[stack.length - 1].level >= field.level) stack.pop();
    if (stack.length) stack[stack.length - 1].children.push(field);
    else roots.push(field);
    stack.push(field);
  });
  return roots;
};

const CopybookViewer = ({ data }) => {
  const payload = copybookPayload(data);
  const hierarchy = payload.hierarchy || payload.semantic_structure?.record_definition || {};
  const nestedRecords = asArray(payload.records).length
    ? payload.records
    : asArray(hierarchy.records || hierarchy.field_hierarchy);
  const roots = nestedRecords.length ? nestedRecords : buildFieldHierarchy(payload.fields);
  
  const renderField = (field, idx) => {
    const { name, level, pic, length, usage, occurs, redefines, children } = field;
    const hasChildren = children && children.length > 0;
    const resolvedLength = length ?? fieldLengthFromPicture(pic);
    const normalizedPicture = pictureLabel(pic);
    
    const label = (
      <div className="flex flex-wrap items-center gap-2 font-mono text-[12px]">
        {level != null && <span className="text-blue-600 font-bold">{String(level).padStart(2, '0')}</span>}
        <span className="text-zinc-900 font-semibold">{name}</span>
        {normalizedPicture && <span className="text-emerald-600">PIC {normalizedPicture}</span>}
        {resolvedLength != null && <span className="text-zinc-500">({resolvedLength})</span>}
        {usage && <span className="text-indigo-600">USAGE {usage}</span>}
        {occurs && <span className="text-amber-600">OCCURS {occurs}</span>}
        {redefines && <span className="text-purple-600">REDEFINES {redefines}</span>}
      </div>
    );
    
    if (hasChildren) {
      return (
        <TreeNode key={`${name}-${idx}`} label={label}>
          {children.map((child, i) => renderField(child, i))}
        </TreeNode>
      );
    }
    
    return <div key={`${name}-${idx}`} className="pl-4 py-1">{label}</div>;
  };

  if (roots.length === 0) return <div className="text-zinc-400 italic">No record hierarchy found.</div>;

  return (
    <div className="flex flex-col gap-1">
      {roots.map((root, i) => renderField(root, i))}
    </div>
  );
};

const CobolViewer = ({ data }) => {
  const renderList = (items) => {
    if (!items || items.length === 0) return null;
    return items.map((item, i) => {
       if (typeof item === 'string') return <div key={i} className="py-1 font-mono text-[12px] pl-4">{item}</div>;
       return <div key={i} className="py-1 font-mono text-[12px] pl-4"><GenericTree data={item} /></div>;
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {data.divisions?.length > 0 && (
        <TreeNode label="Divisions">
          {renderList(data.divisions)}
        </TreeNode>
      )}
      {data.sections?.length > 0 && (
        <TreeNode label="Sections">
          {renderList(data.sections)}
        </TreeNode>
      )}
      {data.procedures?.length > 0 && (
        <TreeNode label="Paragraphs (Procedures)">
          {renderList(data.procedures)}
        </TreeNode>
      )}
      {data.fields?.length > 0 && (
        <TreeNode label="Record Definitions (Fields)">
          <div className="pl-4"><GenericTree data={data.fields} /></div>
        </TreeNode>
      )}
    </div>
  );
};

const JclViewer = ({ data }) => {
  const jobCard = data.extra_definitions?.find(d => d.job_card)?.job_card;
  const jobName = jobCard?.job_name || "UNKNOWN";
  
  return (
    <div className="flex flex-col gap-2">
      <TreeNode label={`Job Name: ${jobName}`}>
        {jobCard && <div className="pl-4"><GenericTree data={jobCard} /></div>}
      </TreeNode>
      {data.steps?.length > 0 && (
        <TreeNode label="Steps">
          <div className="pl-4"><GenericTree data={data.steps} /></div>
        </TreeNode>
      )}
      {data.exec_statements?.length > 0 && (
        <TreeNode label="EXEC Statements">
          <div className="pl-4"><GenericTree data={data.exec_statements} /></div>
        </TreeNode>
      )}
      {data.dd_statements?.length > 0 && (
        <TreeNode label="DD Statements">
          <div className="pl-4"><GenericTree data={data.dd_statements} /></div>
        </TreeNode>
      )}
    </div>
  );
};

const IdcamsViewer = ({ data }) => {
  const extraDef = data.extra_definitions?.[0] || {};
  
  return (
    <div className="flex flex-col gap-2">
      {data.exec_statements?.length > 0 && (
        <TreeNode label="DEFINE CLUSTER (EXEC Statements)">
          <div className="pl-4"><GenericTree data={data.exec_statements} /></div>
        </TreeNode>
      )}
      {extraDef.data_component && Object.keys(extraDef.data_component).length > 0 && (
        <TreeNode label="DATA Component">
          <div className="pl-4"><GenericTree data={extraDef.data_component} /></div>
        </TreeNode>
      )}
      {extraDef.index_component && Object.keys(extraDef.index_component).length > 0 && (
        <TreeNode label="INDEX Component">
          <div className="pl-4"><GenericTree data={extraDef.index_component} /></div>
        </TreeNode>
      )}
      {extraDef.path && Object.keys(extraDef.path).length > 0 && (
        <TreeNode label="PATH">
          <div className="pl-4"><GenericTree data={extraDef.path} /></div>
        </TreeNode>
      )}
      {extraDef.alternate_index && Object.keys(extraDef.alternate_index).length > 0 && (
        <TreeNode label="Alternate Index">
          <div className="pl-4"><GenericTree data={extraDef.alternate_index} /></div>
        </TreeNode>
      )}
    </div>
  );
};

const GenericTree = ({ data }) => {
  if (data === null || data === undefined) return null;
  if (typeof data !== 'object') return <span className="font-mono text-[12px] text-emerald-600">{String(data)}</span>;
  
  if (Array.isArray(data)) {
    if (data.length === 0) return null;
    return (
      <div className="flex flex-col gap-1">
        {data.map((item, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-zinc-400 select-none">-</span>
            <div><GenericTree data={item} /></div>
          </div>
        ))}
      </div>
    );
  }
  
  const entries = Object.entries(data).filter(([k, v]) => {
    if (v === null || v === undefined) return false;
    if (Array.isArray(v) && v.length === 0) return false;
    if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) return false;
    return true;
  });
  
  if (entries.length === 0) return null;
  
  return (
    <div className="flex flex-col gap-1">
      {entries.map(([key, val]) => (
        <div key={key} className="flex flex-col">
          {typeof val === 'object' ? (
            <TreeNode label={key}>
              <div className="pl-4"><GenericTree data={val} /></div>
            </TreeNode>
          ) : (
            <div className="flex items-start gap-2 pl-4 py-0.5">
              <span className="text-blue-600 font-semibold font-mono text-[12px]">{key}:</span>
              <span className="font-mono text-[12px] text-zinc-700">{String(val)}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const formatProperty = (value) => {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
};

const ArtifactStructureNode = ({ node, path }) => {
  const children = asArray(node.children);
  const properties = node.properties || {};
  const label = (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[12px]">
      <span className="font-semibold text-zinc-900">{node.name}</span>
      <span className="text-[10px] uppercase tracking-wide text-blue-600">{String(node.type || 'node').replace(/_/g, ' ')}</span>
      {Object.entries(properties).map(([key, value]) => (
        <span key={key} className="text-zinc-500">
          <span className="text-zinc-400">{key.replace(/_/g, ' ')}:</span> {formatProperty(value)}
        </span>
      ))}
    </div>
  );

  if (!children.length) return <div className="pl-4 py-1">{label}</div>;
  return (
    <TreeNode label={label} key={path}>
      {children.map((child, index) => <ArtifactStructureNode key={`${path}-${index}`} node={child} path={`${path}-${index}`} />)}
    </TreeNode>
  );
};

const ArtifactTreeView = ({ structure }) => {
  const nodes = asArray(structure.nodes);
  if (!structure.available || !nodes.length) {
    return (
      <div className="space-y-3">
        <p className="text-zinc-500 italic">{structure.message || 'No parsed structure is available.'}</p>
        {structure.metadata && Object.keys(structure.metadata).length > 0 && <GenericTree data={structure.metadata} />}
      </div>
    );
  }
  return <div className="flex flex-col gap-1">{nodes.map((node, index) => <ArtifactStructureNode key={index} node={node} path={String(index)} />)}</div>;
};

const JclStructureView = ({ structure }) => <ArtifactTreeView structure={structure} />;
const CobolProgramStructureView = ({ structure }) => <ArtifactTreeView structure={structure} />;
const IdcamsStructureView = ({ structure }) => <ArtifactTreeView structure={structure} />;
const CatalogStructureView = ({ structure }) => <ArtifactTreeView structure={structure} />;
const GenericStructureView = ({ structure }) => <ArtifactTreeView structure={structure} />;

const StructureViewer = ({ data, artifactType }) => {
  if (!data) return <div className="text-zinc-400">No structure data available.</div>;

  const normalizedStructure = data?.structure_view || data?.structureView;
  if (normalizedStructure) {
    switch (String(normalizedStructure.artifact_type || artifactType).toUpperCase()) {
      case 'COPYBOOK':
        return <CopybookViewer data={data} />;
      case 'JCL':
        return <JclStructureView structure={normalizedStructure} />;
      case 'COBOL':
      case 'CBL':
        return <CobolProgramStructureView structure={normalizedStructure} />;
      case 'IDCAMS':
        return <IdcamsStructureView structure={normalizedStructure} />;
      case 'CATALOG':
        return <CatalogStructureView structure={normalizedStructure} />;
      default:
        return <GenericStructureView structure={normalizedStructure} />;
    }
  }

  const inferredType = artifactType
    || data?.identity?.artifact_type
    || data?.artifact_type
    || data?.type
    || (data?.fields || data?.structure?.fields ? 'COPYBOOK' : '');

  switch (String(inferredType).toUpperCase()) {
    case 'COPYBOOK':
      return <CopybookViewer data={data} />;
    case 'COBOL':
      return <CobolViewer data={data} />;
    case 'JCL':
      return <JclViewer data={data} />;
    case 'IDCAMS':
      return <IdcamsViewer data={data} />;
    default:
      return <GenericTree data={data} />;
  }
};

export default StructureViewer;

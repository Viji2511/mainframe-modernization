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

const CopybookViewer = ({ data }) => {
  let roots = data.records || [];
  
  if (roots.length === 0 && data.fields && data.fields.length > 0) {
    const stack = [];
    const newRoots = [];
    
    // Create deep copies to avoid mutating original data
    const fields = JSON.parse(JSON.stringify(data.fields));
    
    fields.forEach(f => {
      if (!f.children) f.children = [];
      const level = parseInt(f.level, 10) || 0;
      f.level = level;
      
      while(stack.length > 0 && stack[stack.length - 1].level >= level) {
        stack.pop();
      }
      
      if (stack.length > 0) {
        stack[stack.length - 1].children.push(f);
      } else {
        newRoots.push(f);
      }
      
      stack.push(f);
    });
    
    roots = newRoots;
  }
  
  const renderField = (field, idx) => {
    const { name, level, pic, length, usage, occurs, redefines, children } = field;
    const hasChildren = children && children.length > 0;
    
    const label = (
      <div className="flex flex-wrap items-center gap-2 font-mono text-[12px]">
        {level != null && <span className="text-blue-600 font-bold">{String(level).padStart(2, '0')}</span>}
        <span className="text-zinc-900 font-semibold">{name}</span>
        {pic && <span className="text-emerald-600">PIC {pic}</span>}
        {length != null && <span className="text-zinc-500">({length})</span>}
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

const StructureViewer = ({ data, artifactType }) => {
  if (!data) return <div className="text-zinc-400">No structure data available.</div>;
  
  switch (artifactType?.toUpperCase()) {
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

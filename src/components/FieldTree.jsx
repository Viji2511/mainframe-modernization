import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronRight, Folder, FileText } from 'lucide-react';

const FieldNode = ({ field, depth }) => {
  const [isOpen, setIsOpen] = useState(true);
  const hasChildren = field.children && field.children.length > 0;

  // Determine Level badge color with black outlines
  const getLevelStyle = (level) => {
    if (level === 1 || level === 77) return 'bg-black text-[#00ff4c] border-black font-bold';
    if (level === 5) return 'bg-blue-100 text-blue-900 border-black font-bold';
    if (level === 10) return 'bg-cyan-100 text-cyan-900 border-black font-bold';
    if (level === 15) return 'bg-green-100 text-green-950 border-black font-bold';
    return 'bg-zinc-100 text-zinc-800 border-black font-semibold';
  };

  return (
    <div className="font-mono text-xs select-none">
      {/* Node Header Row */}
      <div 
        className="flex items-center gap-2 py-1.5 px-2 hover:bg-zinc-100 rounded border border-transparent hover:border-black cursor-pointer"
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && setIsOpen(!isOpen)}
      >
        {/* Collapse Arrow */}
        <div className="w-4 h-4 flex items-center justify-center text-black">
          {hasChildren ? (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : null}
        </div>

        {/* Level Badge */}
        <span className={`text-[9px] border px-1 rounded shrink-0 ${getLevelStyle(field.level)}`}>
          {field.level.toString().padStart(2, '0')}
        </span>

        {/* Folder vs Variable Icon */}
        {hasChildren ? (
          <Folder size={12} className="text-yellow-600/80 shrink-0" />
        ) : (
          <FileText size={12} className="text-zinc-500 shrink-0" />
        )}

        {/* Variable Name */}
        <span className={`truncate font-bold ${hasChildren ? 'text-black' : 'text-zinc-700'}`}>
          {field.name}
        </span>

        {/* Field Details info spacer */}
        <div className="ml-auto flex items-center gap-4 text-[9px] text-zinc-500 shrink-0 font-bold">
          {field.pic && (
            <span className="bg-zinc-200 border border-black text-black px-1.5 py-0.5 rounded">
              PIC {field.pic}
            </span>
          )}
          {field.cobol_type && (
            <span className="text-zinc-800 uppercase">
              {field.cobol_type}
            </span>
          )}
          {field.length !== null && field.length !== undefined && (
            <span>
              {field.length}B
            </span>
          )}
          {field.offset !== null && field.offset !== undefined && (
            <span>
              off:{field.offset}
            </span>
          )}
          {field.redefines && (
            <span className="text-pink-600 italic">
              redefines {field.redefines}
            </span>
          )}
        </div>
      </div>

      {/* Render children nodes recursively */}
      {hasChildren && isOpen && (
        <div className="border-l-2 border-black ml-6 pl-1 space-y-0.5 mt-0.5">
          {field.children.map((child, idx) => (
            <FieldNode key={idx} field={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
};

FieldNode.propTypes = {
  field: PropTypes.object.isRequired,
  depth: PropTypes.number.isRequired,
};

const FieldTree = ({ fields }) => {
  if (!fields || fields.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center border-2 border-black rounded bg-white text-zinc-500 text-xs font-mono">
        No field nodes discovered to render.
      </div>
    );
  }

  return (
    <div className="border-2 border-black rounded bg-white p-4 overflow-x-auto space-y-1 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]">
      {fields.map((field, idx) => (
        <FieldNode key={idx} field={field} depth={0} />
      ))}
    </div>
  );
};

FieldTree.propTypes = {
  fields: PropTypes.array.isRequired,
};

export default FieldTree;

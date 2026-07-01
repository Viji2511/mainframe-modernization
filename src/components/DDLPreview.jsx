import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Copy, Check, ShieldAlert } from 'lucide-react';
import { generateDDL } from '../utils/ddlGenerator';

const DDLPreview = ({ dsn, fields, dialect }) => {
  const [copied, setCopied] = useState(false);
  const ddlSql = generateDDL(dsn, fields, dialect);

  const handleCopy = () => {
    navigator.clipboard.writeText(ddlSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col border-2 border-black rounded bg-white overflow-hidden h-[500px] shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]">
      {/* Header controls */}
      <div className="flex items-center justify-between border-b-2 border-black bg-white px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] font-bold text-zinc-500 uppercase tracking-widest">SQL DIALECT:</span>
          <span className="font-mono text-xs font-bold text-blue-600 uppercase border-b border-blue-600">{dialect}</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 border-2 border-black bg-[#00ff4c] px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-black hover:bg-[#00e676]"
        >
          {copied ? (
            <>
              <Check size={10} className="text-black" /> Copied!
            </>
          ) : (
            <>
              <Copy size={10} /> Copy DDL
            </>
          )}
        </button>
      </div>

      {/* SQL Script body */}
      <div className="flex-1 overflow-auto p-4 bg-[#0d1117] font-mono text-[11px] text-[#e6edf3] leading-relaxed whitespace-pre select-text">
        {ddlSql}
      </div>

      {/* Database Warning note */}
      <div className="border-t-2 border-black bg-[#f4f4f0] p-3 flex gap-2 items-start">
        <ShieldAlert size={14} className="text-yellow-600 shrink-0 mt-0.5" />
        <span className="text-[9px] text-zinc-600 font-sans font-medium uppercase tracking-wide leading-tight">
          This mapping is generated directly from source copybook variable storage formats. Confirm numeric bounds before production deployment.
        </span>
      </div>
    </div>
  );
};

DDLPreview.propTypes = {
  dsn: PropTypes.string.isRequired,
  fields: PropTypes.array.isRequired,
  dialect: PropTypes.string.isRequired,
};

export default DDLPreview;

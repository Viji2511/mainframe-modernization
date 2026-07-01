import React from 'react';
import PropTypes from 'prop-types';
import { Terminal, Key, FileSymlink, AlertCircle } from 'lucide-react';

const ProgramCard = ({ analysis }) => {
  const getOpBadgeColor = (op) => {
    const o = op.toUpperCase();
    if (o.includes('READ')) return 'bg-blue-100 text-blue-900 border border-black font-bold';
    if (o.includes('WRITE')) return 'bg-green-100 text-green-950 border border-black font-bold';
    if (o.includes('REWRITE')) return 'bg-yellow-100 text-yellow-955 border border-black font-bold';
    if (o.includes('DELETE')) return 'bg-red-100 text-red-700 border border-black font-bold';
    return 'bg-zinc-100 text-zinc-800 border border-black font-bold';
  };

  return (
    <div className="border-2 border-black rounded bg-white p-4 flex flex-col justify-between hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] transition-all shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
      {/* Title & Ops Header */}
      <div>
        <div className="flex items-center gap-2 border-b-2 border-black pb-2.5 mb-3 justify-between">
          <div className="flex items-center gap-1.5 min-w-0">
            <Terminal size={12} className="text-black shrink-0" />
            <span className="font-mono text-xs font-bold text-black truncate">
              {analysis.program_name}
            </span>
          </div>
          <div className="flex gap-1.5 shrink-0 flex-wrap">
            {analysis.operations.map((op, i) => (
              <span
                key={i}
                className={`text-[8px] border px-1.5 py-0.5 rounded tracking-wide uppercase font-mono ${getOpBadgeColor(
                  op
                )}`}
              >
                {op}
              </span>
            ))}
          </div>
        </div>

        {/* Card Properties List */}
        <div className="space-y-2 text-[10px] font-mono text-black">
          {/* Key Fields */}
          <div className="flex items-start gap-2">
            <Key size={12} className="text-black shrink-0 mt-0.5" />
            <div className="break-all font-medium">
              <span className="text-zinc-500 uppercase text-[9px] font-bold">Keys:</span>{' '}
              {analysis.key_fields.length > 0 ? (
                <span className="text-yellow-600 font-bold">{analysis.key_fields.join(', ')}</span>
              ) : (
                <span className="text-zinc-400">None detected</span>
              )}
            </div>
          </div>

          {/* Related Files */}
          <div className="flex items-start gap-2">
            <FileSymlink size={12} className="text-black shrink-0 mt-0.5" />
            <div className="break-all font-medium">
              <span className="text-zinc-500 uppercase text-[9px] font-bold">Relations:</span>{' '}
              {analysis.related_files.length > 0 ? (
                <span className="text-purple-700 font-bold">{analysis.related_files.join(', ')}</span>
              ) : (
                <span className="text-zinc-400">None mapped</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Rules count badge footer */}
      <div className="mt-4 border-t border-zinc-200 pt-2.5 flex items-center justify-between font-mono text-[9px] text-zinc-500 font-bold">
        <span className="flex items-center gap-1 uppercase">
          <AlertCircle size={10} /> {analysis.business_rules.length} Business rules
        </span>
        <span className="text-zinc-400 uppercase">complete</span>
      </div>
    </div>
  );
};

ProgramCard.propTypes = {
  analysis: PropTypes.object.isRequired,
};

export default ProgramCard;

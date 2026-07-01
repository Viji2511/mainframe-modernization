import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Download, Filter } from 'lucide-react';

const BusinessRulesTable = ({ rules }) => {
  const [filterType, setFilterType] = useState('all');

  const usageTypes = ['all', 'key', 'lookup', 'validation', 'relationship', 'output', 'other'];

  const getUsageBadgeStyle = (usage) => {
    switch (usage) {
      case 'key':
        return 'bg-purple-200 text-purple-900 border border-black font-bold';
      case 'lookup':
        return 'bg-blue-200 text-blue-900 border border-black font-bold';
      case 'validation':
        return 'bg-orange-200 text-orange-950 border border-black font-bold';
      case 'relationship':
        return 'bg-green-200 text-green-950 border border-black font-bold';
      case 'output':
        return 'bg-zinc-200 text-zinc-900 border border-black font-bold';
      default:
        return 'bg-zinc-100 text-zinc-800 border border-black font-bold';
    }
  };

  const filteredRules = filterType === 'all' 
    ? rules 
    : rules.filter((r) => r.usage === filterType);

  const handleExportCSV = () => {
    if (rules.length === 0) return;
    
    const headers = ['Field Name', 'Usage Type', 'Description', 'Found In Program'];
    const rows = rules.map((r) => [
      r.field_name,
      r.usage,
      `"${r.description.replace(/"/g, '""')}"`,
      r.found_in
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'business_rules_extract.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-4">
      {/* Filtering & Export bar */}
      <div className="flex flex-col md:flex-row gap-3 items-start md:items-center justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Filter size={12} className="text-black mr-1 shrink-0" />
          {usageTypes.map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`text-[9px] font-bold font-mono uppercase px-2.5 py-1 rounded border-2 border-black transition-colors ${
                filterType === type
                  ? 'bg-[#00ff4c] text-black shadow-[1px_1px_0px_0px_rgba(0,0,0,1)]'
                  : 'bg-white text-zinc-500 hover:bg-zinc-100 hover:text-black'
              }`}
            >
              {type}
            </button>
          ))}
        </div>
        <button
          onClick={handleExportCSV}
          disabled={rules.length === 0}
          className="flex items-center gap-1.5 border-2 border-black bg-white px-3 py-1.5 text-[10px] font-bold font-mono uppercase text-black hover:bg-zinc-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-nowrap shrink-0"
        >
          <Download size={12} /> Export CSV
        </button>
      </div>

      {/* Grid container */}
      <div className="overflow-x-auto border-2 border-black rounded bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
        <table className="min-w-full divide-y-2 divide-black text-left">
          <thead className="bg-[#f4f4f0] font-mono text-[9px] uppercase text-black tracking-wider font-bold">
            <tr>
              <th className="px-4 py-3 border-r-2 border-black">Field Name</th>
              <th className="px-4 py-3 border-r-2 border-black">Usage</th>
              <th className="px-4 py-3 border-r-2 border-black">Description</th>
              <th className="px-4 py-3">Found In</th>
            </tr>
          </thead>
          <tbody className="divide-y-2 divide-black bg-white text-xs leading-relaxed text-black font-mono">
            {filteredRules.length > 0 ? (
              filteredRules.map((rule, idx) => (
                <tr key={idx} className="hover:bg-zinc-50/50 transition-colors border-black">
                  <td className="px-4 py-3 font-bold text-blue-600 border-r-2 border-black break-all">
                    {rule.field_name}
                  </td>
                  <td className="px-4 py-3 border-r-2 border-black">
                    <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded tracking-wide ${getUsageBadgeStyle(rule.usage)}`}>
                      {rule.usage}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-800 font-sans font-medium min-w-[200px] border-r-2 border-black">
                    {rule.description}
                  </td>
                  <td className="px-4 py-3 text-[10px] text-zinc-500">
                    {rule.found_in}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500 font-sans">
                  No matching business logic rule definitions found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

BusinessRulesTable.propTypes = {
  rules: PropTypes.array.isRequired,
};

export default BusinessRulesTable;

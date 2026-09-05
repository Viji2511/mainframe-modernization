import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Copy, Check, ShieldAlert, Maximize2, X, Database } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useApi } from '../hooks/useApi';

const DDLPreview = ({ jobId, artifactId, dsn, fields, dialect }) => {
  const [copied, setCopied] = useState(false);
  const [ddlSql, setDdlSql] = useState(null);
  const [ddlMeta, setDdlMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const api = useApi();

  useEffect(() => {
    let active = true;
    const fetchDdl = async () => {
      if (!jobId || !artifactId || artifactId === 'UNKNOWN') {
        if (active) setError("No generated SQL is available for this artifact.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await api.get(`/api/repository/${jobId}/artifact-details/${encodeURIComponent(artifactId)}`);
        if (active) {
          if (res.detailed_schema && res.detailed_schema.ddl) {
            setDdlSql(res.detailed_schema.ddl);
            setDdlMeta(res.detailed_schema);
          } else {
            setError(res.detailed_schema?.warnings?.[0]?.reason || "No canonical generated SQL is available for this artifact.");
          }
        }
      } catch (err) {
        if (active) {
          setError("Unable to load generated SQL.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    fetchDdl();
    return () => { active = false; };
  }, [jobId, artifactId, api]);

  const handleCopy = () => {
    if (!ddlSql) return;
    navigator.clipboard.writeText(ddlSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!ddlSql) return;
    const blob = new Blob([ddlSql], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${artifactId || dsn}_schema.sql`;
    link.click();
  };

  const Modal = () => {
    return createPortal(
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
        <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-lg bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 m-auto relative">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 bg-zinc-50">
            <div>
              <h3 className="font-mono text-sm font-bold text-gray-800">Generated PostgreSQL DDL</h3>
              <div className="text-xs text-zinc-500 font-mono mt-0.5">Artifact: {artifactId || dsn}</div>
            </div>
            <button onClick={() => setIsModalOpen(false)} className="rounded-md p-1 hover:bg-zinc-200 transition-colors">
              <X size={18} className="text-zinc-500" />
            </button>
          </div>
          
          <div className="flex-1 overflow-auto p-4 bg-[#0d1117] font-mono text-[13px] text-[#e6edf3] leading-relaxed whitespace-pre select-text">
            {ddlSql}
          </div>
          
          <div className="border-t border-zinc-200 bg-zinc-50 p-3 flex justify-end gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 border border-gray-300 bg-white px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider text-gray-700 hover:bg-zinc-100 rounded shadow-sm"
            >
              {copied ? <><Check size={14} className="text-green-600"/> Copied!</> : <><Copy size={14} /> Copy SQL</>}
            </button>
            <button
              onClick={() => setIsModalOpen(false)}
              className="flex items-center gap-1.5 border border-transparent bg-blue-600 text-white px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider hover:bg-blue-700 rounded shadow-sm"
            >
              Close
            </button>
          </div>
        </div>
      </div>,
      document.body
    );
  };

  if (loading) {
    return (
      <div className="flex flex-col border border-gray-200 rounded bg-white overflow-hidden h-[500px] shadow-sm items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
        <p className="font-mono text-xs text-zinc-500">Loading generated SQL...</p>
      </div>
    );
  }

  if (error || !ddlSql) {
    return (
      <div className="flex flex-col border border-gray-200 rounded bg-white overflow-hidden h-[500px] shadow-sm items-center justify-center p-6 text-center">
        <Database size={40} className="mb-3 text-zinc-300" />
        <h3 className="font-mono text-sm font-bold text-gray-900 uppercase">SQL Generation Unavailable</h3>
        <p className="text-xs font-sans text-zinc-500 mt-2 max-w-xs">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col border border-gray-200 rounded bg-white overflow-hidden h-[500px] shadow-sm">
      {/* Header controls */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] font-bold text-zinc-500 uppercase tracking-widest">SQL DIALECT:</span>
          <span className="font-mono text-xs font-bold text-blue-600 uppercase border-b border-blue-600">{dialect}</span>
          {ddlMeta?.status && <span className={`font-mono text-[9px] font-bold uppercase ${ddlMeta.status === 'GENERATED' ? 'text-green-600' : 'text-amber-600'}`}>{ddlMeta.status.replaceAll('_', ' ')}</span>}
          {ddlMeta?.validation?.validation_status && <span className="font-mono text-[9px] font-bold uppercase text-zinc-600">PG: {ddlMeta.validation.validation_status.replaceAll('_', ' ')}</span>}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-1.5 border border-gray-200 bg-white px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-gray-700 hover:bg-zinc-100 shadow-sm rounded"
          >
            <Maximize2 size={10} /> View Generated SQL
          </button>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 border border-gray-200 bg-blue-600 text-white px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-wider hover:bg-blue-700 shadow-sm rounded"
          >
            {copied ? <><Check size={10} /> Copied!</> : <><Copy size={10} /> Copy</>}
          </button>
        </div>
      </div>

      {/* SQL Script body */}
      <div className="flex-1 overflow-auto p-4 bg-[#0d1117] font-mono text-[11px] text-[#e6edf3] leading-relaxed whitespace-pre select-text">
        {ddlSql}
      </div>

      {/* Database Warning note */}
      <div className="border-t border-gray-200 bg-[#f3f4f6] p-3 flex gap-2 items-start justify-between">
        <div className="flex gap-2 items-start">
          <ShieldAlert size={14} className="text-blue-600 shrink-0 mt-0.5" />
          <span className="text-[9px] text-zinc-600 font-sans font-medium uppercase tracking-wide leading-tight">Authoritative backend DDL{ddlMeta?.ddl_hash ? ` · ${ddlMeta.ddl_hash.slice(0, 12)}` : ''}.</span>
        </div>
        <button onClick={handleDownload} className="text-[9px] text-blue-600 font-bold uppercase tracking-wide hover:underline whitespace-nowrap">
          Download SQL
        </button>
      </div>
      {ddlMeta?.warnings?.length > 0 && <div className="border-t border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">{ddlMeta.warnings.length} structural review warning(s): {ddlMeta.warnings.map(w => w.reason).filter(Boolean).join(' ')}</div>}
      
      {isModalOpen && <Modal />}
    </div>
  );
};

DDLPreview.propTypes = {
  jobId: PropTypes.string,
  artifactId: PropTypes.string,
  dsn: PropTypes.string.isRequired,
  fields: PropTypes.array.isRequired,
  dialect: PropTypes.string.isRequired,
};

export default DDLPreview;

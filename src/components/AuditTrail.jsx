import React, { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';

const statusTone = (status, severity) => {
  if (status === 'FAILED' || ['ERROR', 'CRITICAL'].includes(severity)) return 'text-red-700 bg-red-50 border-red-200';
  if (status === 'REVIEW_REQUIRED' || severity === 'WARNING') return 'text-amber-700 bg-amber-50 border-amber-200';
  return 'text-emerald-700 bg-emerald-50 border-emerald-200';
};

const AuditTrail = ({ jobId, artifactId, onClearArtifact, showHeader = true, fullPage = false }) => {
  const api = useApi();
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [view, setView] = useState('timeline');
  const [stage, setStage] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId) return undefined;
    setLoading(true);
    setError(null);
    const query = new URLSearchParams();
    if (stage) query.set('stage', stage);
    if (status) query.set('status', status);
    if (artifactId) query.set('artifact_id', artifactId);
    api.get(`/api/repository/${jobId}/audit?${query.toString()}`)
      .then((result) => {
        setEvents(result.events || []);
        setSummary(result.summary || null);
      })
      .catch((requestError) => { setEvents([]); setSummary(null); setError(requestError.message || 'Failed to load audit trail'); })
      .finally(() => setLoading(false));
  }, [jobId, api, stage, status, artifactId]);

  const visibleEvents = useMemo(() => view === 'decisions'
    ? events.filter((event) => event.status === 'REVIEW_REQUIRED' || ['REDEFINES', 'OCCURS'].includes(event.stage) || ['WARNING', 'ERROR', 'CRITICAL'].includes(event.severity))
    : events, [events, view]);
  const stages = [...new Set(events.map((event) => event.stage).filter(Boolean))].sort();

  if (!jobId) return null;
  return (
    <section className="bg-white border border-gray-200 rounded-lg shadow-sm p-3 space-y-3">
      {showHeader && <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2">
        <div>
          <h2 className="text-sm font-bold font-mono text-gray-900">AUDIT TRAIL</h2>
          <p className="text-[10px] text-zinc-500 font-mono">Persistent execution evidence and modernization decisions</p>
          {artifactId && <button onClick={onClearArtifact} className="mt-1 text-[10px] font-mono text-blue-700 underline">Filtering selected artifact: {artifactId} (clear)</button>}
        </div>
        <div className="flex gap-1">
          {['summary', 'timeline', 'decisions'].map((item) => <button key={item} onClick={() => setView(item)} className={`px-2 py-1 text-[10px] font-mono font-bold uppercase border rounded ${view === item ? 'bg-zinc-900 text-white' : 'bg-white text-zinc-600'}`}>{item === 'decisions' ? 'Review' : item}</button>)}
        </div>
      </div>}

      {!showHeader && <div className="flex justify-end border-b pb-2"><div className="flex gap-1">
        {['summary', 'timeline', 'decisions'].map((item) => <button key={item} onClick={() => setView(item)} className={`px-2 py-1 text-[10px] font-mono font-bold uppercase border rounded ${view === item ? 'bg-zinc-900 text-white' : 'bg-white text-zinc-600'}`}>{item === 'decisions' ? 'Review' : item}</button>)}
      </div></div>}

      {loading && <div className="p-4 text-xs font-mono text-zinc-500">Loading audit trail...</div>}
      {error && <div className="rounded border border-red-200 bg-red-50 p-3 text-xs font-mono text-red-700">Failed to load audit trail: {error}</div>}

      {!loading && !error && view === 'summary' && <div className="grid grid-cols-2 md:grid-cols-5 gap-2 font-mono text-xs">
        {[['Events', summary?.total], ['Success', summary?.success], ['Warnings', summary?.warnings], ['Review', summary?.review_required], ['Failed', summary?.failed]].map(([label, value]) => <div key={label} className="border rounded p-2"><div className="text-[9px] uppercase text-zinc-500">{label}</div><div className="font-bold text-base">{value ?? 0}</div></div>)}
        <div className="col-span-2 md:col-span-5 border rounded p-2 text-[11px]">
          {Object.entries(summary?.by_stage || {}).map(([name, counts]) => <span key={name} className="inline-block mr-4 mb-1"><b>{name}</b>: {counts.total} events / {counts.review_required} review / {counts.failed} failed</span>)}
        </div>
      </div>}

      {!loading && !error && view !== 'summary' && <>
        <div className="flex gap-2 text-xs font-mono">
          <select value={stage} onChange={(e) => setStage(e.target.value)} className="border rounded px-2 py-1"><option value="">All stages</option>{stages.map((item) => <option key={item}>{item}</option>)}</select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="border rounded px-2 py-1"><option value="">All statuses</option><option>SUCCESS</option><option>REVIEW_REQUIRED</option><option>FAILED</option><option>SKIPPED</option></select>
        </div>
        <div className={`${fullPage ? '' : 'max-h-72 overflow-auto'} border rounded divide-y font-mono text-[11px]`}>
          {visibleEvents.length === 0 && <div className="p-3 text-zinc-500">No matching audit events persisted for this analysis.</div>}
          {visibleEvents.map((event) => <button type="button" onClick={() => setSelected(event)} key={event.audit_id} className="block w-full text-left p-2 hover:bg-zinc-50">
            <div className="flex flex-wrap gap-x-2 gap-y-1 items-center"><span className="text-zinc-500">{new Date(event.timestamp).toLocaleTimeString()}</span><span className="font-bold">{event.stage}</span><span className={`border rounded px-1 ${statusTone(event.status, event.severity)}`}>{event.status}</span><span>{event.artifact_name || event.component}</span></div>
            <div className="text-zinc-700 mt-1">{event.summary}</div>
          </button>)}
        </div>
      </>}

      {selected && <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
        <div className="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] overflow-auto p-5 font-mono text-xs" onClick={(event) => event.stopPropagation()}>
          <div className="flex justify-between gap-4 border-b pb-2 mb-3"><h3 className="font-bold">Audit event details</h3><button onClick={() => setSelected(null)}>×</button></div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">{[['Event ID', selected.audit_id], ['Timestamp', selected.timestamp], ['Repository', selected.repository_id], ['Artifact', selected.artifact_name || selected.artifact_id], ['Stage', selected.stage], ['Component', selected.component], ['Action', selected.action], ['Status', selected.status], ['Severity', selected.severity], ['Confidence', selected.confidence], ['Rule', selected.rule_id], ['Strategy', selected.strategy], ['Source', selected.source_file], ['Source line', selected.source_line]].map(([label, value]) => <div key={label}><span className="text-zinc-500">{label}: </span>{value ?? '—'}</div>)}</div>
          <div className="mt-3"><b>Decision</b><p className="mt-1 whitespace-pre-wrap">{selected.summary}</p></div>
          <div className="mt-3"><b>Evidence references</b><p className="mt-1 break-all">{selected.evidence_ids?.join(', ') || 'No extracted evidence reference'}</p></div>
          <div className="mt-3"><b>Details</b><pre className="mt-1 bg-zinc-50 border rounded p-2 overflow-auto">{JSON.stringify(selected.details || {}, null, 2)}</pre></div>
        </div>
      </div>}
    </section>
  );
};

export default AuditTrail;

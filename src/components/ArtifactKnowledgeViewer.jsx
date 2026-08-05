import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { useApi } from '../hooks/useApi';
import ArtifactDetails from './ArtifactDetails';
import DependencyPanel from './DependencyPanel';
import { Loader2, ChevronRight, X } from 'lucide-react';

const ObjectViewer = ({ data, depth = 0 }) => {
  if (data === null || data === undefined) return <span className="text-zinc-400">null</span>;
  if (typeof data !== 'object') return <span className="text-emerald-600">{String(data)}</span>;
  
  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-zinc-400">[]</span>;
    return (
      <div className="flex flex-col gap-1">
        {data.map((item, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-zinc-400 select-none">-</span>
            <div><ObjectViewer data={item} depth={depth + 1} /></div>
          </div>
        ))}
      </div>
    );
  }

  const keys = Object.keys(data);
  if (keys.length === 0) return <span className="text-zinc-400">{'{}'}</span>;

  return (
    <div className="flex flex-col gap-1">
      {keys.map((key) => (
        <div key={key} className="flex items-start gap-2">
          <span className="text-blue-600 font-semibold">{key}:</span>
          <div className="flex-1"><ObjectViewer data={data[key]} depth={depth + 1} /></div>
        </div>
      ))}
    </div>
  );
};

import { createPortal } from 'react-dom';

const Modal = ({ title, data, onClose }) => {
  const modalContent = (
    <div className="fixed top-0 left-0 w-screen h-screen z-[9999] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200 m-auto relative">
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 bg-zinc-50">
          <h3 className="font-mono text-sm font-bold text-gray-800">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-zinc-200 transition-colors">
            <X size={18} className="text-zinc-500" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4 font-mono text-[13px] text-zinc-700 bg-zinc-50/50">
          <ObjectViewer data={data} />
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

const CardSection = ({ title, data, onOpen }) => {
  if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) return null;

  return (
    <button
      onClick={() => onOpen(title, data)}
      className="mb-2 w-full flex items-center justify-between rounded-md border border-zinc-200 bg-white px-3 py-3 text-left shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50/50 hover:shadow"
    >
      <span className="font-mono text-[11px] font-bold text-gray-800">{title}</span>
      <ChevronRight size={14} className="text-zinc-400" />
    </button>
  );
};

const ArtifactKnowledgeViewer = ({ jobId, artifactId, onSelectDependency }) => {
  const api = useApi();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [modalState, setModalState] = useState({ isOpen: false, title: '', data: null });

  useEffect(() => {
    let active = true;
    const fetchDetails = async () => {
      if (!jobId || !artifactId) {
        setData(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        // We use encodeURIComponent just in case artifactId has special characters
        const res = await api.get(`/api/repository/${jobId}/artifact-details/${encodeURIComponent(artifactId)}`);
        if (active) {
          setData(res);
        }
      } catch (err) {
        if (active) {
          console.error("Failed to fetch artifact details:", err);
          setError("Failed to load artifact details.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    fetchDetails();
    return () => { active = false; };
  }, [jobId, artifactId, api]);

  if (!artifactId) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center font-mono text-[11px] text-zinc-500">
        Select an artifact from Repository Explorer to inspect its knowledge.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-zinc-500">
        <Loader2 className="animate-spin" size={24} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center font-mono text-[11px] text-red-500">
        {error || "Artifact not found."}
      </div>
    );
  }

  const handleOpenModal = (title, data) => {
    setModalState({ isOpen: true, title, data });
  };

  return (
    <>
      <div className="flex flex-col h-full overflow-y-auto pr-1 relative">
        <div className="flex-none">
          <ArtifactDetails details={data.artifact} />
          <DependencyPanel dependencies={data.dependencies} onSelectDependency={onSelectDependency} />
        </div>
        
        <div className="flex-none flex flex-col mt-4 min-h-[400px]">
          <h4 className="font-mono text-[11px] font-bold text-gray-900 uppercase tracking-widest border-b pb-1 mb-3 shrink-0">
            Structured Knowledge Explorer
          </h4>
          <div className="flex-1 min-h-0 pb-10">
            {data.structure && (
              <>
                <CardSection title="Identity" data={data.structure.identity} onOpen={handleOpenModal} />
                <CardSection title="Structure" data={data.structure.structure} onOpen={handleOpenModal} />
                <CardSection title="Datasets" data={data.structure.datasets} onOpen={handleOpenModal} />
                <CardSection title="Dependencies" data={data.structure.dependencies} onOpen={handleOpenModal} />
                <CardSection title="Semantics" data={data.structure.semantics} onOpen={handleOpenModal} />
                <CardSection title="Metadata" data={data.structure.metadata} onOpen={handleOpenModal} />
                <CardSection title="Relationships" data={data.structure.relationships} onOpen={handleOpenModal} />
                {/* Fallback for legacy generic structure if new format doesn't exist */}
                {!data.structure.identity && (
                  <CardSection title="Artifact Structure" data={data.structure} onOpen={handleOpenModal} />
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {modalState.isOpen && (
        <Modal 
          title={modalState.title} 
          data={modalState.data} 
          onClose={() => setModalState({ isOpen: false, title: '', data: null })} 
        />
      )}
    </>
  );
};

ArtifactKnowledgeViewer.propTypes = {
  jobId: PropTypes.string,
  artifactId: PropTypes.string,
  onSelectDependency: PropTypes.func,
};

export default ArtifactKnowledgeViewer;

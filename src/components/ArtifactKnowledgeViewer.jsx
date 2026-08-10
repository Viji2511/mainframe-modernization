import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { useApi } from '../hooks/useApi';
import ArtifactDetails from './ArtifactDetails';
import { Loader2, ChevronRight, X } from 'lucide-react';
import StructureViewer from './StructureViewer';

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

const RelationshipsViewer = ({ data }) => {
  if (!data || data.length === 0) return <div className="text-zinc-400 italic font-sans text-sm p-2">No relationships found.</div>;
  return (
    <div className="flex flex-col gap-2">
      {data.map((rel, i) => (
        <div key={i} className="p-3 bg-white border border-zinc-200 rounded-md shadow-sm">
          <div className="flex flex-col text-sm">
            <span className="font-semibold text-blue-600">{rel.source_id}</span>
            <div className="pl-4 border-l-2 border-zinc-200 flex flex-col my-1">
              <span className="text-zinc-500 font-mono text-xs">→ {rel.rel_type || rel.relationship_type}</span>
              <span className="text-zinc-500 font-mono text-xs text-emerald-600">→ {rel.target_id}</span>
            </div>
            {rel.properties && rel.properties.evidence_id && (
              <span className="text-xs text-zinc-400 mt-1 block">Evidence: {rel.properties.evidence_id}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};



const SchemaViewer = ({ data }) => {
  if (!data || (!data.ddl && !data.columns && !data.schema_type)) return <div className="text-zinc-400 italic font-sans text-sm p-2">No schema available.</div>;
  
  if (data.ddl) {
    return (
      <div className="flex flex-col gap-2">
        <div className="p-3 bg-zinc-800 text-zinc-100 rounded-md shadow-sm font-mono text-xs whitespace-pre-wrap overflow-x-auto">
          {data.ddl}
        </div>
        {data.readiness_status && (
          <div className="mt-2 text-xs font-semibold text-zinc-600">Status: {data.readiness_status}</div>
        )}
      </div>
    );
  }

  if (data.schema_type === 'PROGRAM_SCHEMA') {
    return (
      <div className="flex flex-col gap-4 p-2 text-sm">
        <div><span className="font-bold text-lg">PROGRAM:</span> {data.program_name}</div>
        
        {data.data_structures && data.data_structures.length > 0 && (
          <div>
            <div className="font-bold mb-1 border-b pb-1">Data Structures</div>
            <ul className="list-disc pl-5 font-mono text-xs text-blue-700">
              {data.data_structures.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        
        {data.datasets && data.datasets.length > 0 && (
          <div>
            <div className="font-bold mb-1 border-b pb-1">Datasets Accessed</div>
            <ul className="list-disc pl-5 font-mono text-xs text-emerald-600">
              {data.datasets.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        
        {data.copybooks && data.copybooks.length > 0 && (
          <div>
            <div className="font-bold mb-1 border-b pb-1">Copybooks</div>
            <ul className="list-disc pl-5 font-mono text-xs text-zinc-600">
              {data.copybooks.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
        
        {data.called_programs && data.called_programs.length > 0 && (
          <div>
            <div className="font-bold mb-1 border-b pb-1">Calls</div>
            <ul className="list-disc pl-5 font-mono text-xs text-amber-600">
              {data.called_programs.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (data.schema_type === 'JOB_SCHEMA') {
    return (
      <div className="flex flex-col gap-4 p-2 text-sm">
        <div><span className="font-bold text-lg">JOB:</span> {data.job_name}</div>
        {data.steps && data.steps.map((step, i) => (
          <div key={i} className="pl-2 border-l-2 border-zinc-200">
            <div className="font-bold text-blue-600 mb-2">STEP: {step.step_name}</div>
            
            {step.exec && step.exec.length > 0 && (
              <div className="pl-4 mb-2">
                <span className="font-semibold text-xs text-zinc-500">PROGRAM:</span>
                <span className="ml-2 font-mono text-xs font-bold">{step.exec[0].program}</span>
              </div>
            )}
            
            {step.dd && step.dd.length > 0 && (
              <div className="pl-4">
                <span className="font-semibold text-xs text-zinc-500 block mb-1">DD Allocations:</span>
                <ul className="list-none space-y-1">
                  {step.dd.map((dd, j) => (
                    <li key={j} className="font-mono text-xs flex gap-2">
                      <span className="text-zinc-600 w-24">{dd.dd_name}:</span>
                      <span className="text-emerald-600">{dd.dataset || dd.sysout || dd.dummy || '...'}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }
  
  if (data.schema_type === 'DATASET_SCHEMA') {
    return (
      <div className="flex flex-col gap-3 p-2 text-sm">
        <div><span className="font-bold text-lg border-b pb-1 block">Dataset: {data.dataset_name}</span></div>
        <div className="flex gap-4 font-mono text-xs bg-zinc-50 p-2 rounded">
          <span className="font-bold">Organization:</span> 
          <span className="text-blue-700">{data.organization}</span>
        </div>
        <div className="flex gap-4 font-mono text-xs bg-zinc-50 p-2 rounded">
          <span className="font-bold">Primary Key Length:</span> 
          <span className="text-blue-700">{data.key_length !== null ? data.key_length : '-'}</span>
        </div>
        <div className="flex gap-4 font-mono text-xs bg-zinc-50 p-2 rounded">
          <span className="font-bold">Primary Key Offset:</span> 
          <span className="text-blue-700">{data.key_offset !== null ? data.key_offset : '-'}</span>
        </div>
        <div className="flex gap-4 font-mono text-xs bg-zinc-50 p-2 rounded">
          <span className="font-bold">Record Length:</span> 
          <span className="text-blue-700">{data.record_length !== null ? data.record_length : '-'}</span>
        </div>
      </div>
    );
  }
  
  if (data.columns || data.schema_type === 'RECORD_SCHEMA') {
    return (
      <div className="flex flex-col gap-2">
        <div className="font-bold text-lg mb-2">Table: {data.table_name}</div>
        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-zinc-100 border-b border-zinc-200">
              <th className="p-2">Column Name</th>
              <th className="p-2">SQL Type</th>
              <th className="p-2">Source Field</th>
              <th className="p-2 text-center">Key</th>
            </tr>
          </thead>
          <tbody>
            {data.columns && data.columns.map((col, i) => (
              <tr key={i} className="border-b border-zinc-100">
                <td className="p-2 font-semibold text-blue-700">{col.name}</td>
                <td className="p-2 text-emerald-600">{col.sql_type}</td>
                <td className="p-2 text-zinc-500">{col.source_field || col.source_pic}</td>
                <td className="p-2 text-center text-zinc-400">{col.primary_key ? 'PK' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <div className="text-zinc-400 italic font-sans text-sm p-2">No schema available.</div>;
};

const MetadataViewer = ({ data }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-zinc-400 italic font-sans text-sm p-2">No metadata found.</div>;
  const validKeys = Object.keys(data).filter(k => {
    const v = data[k];
    if (v === null || v === undefined || v === '') return false;
    if (Array.isArray(v) && v.length === 0) return false;
    if (typeof v === 'object' && Object.keys(v).length === 0) return false;
    return true;
  });

  if (validKeys.length === 0) return <div className="text-zinc-400 italic font-sans text-sm p-2">No metadata found.</div>;

  return (
    <div className="flex flex-col gap-2">
      {validKeys.map(k => (
        <div key={k} className="flex justify-between p-2 border-b border-zinc-100 text-sm">
          <span className="font-semibold text-zinc-600 capitalize">{k.replace(/_/g, ' ')}</span>
          <span className="font-mono text-zinc-800 text-xs break-all max-w-[60%] text-right">
            {typeof data[k] === 'object' ? JSON.stringify(data[k]) : String(data[k])}
          </span>
        </div>
      ))}
    </div>
  );
};

const Modal = ({ title, data, artifactType, onClose }) => {
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
          {title === 'Structure' ? <StructureViewer data={data} artifactType={artifactType} /> :
           title === 'Relationships' ? <RelationshipsViewer data={data} /> :
           title === 'Schema' ? <SchemaViewer data={data} /> :
           title === 'Metadata' ? <MetadataViewer data={data} /> :
           <ObjectViewer data={data} />}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

const CardSection = ({ title, data, onOpen }) => {
  // Always render the button so empty states can be viewed.
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
        </div>
        
        <div className="flex-none flex flex-col mt-4 min-h-[400px]">
          <h4 className="font-mono text-[11px] font-bold text-gray-900 uppercase tracking-widest border-b pb-1 mb-3 shrink-0">
            Structured Knowledge Explorer
          </h4>
          <div className="flex-1 min-h-0 pb-10">
            {data.structure && (
              <>
                <CardSection title="Identity" data={data.structure.identity} onOpen={handleOpenModal} />
                <CardSection title="Structure" data={data.structure.structure || data.structure} onOpen={handleOpenModal} />
                <CardSection title="Relationships" data={data.detailed_relationships} onOpen={handleOpenModal} />
                <CardSection 
                  title={
                    data?.artifact?.type === 'COBOL' || data?.artifact?.type === 'CBL' ? 'Program Schema' :
                    data?.artifact?.type === 'JCL' ? 'Job/Data Flow Schema' :
                    data?.artifact?.type === 'IDCAMS' || data?.artifact?.type === 'DATASET' ? 'Dataset Definition Schema' :
                    data?.artifact?.type === 'COPYBOOK' ? 'Record Schema' :
                    'Schema'
                  } 
                  data={data.detailed_schema} 
                  onOpen={(t, d) => handleOpenModal('Schema', d)} 
                />
                <CardSection title="Metadata" data={{
                   ...data.structure.metadata,
                   parser: data.artifact.parser,
                   language: data.artifact.language,
                   repositoryPath: data.artifact.repositoryPath
                }} onOpen={handleOpenModal} />
              </>
            )}
          </div>
        </div>
      </div>

      {modalState.isOpen && (
        <Modal 
          title={modalState.title} 
          data={modalState.data} 
          artifactType={data?.structure?.identity?.artifact_type}
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

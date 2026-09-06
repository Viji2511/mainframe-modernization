import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { useApi } from '../hooks/useApi';
import ArtifactDetails from './ArtifactDetails';
import { Loader2, ChevronRight, X } from 'lucide-react';
import StructureViewer from './StructureViewer';
import DDLPreview from './DDLPreview';

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



const RecursivePropRenderer = ({ obj }) => {
  if (!obj) return null;
  if (typeof obj !== 'object') {
    return <span className="text-blue-700 font-mono">{String(obj)}</span>;
  }
  if (Array.isArray(obj)) {
    return (
      <ul className="list-disc pl-4 mt-1">
        {obj.map((item, i) => (
          <li key={i}>{typeof item === 'object' ? <RecursivePropRenderer obj={item} /> : <span className="text-blue-700 font-mono">{String(item)}</span>}</li>
        ))}
      </ul>
    );
  }
  
  return (
    <div className="flex flex-col gap-1 mt-1 pl-3 border-l border-zinc-200">
      {Object.entries(obj).map(([k, v], i) => {
        if (v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) return null;
        return (
          <div key={i} className="text-xs font-mono">
            <span className="font-semibold text-zinc-600 mr-2">{k.replace(/_/g, ' ').toUpperCase()}:</span>
            <RecursivePropRenderer obj={v} />
          </div>
        );
      })}
    </div>
  );
};

const ProgramSchemaViewer = ({ data }) => {
  return (
    <div className="flex flex-col gap-4 p-2 text-sm">
      <div className="text-lg font-bold border-b pb-1">PROGRAM: {data.program_name}</div>
      
      {data.data_structures && data.data_structures.length > 0 && (
        <div className="pl-2 border-l-2 border-blue-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">DATA STRUCTURES</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.data_structures} />
          </div>
        </div>
      )}

      {data.copybooks && data.copybooks.length > 0 && (
        <div className="pl-2 border-l-2 border-indigo-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">COPYBOOKS</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.copybooks} />
          </div>
        </div>
      )}

      {data.datasets && data.datasets.length > 0 && (
        <div className="pl-2 border-l-2 border-emerald-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">DATASETS</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.datasets} />
          </div>
        </div>
      )}

      {data.files && Object.keys(data.files).length > 0 && (
        <div className="pl-2 border-l-2 border-cyan-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">FILE REFERENCES</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.files} />
          </div>
        </div>
      )}

      {data.operations && data.operations.length > 0 && (
        <div className="pl-2 border-l-2 border-amber-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">OPERATIONS</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.operations} />
          </div>
        </div>
      )}

      {data.called_programs && data.called_programs.length > 0 && (
        <div className="pl-2 border-l-2 border-rose-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">CALLED PROGRAMS</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.called_programs} />
          </div>
        </div>
      )}
    </div>
  );
};

const JobSchemaViewer = ({ data }) => {
  return (
    <div className="flex flex-col gap-4 p-2 text-sm">
      <div className="text-lg font-bold border-b pb-1">JOB: {data.job_name}</div>
      
      {data.job_card && Object.keys(data.job_card).length > 0 && (
        <div className="pl-2 border-l-2 border-amber-400">
          <div className="font-bold text-xs uppercase text-zinc-500 mb-1">JOB PARAMETERS</div>
          <div className="pl-2">
            <RecursivePropRenderer obj={data.job_card} />
          </div>
        </div>
      )}

      {data.steps && data.steps.length > 0 && (
        <div>
          <div className="font-bold text-sm uppercase text-zinc-700 mb-2">STEPS</div>
          <div className="flex flex-col gap-4 pl-4">
            {data.steps.map((step, i) => (
              <div key={i} className="pl-2 border-l-2 border-zinc-300">
                <div className="font-bold text-blue-700 mb-2">STEP: {step.step_name}</div>
                
                {step.exec && step.exec.length > 0 && (
                  <div className="pl-4 mb-3 border-l-2 border-indigo-200">
                    <div className="font-bold text-xs uppercase text-zinc-500 mb-1">PROGRAM EXECUTIONS</div>
                    <RecursivePropRenderer obj={step.exec} />
                  </div>
                )}
                
                {step.dd && step.dd.length > 0 && (
                  <div className="pl-4 border-l-2 border-emerald-200">
                    <div className="font-bold text-xs uppercase text-zinc-500 mb-1">DD STATEMENTS</div>
                    <div className="flex flex-col gap-2">
                      {step.dd.map((dd, j) => (
                        <div key={j} className="pl-2">
                          <div className="font-bold font-mono text-xs text-zinc-800 mb-1">{dd.dd_name}</div>
                          <div className="pl-4">
                            {Object.entries(dd).map(([k, v]) => {
                              if (k === 'dd_name' || v === null || v === undefined || v === '') return null;
                              return (
                                <div key={k} className="flex gap-2 font-mono text-xs">
                                  <span className="font-semibold text-zinc-500 w-20">{k.toUpperCase()}:</span>
                                  <span className="text-emerald-700">{v}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const DatasetSchemaViewer = ({ data }) => {
  const skipKeys = ['schema_type', 'dataset_name'];
  return (
    <div className="flex flex-col gap-4 p-2 text-sm">
      <div className="text-lg font-bold border-b pb-1">DATASET: {data.dataset_name}</div>
      <div className="pl-2 border-l-2 border-blue-400">
        <div className="font-bold text-xs uppercase text-zinc-500 mb-1">PROPERTIES</div>
        <div className="pl-2 flex flex-col gap-2">
          {Object.entries(data).map(([k, v]) => {
            if (skipKeys.includes(k) || v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) return null;
            return (
              <div key={k} className="flex flex-col font-mono text-xs bg-zinc-50 p-2 rounded">
                <span className="font-bold text-zinc-600 mb-1">{k.replace(/_/g, ' ').toUpperCase()}:</span>
                <div className="pl-2 border-l border-zinc-200">
                  <RecursivePropRenderer obj={v} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
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

  if (data.schema_type === 'PROGRAM_SCHEMA') return <ProgramSchemaViewer data={data} />;
  if (data.schema_type === 'JOB_SCHEMA') return <JobSchemaViewer data={data} />;
  if (data.schema_type === 'DATASET_SCHEMA') return <DatasetSchemaViewer data={data} />;
  
  if (data.columns || data.schema_type === 'RECORD_SCHEMA') {
    return (
      <div className="flex flex-col gap-2">
        <div className="font-bold text-lg mb-2">Table: {data.table_name}</div>
        
        {data.validation_summary && (
          <div className="mb-4 p-3 bg-zinc-50 border border-zinc-200 rounded-md text-xs font-mono grid grid-cols-2 gap-2">
            <div className="font-semibold text-zinc-700 col-span-2 border-b pb-1 mb-1">Validation Summary</div>
            <div className="flex justify-between"><span>Total fields:</span> <span className="font-bold">{data.validation_summary.total_fields}</span></div>
            <div className="flex justify-between"><span>PostgreSQL-compatible:</span> <span className="font-bold text-green-600">{data.validation_summary.postgres_compatible}</span></div>
            <div className="flex justify-between"><span>Requires review:</span> <span className="font-bold text-yellow-600">{data.validation_summary.requires_review}</span></div>
            <div className="flex justify-between"><span>Unsupported/Invalid:</span> <span className="font-bold text-red-600">{data.validation_summary.unsupported}</span></div>
            <div className="flex justify-between"><span>Numeric conversions:</span> <span className="font-bold">{data.validation_summary.numeric_conversions}</span></div>
            <div className="flex justify-between"><span>Character conversions:</span> <span className="font-bold">{data.validation_summary.character_conversions}</span></div>
            <div className="flex justify-between"><span>Date/time conversions:</span> <span className="font-bold">{data.validation_summary.date_conversions}</span></div>
            <div className="flex justify-between"><span>Redefines handled (Excluded):</span> <span className="font-bold text-blue-600">{data.validation_summary.redefines_handled}</span></div>
          </div>
        )}

        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-zinc-100 border-b border-zinc-200">
              <th className="p-2">Column Name</th>
              <th className="p-2">Source Field</th>
              <th className="p-2">COBOL PIC</th>
              <th className="p-2">PostgreSQL Type</th>
              <th className="p-2 text-center">Key</th>
              <th className="p-2 text-center">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.columns && data.columns.map((col, i) => {
              const isReviewRequired = col.schema_status && col.schema_status.includes("REVIEW_REQUIRED");
              const isExcludedPhysical = col.is_excluded && !isReviewRequired;
              
              return (
                <tr key={i} className={`border-b border-zinc-100 ${isExcludedPhysical ? 'opacity-50 line-through' : ''}`}>
                  <td className="p-2 font-semibold text-blue-700" title={col.conversion_reason || ""}>
                    {isReviewRequired && <span className="text-amber-500 mr-1" title="REVIEW_REQUIRED">⚠</span>}
                    {col.name}
                  </td>
                  <td className="p-2 text-zinc-500">{col.source_field || "-"}</td>
                  <td className="p-2 text-zinc-500">{col.source_pic || col.pic || col.original_pic || "-"}</td>
                  <td className="p-2 text-emerald-600 font-bold">{col.postgres_type || col.sql_type || col.type || "-"}</td>
                  <td className="p-2 text-center text-zinc-400 font-bold">{col.primary_key || col.is_primary ? 'PK' : ''}</td>
                  <td className={`p-2 text-center font-bold ${isExcludedPhysical ? 'text-zinc-500' : col.confidence === 'HIGH' ? 'text-green-600' : col.confidence === 'MEDIUM' ? 'text-yellow-600' : col.confidence === 'LOW' ? 'text-red-600' : 'text-zinc-400'}`}>
                    {col.confidence || "-"}
                  </td>
                </tr>
              );
            })}
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

const GeneratedSqlAction = ({ jobId, artifactId, artifact, schema }) => {
  const artifactType = String(artifact?.type || '').toUpperCase();
  const hasCanonicalDdl = Boolean(schema?.ddl);
  // Copybooks are the normal generated-schema source. Other artifacts only
  // receive this action when their existing backend detail response actually
  // contains canonical SQL.
  if (artifactType !== 'COPYBOOK' && !hasCanonicalDdl) return null;

  return (
    <section className="mb-2 rounded-md border border-zinc-200 bg-white p-3 shadow-sm">
      <div className="mb-2 font-mono text-[11px] font-bold text-gray-800">Generated PostgreSQL SQL</div>
      {hasCanonicalDdl ? (
        <DDLPreview
          compact
          jobId={jobId}
          artifactId={artifactId}
          dsn={artifact?.name || artifactId || 'artifact'}
          fields={[]}
          dialect="PostgreSQL"
        />
      ) : (
        <button disabled className="cursor-not-allowed rounded border border-zinc-200 bg-zinc-100 px-3 py-2 font-mono text-[11px] font-bold text-zinc-400">Generated SQL not available</button>
      )}
    </section>
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

  const handleOpenModal = async (title, modalData) => {
    // Structure is the one view that must always reflect the persisted,
    // backend-derived hierarchy.  A repository can finish re-analysis while
    // its detail card is already mounted, so refresh it at the user action
    // boundary instead of opening a stale, previously unavailable response.
    if (title === 'Structure' && jobId && artifactId) {
      try {
        const refreshed = await api.get(`/api/repository/${jobId}/artifact-details/${encodeURIComponent(artifactId)}`);
        setData(refreshed);
        setModalState({
          isOpen: true,
          title,
          data: {
            raw_structure: refreshed.structure,
            structure_view: refreshed.structure_view,
          },
        });
        return;
      } catch (refreshError) {
        // Keep the already loaded response usable if a transient refresh
        // fails; the normal visible error state still covers later retries.
        console.error('Failed to refresh structure before opening modal:', refreshError);
      }
    }
    setModalState({ isOpen: true, title, data: modalData });
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
                <CardSection title="Structure" data={{
                  raw_structure: data.structure,
                  structure_view: data.structure_view,
                }} onOpen={handleOpenModal} />
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
                <GeneratedSqlAction jobId={jobId} artifactId={artifactId} artifact={data.artifact} schema={data.detailed_schema} />
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
          artifactType={data?.structure?.identity?.artifact_type || data?.structure?.artifact_type || data?.artifact?.type}
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

GeneratedSqlAction.propTypes = {
  jobId: PropTypes.string,
  artifactId: PropTypes.string,
  artifact: PropTypes.object,
  schema: PropTypes.object,
};

export default ArtifactKnowledgeViewer;

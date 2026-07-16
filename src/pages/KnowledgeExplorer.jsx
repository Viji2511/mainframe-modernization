import React, { useState, useEffect } from 'react';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import { 
  Folder, FileCode, Database, MessageSquare, List,
  ChevronRight, ChevronDown, CheckCircle, Activity, Award
} from 'lucide-react';

const KnowledgeExplorer = () => {
  const { currentJobId } = useAppStore();
  const api = useApi();
  const [summary, setSummary] = useState(null);
  const [structure, setStructure] = useState(null);
  const [schema, setSchema] = useState(null);
  const [datasets, setDatasets] = useState(null);
  const [relationships, setRelationships] = useState(null);
  const [chatQuery, setChatQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);

  useEffect(() => {
    const fetchRepoData = async () => {
      if (!currentJobId) return;
      try {
        const sumData = await api.get(`/api/repository/${currentJobId}/summary`);
        setSummary(sumData);
        
        const structData = await api.get(`/api/repository/${currentJobId}/structure`);
        setStructure(structData);
        
        const schemaData = await api.get(`/api/repository/${currentJobId}/schema`);
        setSchema(schemaData);
        
        const dsData = await api.get(`/api/repository/${currentJobId}/datasets`);
        setDatasets(dsData);
        
        const relData = await api.get(`/api/repository/${currentJobId}/relationships`);
        setRelationships(relData);
      } catch (err) {
        console.error('Error fetching repo data:', err);
      }
    };
    fetchRepoData();
  }, [currentJobId, api]);

  const handleChat = async () => {
    if (!chatQuery.trim()) return;
    
    const submittedQuery = chatQuery;
    const newHistory = [...chatHistory, { role: 'user', content: chatQuery }];
    setChatHistory(newHistory);
    setChatQuery('');
    
    try {
      const response = await api.post(`/api/repository/${currentJobId}/chat`, { query: submittedQuery });
      setChatHistory([...newHistory, { role: 'assistant', content: response.response }]);
    } catch (err) {
      const stat = summary?.statistics || {};
      setChatHistory([
        ...newHistory,
        {
          role: 'assistant',
          content: `Local knowledge response:\n\nHealth score: ${stat.repository_health_score ?? 0}/100.\nMigration readiness: ${stat.migration_readiness || 'Not evaluated'}.\nKnown inventory: ${stat.total_files || 0} files, ${stat.copybooks || 0} copybooks, ${stat.cobol_programs || 0} COBOL programs, ${stat.datasets || 0} datasets.\n\nThe assistant endpoint was unavailable, but the repository knowledge is still loaded in this view.`,
        },
      ]);
    }
  };

  if (!summary) {
    return <div className="p-6 text-center text-zinc-500">Loading Repository Knowledge...</div>;
  }

  const stat = summary.statistics || {};

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* 1. Repository Summary */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
        <h2 className="text-lg font-bold font-mono text-gray-900 border-b pb-2 mb-4">REPOSITORY SUMMARY</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-sm font-mono">
          <div><div className="text-zinc-500 text-[10px] uppercase">Name</div><div className="font-bold">{summary.repository_name}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Health Score</div><div className="font-bold text-green-600">{stat.repository_health_score ?? 0}/100</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Migration Readiness</div><div className="font-bold text-blue-600">{stat.migration_readiness || 'Not evaluated'}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Total Files</div><div className="font-bold">{stat.total_files || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">COBOL Programs</div><div className="font-bold">{stat.cobol_programs || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Copybooks</div><div className="font-bold">{stat.copybooks || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">JCL Jobs</div><div className="font-bold">{stat.jcl_jobs || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">IDCAMS Scripts</div><div className="font-bold">{stat.idcams_scripts || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Datasets</div><div className="font-bold">{stat.datasets || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Relationships</div><div className="font-bold">{stat.relationships || 0}</div></div>
          <div><div className="text-zinc-500 text-[10px] uppercase">Business Rules</div><div className="font-bold">{stat.business_rules || 0}</div></div>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden h-[600px]">
        {/* 2. Repository Explorer */}
        <div className="w-1/4 bg-white border border-gray-200 rounded-lg shadow-sm p-4 overflow-y-auto">
          <h3 className="font-mono text-xs font-bold text-gray-900 uppercase tracking-widest border-b pb-2 mb-3 flex items-center gap-2">
            <Folder size={14} /> Repository Explorer
          </h3>
          {structure && (
            <div className="space-y-2 text-sm font-mono">
              <div className="font-bold text-gray-700 flex items-center gap-1"><ChevronDown size={14} /> COBOL Programs</div>
              <div className="pl-5 space-y-1">
                {Object.keys(structure.programs || {}).map(p => (
                  <div key={p} className="cursor-pointer text-blue-600 hover:underline flex items-center gap-1" onClick={() => setSelectedFile(structure.programs[p])}>
                    <FileCode size={12}/> {p}.cbl
                  </div>
                ))}
              </div>
              <div className="font-bold text-gray-700 flex items-center gap-1"><ChevronDown size={14} /> Copybooks</div>
              <div className="pl-5 space-y-1">
                {Object.keys(structure.copybooks || {}).map(c => (
                  <div key={c} className="cursor-pointer text-blue-600 hover:underline flex items-center gap-1" onClick={() => setSelectedFile(structure.copybooks[c])}>
                    <List size={12}/> {c}.cpy
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 3. Knowledge Explorer Details */}
        <div className="w-1/3 bg-white border border-gray-200 rounded-lg shadow-sm p-4 overflow-y-auto">
          <h3 className="font-mono text-xs font-bold text-gray-900 uppercase tracking-widest border-b pb-2 mb-3 flex items-center gap-2">
            <Activity size={14} /> Knowledge Object
          </h3>
          {selectedFile ? (
            <div className="space-y-4 font-mono text-xs">
              <div>
                <div className="text-zinc-500 text-[10px] uppercase">ID</div>
                <div className="font-bold text-gray-900">{selectedFile.id}</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px] uppercase">Source File</div>
                <div className="font-bold text-gray-900">{selectedFile.filepath || selectedFile.traceability?.source_file || 'Unknown'}</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px] uppercase">Object Type</div>
                <div className="text-gray-900">{selectedFile.language ? 'Program' : selectedFile.fields ? 'Copybook' : 'Knowledge object'}</div>
              </div>
              {selectedFile.fields && (
                <div>
                  <div className="text-zinc-500 text-[10px] uppercase">Parsed Fields</div>
                  <div className="text-gray-900">{selectedFile.fields.length}</div>
                </div>
              )}
              {selectedFile.fields && schema?.database_schema?.tables && (
                <div>
                  <div className="text-zinc-500 text-[10px] uppercase mt-2 border-t pt-2">SQL Schema Mapping</div>
                  <div className="max-h-40 overflow-y-auto mt-1 bg-gray-50 rounded border border-gray-100 p-2">
                    {(() => {
                        const tableName = selectedFile.id.replace('.CPY', '').replace('.COPY', '').replace('-', '_').toUpperCase();
                        const table = schema.database_schema.tables.find(t => t.name === tableName);
                        if (!table) return <div className="text-gray-500 text-[10px] italic">No schema mapped.</div>;
                        return (
                           <table className="w-full text-[10px]">
                              <thead>
                                <tr className="border-b text-left text-zinc-500"><th className="pb-1">Column</th><th className="pb-1">SQL Type</th></tr>
                              </thead>
                              <tbody>
                                {table.columns.map((col, i) => (
                                   <tr key={i} className="border-b border-gray-100 last:border-0">
                                      <td className="py-1 font-semibold text-gray-800">{col.name}{col.is_primary ? ' 🔑' : ''}</td>
                                      <td className="py-1 text-blue-600 font-mono">{col.type}</td>
                                   </tr>
                                ))}
                              </tbody>
                           </table>
                        );
                    })()}
                  </div>
                </div>
              )}
              <div>
                <div className="text-zinc-500 text-[10px] uppercase">Datasets Accessed</div>
                <div className="text-gray-900">{selectedFile.datasets_accessed?.join(', ') || 'None'}</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px] uppercase">Copybooks Used</div>
                <div className="text-gray-900">{selectedFile.copybooks_used?.join(', ') || 'None'}</div>
              </div>
            </div>
          ) : (
            <div className="text-zinc-500 text-xs italic">Select a file from the Repository Explorer to view its extracted knowledge and relationships.</div>
          )}
        </div>

        {/* 4. Modernization Assistant */}
        <div className="flex-1 bg-white border border-gray-200 rounded-lg shadow-sm flex flex-col overflow-hidden">
          <div className="p-3 border-b border-gray-200 bg-zinc-50 flex items-center gap-2">
            <MessageSquare size={16} className="text-blue-600" />
            <span className="font-mono text-xs font-bold uppercase tracking-widest">Modernization Assistant</span>
          </div>
          <div className="flex-1 p-4 overflow-y-auto space-y-4 bg-zinc-50/50">
            {chatHistory.length === 0 && (
              <div className="text-xs text-zinc-500 text-center mt-10 font-mono">
                Ask a question about the repository (e.g., "Explain CUSTOMER.cbl" or "Generate ER Diagram").
              </div>
            )}
            {chatHistory.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-lg p-3 text-xs font-mono whitespace-pre-wrap ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white border border-gray-200 text-gray-800 shadow-sm'}`}>
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
          <div className="p-3 border-t border-gray-200 bg-white flex gap-2">
            <input 
              type="text"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleChat()}
              placeholder="Ask the assistant..."
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-blue-500 shadow-sm"
            />
            <button onClick={handleChat} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-xs font-bold font-mono uppercase tracking-wider hover:bg-blue-700 shadow-sm transition-colors">
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default KnowledgeExplorer;

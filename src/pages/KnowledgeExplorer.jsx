import React, { useState, useEffect } from 'react';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import ArtifactKnowledgeViewer from '../components/ArtifactKnowledgeViewer';
import AuditTrail from '../components/AuditTrail';
import { 
  Folder, FileCode, FileText, Database, MessageSquare, List,
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

  const buildTree = (structureData) => {
    if (!structureData) return {};
    const tree = {};
    const addPath = (path, item, typeIcon) => {
      // Normalize slashes
      const normalized = path.replace(/\\/g, '/');
      const parts = normalized.split('/');
      let current = tree;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) current[parts[i]] = { _isDir: true, children: {} };
        current = current[parts[i]].children;
      }
      current[parts[parts.length - 1]] = { _isDir: false, item, typeIcon };
    };

    if (structureData.programs) {
      Object.entries(structureData.programs).forEach(([id, p]) => addPath(p.filepath || `${id}.cbl`, id, <FileCode size={12}/>));
    }
    if (structureData.copybooks) {
      Object.entries(structureData.copybooks).forEach(([id, c]) => addPath(c.filepath || `${id}.cpy`, id, <List size={12}/>));
    }
    if (structureData.jcl_jobs) {
      Object.entries(structureData.jcl_jobs).forEach(([id, j]) => addPath(j.filepath || `${id}.jcl`, id, <FileCode size={12}/>));
    }
    if (structureData.idcams_definitions) {
      Object.entries(structureData.idcams_definitions).forEach(([id, i]) => addPath(i.filepath || id, id, <FileCode size={12}/>));
    }
    if (structureData.catalogs) {
      Object.entries(structureData.catalogs).forEach(([id, c]) => addPath(c.filepath || `${id}.lst`, id, <List size={12}/>));
    }
    if (structureData.other_artifacts) {
      Object.entries(structureData.other_artifacts).forEach(([id, artifact]) => addPath(artifact.filepath || id, id, <FileText size={12}/>));
    }
    if (structureData.datasets) {
      // Datasets might not have physical files but logical, if they do, we group them at root if no path
      Object.entries(structureData.datasets).forEach(([id, d]) => addPath(d.filepath || id, id, <Database size={12}/>));
    }
    return tree;
  };

  const renderTree = (node, path = "") => {
    return Object.keys(node).sort().map(key => {
      const child = node[key];
      const fullPath = path ? `${path}/${key}` : key;
      if (child._isDir) {
        return (
          <div key={fullPath} className="space-y-1">
            <div className="font-bold text-gray-700 flex items-center gap-1 cursor-default">
              <ChevronDown size={14} /> <Folder size={14} className="text-gray-500"/> {key}
            </div>
            <div className="pl-5 border-l border-gray-200 ml-2 space-y-1">
              {renderTree(child.children, fullPath)}
            </div>
          </div>
        );
      } else {
        const isSelected = selectedFile === child.item;
        return (
          <div 
            key={fullPath} 
            className={`cursor-pointer hover:bg-zinc-100 flex items-center gap-1.5 py-0.5 rounded px-1 -ml-1 ${isSelected ? 'bg-zinc-100 font-bold text-blue-800' : 'text-blue-700'}`} 
            onClick={() => setSelectedFile(child.item)}
          >
            {child.typeIcon} <span className="truncate text-[11px]">{key}</span>
          </div>
        );
      }
    });
  };

  const repoTree = buildTree(structure);
  const stat = summary.statistics || {};

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* 1. Repository Summary */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-3">
        <h2 className="text-sm font-bold font-mono text-gray-900 border-b pb-1.5 mb-2">REPOSITORY SUMMARY</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-x-4 gap-y-2 text-xs font-mono leading-tight">
          <div className="min-w-0"><div className="text-zinc-500 text-[9px] uppercase">Name</div><div className="font-bold truncate" title={summary.repository_name}>{summary.repository_name}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Health Score</div><div className="font-bold text-green-600">{stat.repository_health_score ?? 0}/100</div></div>
          <div className="lg:col-span-2 min-w-0"><div className="text-zinc-500 text-[9px] uppercase">Migration Readiness</div><div className="font-bold text-blue-600 truncate" title={stat.migration_readiness || 'Not evaluated'}>{stat.migration_readiness || 'Not evaluated'}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Total Folders</div><div className="font-bold">{stat.total_folders || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Total Files</div><div className="font-bold">{stat.total_files || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">COBOL Programs</div><div className="font-bold">{stat.cobol_programs || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Copybooks</div><div className="font-bold">{stat.copybooks || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">JCL Jobs</div><div className="font-bold">{stat.jcl_jobs || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">IDCAMS Scripts</div><div className="font-bold">{stat.idcams_scripts || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Datasets</div><div className="font-bold">{stat.datasets || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Relationships</div><div className="font-bold">{stat.relationships || 0}</div></div>
          <div><div className="text-zinc-500 text-[9px] uppercase">Business Rules</div><div className="font-bold">{stat.business_rules || 0}</div></div>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden h-[600px]">
        {/* 2. Repository Explorer */}
        <div className="w-1/4 bg-white border border-gray-200 rounded-lg shadow-sm p-4 overflow-y-auto">
          <h3 className="font-mono text-xs font-bold text-gray-900 uppercase tracking-widest border-b pb-2 mb-3 flex items-center gap-2">
            <Folder size={14} /> Repository Explorer
          </h3>
          {structure && (
            <div className="space-y-1 text-sm font-mono pl-1">
              {renderTree(repoTree)}
            </div>
          )}
        </div>

        {/* 3. Repository Knowledge Viewer */}
        <div className="w-1/3 bg-white border border-gray-200 rounded-lg shadow-sm p-4 overflow-y-auto">
          <h3 className="font-mono text-xs font-bold text-gray-900 uppercase tracking-widest border-b pb-2 mb-3 flex items-center gap-2">
            <Activity size={14} /> Artifact Knowledge
          </h3>
          <ArtifactKnowledgeViewer 
            jobId={currentJobId} 
            artifactId={selectedFile} 
            onSelectDependency={(depId) => setSelectedFile(depId)} 
          />
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
      <AuditTrail jobId={currentJobId} artifactId={selectedFile} onClearArtifact={() => setSelectedFile(null)} />
    </div>
  );
};

export default KnowledgeExplorer;

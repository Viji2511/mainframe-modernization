import React, { useState, useEffect } from 'react';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import FieldTree from '../components/FieldTree';
import DDLPreview from '../components/DDLPreview';
import BusinessRulesTable from '../components/BusinessRulesTable';
import ProgramCard from '../components/ProgramCard';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';
import { 
  Database, 
  Layout, 
  Cpu, 
  FileCode, 
  Award,
  Layers,
  ChevronDown
} from 'lucide-react';
import demoResult from '../../demo/pipeline_result.json';

const ResultsPage = () => {
  const { currentJobId, setCurrentJobId, currentResult, setCurrentResult, settings, addJob } = useAppStore();
  const api = useApi();

  const [activeTab, setActiveTab] = useState('overview');
  const [allResults, setAllResults] = useState([]);
  const [selectedDsn, setSelectedDsn] = useState('');

  const handleLoadDemo = () => {
    const fakeJobId = 'demo-job-id';
    const fakeJob = {
      job_id: fakeJobId,
      status: 'done',
      db: 'postgresql',
      dsn: demoResult.vsam_dataset.dsn,
      files_count: 5,
      created_at: new Date().toISOString(),
    };
    addJob(fakeJob);
    setCurrentJobId(fakeJobId);
    setCurrentResult(demoResult);
    setAllResults([demoResult]);
  };

  useEffect(() => {
    const fetchResults = async () => {
      if (!currentJobId) return;
      try {
        const data = await api.get(`/api/result/${currentJobId}`);
        if (data && !data.status) {
          const resultsList = Array.isArray(data) ? data : [data];
          setAllResults(resultsList);
          
          if (currentResult) {
            setSelectedDsn(currentResult.vsam_dataset.dsn);
          } else if (resultsList.length > 0) {
            setSelectedDsn(resultsList[0].vsam_dataset.dsn);
            setCurrentResult(resultsList[0]);
          }
        }
      } catch (err) {
        console.error('Error fetching job results:', err);
      }
    };
    fetchResults();
  }, [currentJobId]);

  const handleDsnChange = (e) => {
    const dsn = e.target.value;
    setSelectedDsn(dsn);
    const matched = allResults.find((r) => r.vsam_dataset.dsn === dsn);
    if (matched) {
      setCurrentResult(matched);
    }
  };

  if (!currentResult) {
    return (
      <div className="flex flex-col h-[70vh] items-center justify-center border border-gray-200 rounded bg-white text-zinc-500 p-6 text-center shadow-sm rounded-lg">
        <Database size={40} className="mb-3 text-gray-900" />
        <h3 className="font-mono text-sm font-bold text-gray-900 uppercase">No Result Loaded</h3>
        <p className="text-xs max-w-xs mt-1 font-sans font-medium mb-4">Select a completed job on the Pipeline Jobs page or run a modernization task.</p>
        <button
          onClick={handleLoadDemo}
          className="bg-blue-600 text-white text-gray-900 border border-gray-200 px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider hover:bg-blue-700 shadow-sm rounded-lg active:translate-y-0.5 active:shadow-sm rounded-lg transition-all"
        >
          Load Sample Demo Data
        </button>
      </div>
    );
  }

  const totalDatasets = allResults.length;
  const totalFields = currentResult.copybook?.fields.length || 0;
  const totalPrograms = currentResult.source_analyses.length;
  const confidence = currentResult.vsam_dataset.confidence;

  const allRules = currentResult.source_analyses.flatMap((a) => a.business_rules);

  const getOpsData = () => {
    const counts = { READ: 0, WRITE: 0, REWRITE: 0, DELETE: 0 };
    currentResult.source_analyses.forEach((a) => {
      a.operations.forEach((op) => {
        const opU = op.toUpperCase();
        if (opU.includes('READ')) counts.READ++;
        if (opU.includes('WRITE')) counts.WRITE++;
        if (opU.includes('REWRITE')) counts.REWRITE++;
        if (opU.includes('DELETE')) counts.DELETE++;
      });
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  };

  const tabs = [
    { id: 'overview', name: 'Overview', icon: Layers },
    { id: 'schema', name: 'Database Schema', icon: Layout },
    { id: 'rules', name: 'Business Logic Rules', icon: Cpu },
    { id: 'programs', name: 'Programs Map', icon: FileCode },
    { id: 'json', name: 'Raw JSON', icon: Database },
  ];

  return (
    <div className="space-y-6">
      {/* Header with Dataset Select */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-gray-200 pb-4 gap-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-gray-900">MODERNIZATION ANALYSIS REPORT</h1>
          <p className="text-xs text-zinc-600 mt-1 font-sans">Job ID: <span className="font-mono text-blue-600 font-bold">{currentJobId}</span></p>
        </div>

        {/* Dataset dropdown selector */}
        {allResults.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-gray-900 uppercase">Target Dataset:</span>
            <div className="relative">
              <select
                value={selectedDsn}
                onChange={handleDsnChange}
                className="appearance-none font-mono text-xs rounded border border-gray-200 bg-white pl-3 pr-8 py-2 text-gray-900 font-bold focus:outline-none focus:border-[#00ff4c] cursor-pointer shadow-sm rounded-lg"
              >
                {allResults.map((res) => (
                  <option key={res.vsam_dataset.dsn} value={res.vsam_dataset.dsn}>
                    {res.vsam_dataset.dsn}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-2.5 text-gray-900 pointer-events-none" />
            </div>
          </div>
        )}
      </div>

      {/* Tabs navigation */}
      <div className="flex border-b border-gray-200 overflow-x-auto bg-white rounded">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 border-r border-zinc-200 px-4 py-3.5 text-xs font-mono font-bold uppercase transition-colors text-nowrap ${
                isActive
                  ? 'bg-blue-600 text-white/20 text-gray-900 border-b-4 border-black'
                  : 'text-zinc-500 hover:text-gray-900 hover:bg-zinc-50'
              }`}
            >
              <Icon size={12} />
              {tab.name}
            </button>
          );
        })}
      </div>

      {/* Tab Panel contents */}
      <div className="mt-4">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Overview cards summary */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="rounded bg-white border border-gray-200 p-4 flex items-center justify-between shadow-sm rounded-lg">
                <div>
                  <span className="text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">VSAM Datasets</span>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">{totalDatasets}</div>
                </div>
                <Database size={20} className="text-gray-900" />
              </div>

              <div className="rounded bg-white border border-gray-200 p-4 flex items-center justify-between shadow-sm rounded-lg">
                <div>
                  <span className="text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">Parsed Fields</span>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">{totalFields}</div>
                </div>
                <Layout size={20} className="text-gray-900" />
              </div>

              <div className="rounded bg-white border border-gray-200 p-4 flex items-center justify-between shadow-sm rounded-lg">
                <div>
                  <span className="text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">Analyzed Programs</span>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">{totalPrograms}</div>
                </div>
                <FileCode size={20} className="text-gray-900" />
              </div>

              <div className="rounded bg-white border border-gray-200 p-4 flex items-center justify-between shadow-sm rounded-lg">
                <div>
                  <span className="text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">Avg Confidence</span>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">{(confidence * 100).toFixed(0)}%</div>
                </div>
                <Award size={20} className="text-gray-900" />
              </div>
            </div>

            {/* Graphs and metadata descriptions */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Dataset Meta details */}
              <div className="lg:col-span-7 rounded bg-white border border-gray-200 p-5 space-y-4 shadow-sm rounded-lg">
                <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest border-b border-black pb-2">Dataset Metadata</h3>
                <div className="grid grid-cols-2 gap-4 text-xs font-mono text-gray-900">
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">DSN:</div>
                    <div className="text-blue-600 break-all font-bold mt-0.5">{currentResult.vsam_dataset.dsn}</div>
                  </div>
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">VSAM Type:</div>
                    <div className="font-bold mt-0.5">{currentResult.vsam_dataset.vsam_type}</div>
                  </div>
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">Record Length:</div>
                    <div className="font-bold mt-0.5">{currentResult.vsam_dataset.record_length || '—'} bytes</div>
                  </div>
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">Key Length / Offset:</div>
                    <div className="font-bold mt-0.5">
                      {currentResult.vsam_dataset.key_length !== null ? `${currentResult.vsam_dataset.key_length}B / off ${currentResult.vsam_dataset.key_offset || 0}` : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">Source JCL Config:</div>
                    <div className="text-zinc-600 break-all mt-0.5">{currentResult.vsam_dataset.source_jcl || '—'}</div>
                  </div>
                  <div>
                    <div className="text-zinc-500 text-[10px] uppercase">Migration Readiness:</div>
                    <div className={`font-bold mt-0.5 ${currentResult.ready_for_schema_design ? 'text-green-600' : 'text-red-600'}`}>
                      {currentResult.ready_for_schema_design ? 'READY FOR SQL DDL DESIGN' : 'INCOMPLETE METADATA'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Chart operations layout */}
              <div className="lg:col-span-5 rounded bg-white border border-gray-200 p-5 shadow-sm rounded-lg">
                <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest border-b border-black pb-2 mb-4">Operations Profile</h3>
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={getOpsData()}>
                      <XAxis dataKey="name" stroke="#000000" tick={{ fontSize: 9, fontFamily: 'monospace', fontWeight: 'bold' }} />
                      <YAxis stroke="#000000" tick={{ fontSize: 9, fontFamily: 'monospace', fontWeight: 'bold' }} allowDecimals={false} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#ffffff', borderColor: '#000000', borderWidth: 2, fontSize: 10, fontFamily: 'monospace', color: '#000000' }}
                      />
                      <Bar dataKey="value" fill="#00ff4c" stroke="#000000" strokeWidth={1.5} radius={[0, 0, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Schema fields & DDL layout */}
        {activeTab === 'schema' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 space-y-3">
              <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest">Copybook Field Tree ({currentResult.copybook?.language})</h3>
              <FieldTree fields={currentResult.copybook?.fields || []} />
            </div>
            <div className="lg:col-span-5 space-y-3">
              <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest">Target DDL Preview</h3>
              <DDLPreview 
                jobId={currentJobId}
                artifactId={currentResult.copybook?.filename}
                dsn={currentResult.vsam_dataset.dsn} 
                fields={currentResult.copybook?.fields || []} 
                dialect={settings.db || 'postgresql'} 
              />
            </div>
          </div>
        )}

        {/* Tab 3: Business rules logic */}
        {activeTab === 'rules' && (
          <div className="space-y-3">
            <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest">Variables Logic and Validation Rules</h3>
            <BusinessRulesTable rules={allRules} />
          </div>
        )}

        {/* Tab 4: Program map list */}
        {activeTab === 'programs' && (
          <div className="space-y-4">
            <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest">Referencing Mainframe Batch Programs</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {currentResult.source_analyses.map((analysis, idx) => (
                <ProgramCard key={idx} analysis={analysis} />
              ))}
            </div>
          </div>
        )}

        {/* Tab 5: Raw JSON */}
        {activeTab === 'json' && (
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <h3 className="font-mono text-[10px] font-bold text-gray-900 uppercase tracking-widest">Pipeline Result JSON</h3>
              <button
                onClick={() => {
                  const blob = new Blob([JSON.stringify(currentResult, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement('a');
                  link.href = url;
                  link.download = `${currentResult.vsam_dataset.dsn.replace(/\./g, '_')}_result.json`;
                  link.click();
                }}
                className="rounded border border-gray-200 bg-white px-3 py-1 font-mono text-[10px] font-bold text-gray-900 uppercase hover:bg-zinc-100 shadow-sm rounded-lg"
              >
                Download JSON
              </button>
            </div>
            <pre className="border border-gray-200 rounded bg-white p-4 overflow-auto max-h-[500px] font-mono text-xs text-gray-900 shadow-sm rounded-lg select-text">
              {JSON.stringify(currentResult, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsPage;

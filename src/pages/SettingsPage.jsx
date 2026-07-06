import React, { useState } from 'react';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import { Settings, Save, Trash2, Cpu } from 'lucide-react';

const SettingsPage = () => {
  const { settings, updateSettings, setJobs, backendOnline } = useAppStore();
  const api = useApi();

  const [baseUrlInput, setBaseUrlInput] = useState(settings.apiBaseUrl);
  const [dbTypeInput, setDbTypeInput] = useState(settings.db || 'postgresql');
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSave = () => {
    updateSettings({ 
      apiBaseUrl: baseUrlInput.trim(),
      db: dbTypeInput 
    });
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2000);
  };

  const handleClearAll = async () => {
    if (!confirm('Are you sure you want to clear all jobs from the pipeline logs and storage? This cannot be undone.')) return;
    
    try {
      if (backendOnline) {
        const jobsList = await api.get('/api/jobs');
        for (const job of jobsList) {
          await api.delete(`/api/jobs/${job.job_id}`);
        }
      }
      setJobs([]);
      alert('All job logs cleared successfully.');
    } catch (err) {
      alert(`Error clearing job states: ${err.message}`);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="border-b border-gray-200 pb-4">
        <h1 className="text-2xl font-bold font-mono text-gray-900">SYSTEM SETTINGS</h1>
        <p className="text-xs text-zinc-600 mt-1 font-sans">Configure pipeline connections, database default engines, and storage logs.</p>
      </div>

      {/* Connection options card */}
      <div className="rounded bg-white border border-gray-200 shadow-sm rounded-lg p-5 space-y-4 font-mono text-xs text-gray-900">
        <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-gray-900">
          <Settings size={14} className="text-gray-900" /> MIGRATION & ENDPOINT PARAMETERS
        </div>

        {/* API Base URL */}
        <div className="flex flex-col gap-2">
          <span className="text-zinc-600 font-bold uppercase text-[9px] tracking-wider">FastAPI Base URL:</span>
          <input
            type="text"
            value={baseUrlInput}
            onChange={(e) => setBaseUrlInput(e.target.value)}
            placeholder="http://localhost:8000"
            className="rounded border border-gray-200 bg-white px-3 py-2 text-gray-900 font-bold focus:border-[#00ff4c] focus:outline-none"
          />
        </div>

        {/* Default Database Dialect */}
        <div className="flex flex-col gap-2">
          <span className="text-zinc-600 font-bold uppercase text-[9px] tracking-wider">Default SQL Mapping Target:</span>
          <select
            value={dbTypeInput}
            onChange={(e) => setDbTypeInput(e.target.value)}
            className="rounded border border-gray-200 bg-white px-3 py-2 text-gray-900 font-bold focus:border-[#00ff4c] focus:outline-none cursor-pointer"
          >
            <option value="postgresql">PostgreSQL Dialect</option>
            <option value="mysql">MySQL Dialect</option>
          </select>
        </div>

        {/* Save button */}
        <div className="flex items-center justify-between pt-2">
          <span className="text-[10px] text-zinc-500 font-sans font-medium">Local settings persist in browser cache storage.</span>
          <button
            onClick={handleSave}
            className="flex items-center gap-1.5 border border-gray-200 bg-blue-600 text-white px-4 py-2 font-bold uppercase tracking-wider text-gray-900 hover:bg-blue-700 shadow-sm rounded-lg"
          >
            <Save size={12} /> {saveSuccess ? 'SAVED CONFIG!' : 'SAVE CHANGES'}
          </button>
        </div>
      </div>

      {/* Clear logs card */}
      <div className="rounded bg-red-50 border border-gray-200 shadow-sm rounded-lg p-5 space-y-4 font-mono text-xs text-gray-900">
        <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-red-700">
          <Trash2 size={14} /> DANGER ZONE
        </div>
        <p className="text-zinc-700 font-sans font-medium leading-relaxed">
          Clearing jobs deletes all uploads, catalog results, and metadata extraction cache logs from the disk storage directory permanently.
        </p>
        <button
          onClick={handleClearAll}
          className="flex items-center gap-1.5 border border-gray-200 bg-red-100 border-red-400 text-red-700 px-4 py-2 font-bold uppercase tracking-wider hover:bg-red-200 shadow-sm rounded-lg"
        >
          <Trash2 size={12} /> Clear System History
        </button>
      </div>

      {/* About Box */}
      <div className="rounded bg-white border border-gray-200 shadow-sm rounded-lg p-5 space-y-4 font-sans text-gray-900">
        <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-gray-900 font-mono">
          <Cpu size={14} className="text-gray-900" /> ABOUT MAINFRAMEAI
        </div>
        <div className="text-xs text-zinc-600 space-y-2 leading-relaxed font-medium">
          <p>
            <strong className="text-gray-900 font-mono">MainframeAI Modernizer (v1.0.0)</strong> — A general-purpose AI-driven migration assistant mapping legacy systems data stores into standard SQL formats.
          </p>
          <div className="flex gap-4 font-mono text-[9px] text-zinc-400 pt-2 font-bold uppercase">
            <span>React 18 / Vite</span>
            <span>FastAPI</span>
            <span>Llama-3.3-70B</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;

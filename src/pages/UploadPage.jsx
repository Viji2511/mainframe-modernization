import React, { useState } from 'react';
import FileDropzone from '../components/FileDropzone';
import ChatInterface from '../components/ChatInterface';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import { parsePrompt } from '../utils/promptParser';
import { Play, Loader2, Info } from 'lucide-react';

const UploadPage = () => {
  const { addJob, setCurrentPage, currentResult, jobs, backendOnline } = useAppStore();
  const api = useApi();

  const [files, setFiles] = useState([]);
  const [dbType, setDbType] = useState('postgresql');
  const [dsnFilter, setDsnFilter] = useState('');
  const [listVsamOnly, setListVsamOnly] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  // Chat copilot messages state
  const [messages, setMessages] = useState([
    {
      sender: 'system',
      text: "Welcome to MainframeAI! Upload your mainframe codebases (ZIP or files) on the left panel, and ask me questions or run pipelines directly.",
    },
  ]);
  const [promptInput, setPromptInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);

  const handleFilesSelected = (newFiles) => {
    setFiles((prev) => [...prev, ...newFiles]);
  };

  const handleRemoveFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const startPipelineRun = async (overrideDsn = null) => {
    if (files.length === 0) return;
    setIsRunning(true);

    try {
      const formData = new FormData();
      files.forEach((file) => {
        formData.append('files', file);
      });

      const uploadRes = await api.post('/api/upload', formData);
      const jobId = uploadRes.job_id;

      const runOptions = {
        job_id: jobId,
        db: dbType,
        dsn: overrideDsn !== null ? overrideDsn : dsnFilter.trim() || undefined,
        list_vsam: listVsamOnly,
      };

      await api.post('/api/run', runOptions);

      const jobObject = {
        job_id: jobId,
        status: 'queued',
        db: dbType,
        dsn: runOptions.dsn || 'ALL',
        files_count: files.length,
        created_at: new Date().toISOString(),
      };
      addJob(jobObject);

      setCurrentPage('jobs');
    } catch (err) {
      alert(`Pipeline execution failed: ${err.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  const handleSendPrompt = async () => {
    if (!promptInput.trim()) return;

    const userText = promptInput.trim();
    setMessages((prev) => [...prev, { sender: 'user', text: userText }]);
    setPromptInput('');
    setIsThinking(true);

    setTimeout(async () => {
      const activeJob = jobs.length > 0 ? jobs[0] : null;
      const parsed = parsePrompt(userText, currentResult, activeJob);

      if (parsed.type === 'analyse') {
        if (files.length === 0) {
          setMessages((prev) => [
            ...prev,
            { sender: 'system', text: 'Please add mainframe source files on the left panel to execute an analysis.' },
          ]);
        } else {
          setMessages((prev) => [
            ...prev,
            { sender: 'system', text: `Starting async modernizer run targeting DSN segment "${parsed.content}"...` },
          ]);
          startPipelineRun(parsed.content);
        }
      } else if (parsed.type === 'text') {
        setMessages((prev) => [...prev, { sender: 'system', text: parsed.content }]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            sender: 'system',
            text: `Retrieved data mapping report:`,
            cardType: parsed.type,
            data: parsed.content,
          },
        ]);
      }
      setIsThinking(false);
    }, 800);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch">
      {/* Brutalist Tagline & Upload column */}
      <div className="lg:col-span-5 space-y-6">
        <div className="pb-2">
          {/* Neon micro-tag */}
          <span className="inline-block bg-[#00ff4c]/20 text-green-700 border border-green-500/40 text-[9px] font-mono font-bold tracking-widest uppercase px-2 py-0.5 rounded mb-3">
            Agentic AI Systems
          </span>
          <h1 className="font-serif text-5xl font-normal leading-[1.1] text-black tracking-tight mb-3">
            We modernize,<br />not replace
          </h1>
          <p className="text-xs text-zinc-700 leading-relaxed font-sans max-w-sm">
            MainframeAI creates Agentic Systems that adapt to your legacy assets, translating database schemas and business logic without breaking workflow velocity. Every rule compounds.
          </p>
        </div>

        {/* Upload box */}
        <div className="rounded bg-white border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-5 space-y-4">
          <h2 className="text-[10px] font-bold font-mono tracking-widest text-black uppercase">
            File Ingestion
          </h2>
          <FileDropzone
            files={files}
            onFilesSelected={handleFilesSelected}
            onRemoveFile={handleRemoveFile}
          />
        </div>

        {/* Options Panel */}
        <div className="rounded bg-white border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-5 space-y-4">
          <h2 className="text-[10px] font-bold font-mono tracking-widest text-black uppercase">
            Run Configurations
          </h2>
          
          <div className="space-y-4 text-xs">
            {/* DB selector */}
            <div className="flex items-center justify-between border-b border-black pb-3">
              <span className="text-zinc-600 font-mono font-semibold uppercase text-[10px]">Target Dialect:</span>
              <div className="flex rounded bg-[#f4f4f0] p-0.5 border border-black">
                <button
                  onClick={() => setDbType('postgresql')}
                  className={`rounded px-2.5 py-1 font-mono font-bold text-[10px] uppercase transition-colors ${
                    dbType === 'postgresql'
                      ? 'bg-black text-[#00ff4c]'
                      : 'text-zinc-500 hover:text-black'
                  }`}
                >
                  PostgreSQL
                </button>
                <button
                  onClick={() => setDbType('mysql')}
                  className={`rounded px-2.5 py-1 font-mono font-bold text-[10px] uppercase transition-colors ${
                    dbType === 'mysql'
                      ? 'bg-black text-[#00ff4c]'
                      : 'text-zinc-500 hover:text-black'
                  }`}
                >
                  MySQL
                </button>
              </div>
            </div>

            {/* DSN filter */}
            <div className="flex flex-col gap-1.5 border-b border-black pb-3">
              <span className="text-zinc-600 font-mono font-semibold uppercase text-[10px]">Filter Target DSN:</span>
              <input
                type="text"
                value={dsnFilter}
                onChange={(e) => setDsnFilter(e.target.value)}
                placeholder="e.g. ACCTDATA (Optional)"
                className="rounded border-2 border-black bg-white px-2.5 py-1.5 text-xs text-black focus:border-[#00ff4c] focus:outline-none font-mono"
              />
            </div>

            {/* List VSAM only */}
            <div className="flex items-center justify-between">
              <div className="flex flex-col">
                <span className="text-zinc-600 font-mono font-semibold uppercase text-[10px]">Discovery Mode Only:</span>
                <span className="text-[9px] text-zinc-500 font-sans mt-0.5 font-medium">Skip copybook logic mappings</span>
              </div>
              <button
                onClick={() => setListVsamOnly(!listVsamOnly)}
                className={`w-9 h-5 rounded-full p-0.5 transition-colors duration-200 border border-black focus:outline-none ${
                  listVsamOnly ? 'bg-black' : 'bg-zinc-200'
                }`}
              >
                <div
                  className={`w-4 h-4 rounded-full bg-white border border-black transition-transform duration-200 transform ${
                    listVsamOnly ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Trigger button */}
          <button
            onClick={() => startPipelineRun()}
            disabled={files.length === 0 || isRunning || !backendOnline}
            className="flex w-full items-center justify-center gap-2 border-2 border-black bg-[#00ff4c] py-2.5 font-mono text-xs font-bold uppercase tracking-wider text-black hover:bg-[#00e676] shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isRunning ? (
              <>
                <Loader2 size={14} className="animate-spin" /> RUNNING...
              </>
            ) : (
              <>
                <Play size={12} /> RUN PIPELINE
              </>
            )}
          </button>

          {!backendOnline && (
            <div className="flex gap-1.5 items-center justify-center text-[9px] text-red-600 font-mono font-semibold uppercase">
              <Info size={10} /> FastAPI offline! Start service to run
            </div>
          )}
        </div>
      </div>

      {/* Copilot Chat column */}
      <div className="lg:col-span-7 h-full flex flex-col">
        <ChatInterface
          messages={messages}
          promptInput={promptInput}
          setPromptInput={setPromptInput}
          onSendPrompt={handleSendPrompt}
          isThinking={isThinking}
        />
      </div>
    </div>
  );
};

export default UploadPage;

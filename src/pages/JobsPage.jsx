import React, { useEffect, useState } from 'react';
import StatusBadge from '../components/StatusBadge';
import { useAppStore } from '../store/appStore';
import { useApi } from '../hooks/useApi';
import { useJobPolling } from '../hooks/useJobPolling';
import { Trash2, ExternalLink, RefreshCw } from 'lucide-react';

const JobsPage = () => {
  const { jobs, setJobs, deleteJobState, setCurrentJobId, setCurrentResult, setCurrentPage, backendOnline } = useAppStore();
  const api = useApi();
  const [loading, setLoading] = useState(false);

  useJobPolling();

  const fetchJobs = async () => {
    if (!backendOnline) return;
    setLoading(true);
    try {
      const data = await api.get('/api/jobs');
      setJobs(data);
    } catch (err) {
      console.error('Error fetching jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [backendOnline]);

  const handleOpenResults = async (jobId) => {
    try {
      const resultData = await api.get(`/api/result/${jobId}`);
      if (resultData && !resultData.status) {
        const primaryResult = Array.isArray(resultData) ? resultData[0] : resultData;
        setCurrentResult(primaryResult);
        setCurrentJobId(jobId);
        setCurrentPage('results');
      } else {
        alert('Results are not ready or this job encountered errors.');
      }
    } catch (err) {
      alert(`Could not load results: ${err.message}`);
    }
  };

  const handleDeleteJob = async (jobId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this job and all associated workspace assets?')) return;
    
    try {
      await api.delete(`/api/jobs/${jobId}`);
      deleteJobState(jobId);
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b-2 border-black pb-4 gap-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-black">PIPELINE EXECUTION LOGS</h1>
          <p className="text-xs text-zinc-600 mt-1 font-sans">Monitor pipeline runs, validation checks, and data layouts.</p>
        </div>
        <button
          onClick={fetchJobs}
          className="flex items-center gap-1.5 border-2 border-black bg-white px-3 py-1.5 text-xs font-bold text-black hover:bg-zinc-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] font-mono shrink-0"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> RELOAD JOBS
        </button>
      </div>

      {/* Jobs grid table */}
      <div className="overflow-x-auto border-2 border-black rounded bg-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
        <table className="min-w-full divide-y-2 divide-black text-left">
          <thead className="bg-[#f4f4f0] font-mono text-[10px] uppercase text-black tracking-wider font-bold">
            <tr>
              <th className="px-4 py-3 border-r-2 border-black">Job ID</th>
              <th className="px-4 py-3 border-r-2 border-black">Source Input</th>
              <th className="px-4 py-3 border-r-2 border-black">Target DSN</th>
              <th className="px-4 py-3 border-r-2 border-black">Database</th>
              <th className="px-4 py-3 border-r-2 border-black">Status</th>
              <th className="px-4 py-3 border-r-2 border-black">Started At</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y-2 divide-black bg-white text-xs font-mono text-black">
            {jobs.length > 0 ? (
              jobs.map((job) => (
                <tr 
                  key={job.job_id} 
                  onClick={() => job.status === 'done' && handleOpenResults(job.job_id)}
                  className={`transition-colors border-black ${
                    job.status === 'done' 
                      ? 'hover:bg-zinc-50 cursor-pointer' 
                      : 'opacity-80'
                  }`}
                >
                  <td className="px-4 py-3 text-blue-600 font-bold border-r-2 border-black truncate max-w-[120px]">
                    {job.job_id}
                  </td>
                  <td className="px-4 py-3 text-black border-r-2 border-black">
                    {job.files_count} files loaded
                  </td>
                  <td className="px-4 py-3 text-yellow-600 font-bold border-r-2 border-black">
                    {job.dsn}
                  </td>
                  <td className="px-4 py-3 uppercase text-zinc-500 border-r-2 border-black">
                    {job.db}
                  </td>
                  <td className="px-4 py-3 border-r-2 border-black">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-500 text-[10px] border-r-2 border-black">
                    {job.created_at ? new Date(job.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {job.status === 'done' && (
                        <button
                          onClick={() => handleOpenResults(job.job_id)}
                          className="flex items-center gap-1 bg-[#00ff4c] text-black border-2 border-black px-2 py-1 text-[9px] font-bold uppercase tracking-wider hover:bg-[#00e676]"
                        >
                          <ExternalLink size={10} /> View Result
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDeleteJob(job.job_id, e)}
                        className="p-1 text-black hover:text-red-600 rounded border border-transparent hover:border-black hover:bg-zinc-50"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-zinc-500 font-sans text-sm">
                  {loading ? 'Fetching pipeline history logs...' : 'No job records found. Run the pipeline on the Upload Page.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default JobsPage;

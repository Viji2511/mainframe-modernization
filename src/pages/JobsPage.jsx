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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-gray-200 pb-4 gap-4">
        <div>
          <h1 className="text-2xl font-bold font-mono text-gray-900">PIPELINE EXECUTION LOGS</h1>
          <p className="text-xs text-zinc-600 mt-1 font-sans">Monitor pipeline runs, validation checks, and data layouts.</p>
        </div>
        <button
          onClick={fetchJobs}
          className="flex items-center gap-1.5 border border-gray-200 bg-white px-3 py-1.5 text-xs font-bold text-gray-900 hover:bg-zinc-50 shadow-sm rounded-lg font-mono shrink-0"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> RELOAD JOBS
        </button>
      </div>

      {/* Jobs grid table */}
      <div className="overflow-x-auto border border-gray-200 rounded bg-white shadow-sm rounded-lg">
        <table className="min-w-full divide-y-2 divide-black text-left">
          <thead className="bg-[#f3f4f6] font-mono text-[10px] uppercase text-gray-900 tracking-wider font-bold">
            <tr>
              <th className="px-4 py-3 border-r border-gray-200">Job ID</th>
              <th className="px-4 py-3 border-r border-gray-200">Source Input</th>
              <th className="px-4 py-3 border-r border-gray-200">Target DSN</th>
              <th className="px-4 py-3 border-r border-gray-200">Database</th>
              <th className="px-4 py-3 border-r border-gray-200">Status</th>
              <th className="px-4 py-3 border-r border-gray-200">Started At</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y-2 divide-black bg-white text-xs font-mono text-gray-900">
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
                  <td className="px-4 py-3 text-blue-600 font-bold border-r border-gray-200 truncate max-w-[120px]">
                    {job.job_id}
                  </td>
                  <td className="px-4 py-3 text-gray-900 border-r border-gray-200">
                    {job.files_count} files loaded
                  </td>
                  <td className="px-4 py-3 text-yellow-600 font-bold border-r border-gray-200">
                    {job.dsn}
                  </td>
                  <td className="px-4 py-3 uppercase text-zinc-500 border-r border-gray-200">
                    {job.db}
                  </td>
                  <td className="px-4 py-3 border-r border-gray-200">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-500 text-[10px] border-r border-gray-200">
                    {job.created_at ? new Date(job.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {job.status === 'done' && (
                        <button
                          onClick={() => handleOpenResults(job.job_id)}
                          className="flex items-center gap-1 bg-blue-600 text-white text-gray-900 border border-gray-200 px-2 py-1 text-[9px] font-bold uppercase tracking-wider hover:bg-blue-700"
                        >
                          <ExternalLink size={10} /> View Result
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDeleteJob(job.job_id, e)}
                        className="p-1 text-gray-900 hover:text-red-600 rounded border border-transparent hover:border-gray-400 hover:bg-zinc-50"
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

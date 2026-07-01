import { useEffect } from 'react';
import { useAppStore } from '../store/appStore';
import { useApi } from './useApi';

export const useJobPolling = () => {
  const { jobs, addJob, setCurrentResult } = useAppStore();
  const api = useApi();

  useEffect(() => {
    // Check if any job is currently active
    const activeJobs = jobs.filter(
      (job) => job.status === 'running' || job.status === 'queued'
    );

    if (activeJobs.length === 0) return;

    const pollInterval = setInterval(async () => {
      for (const job of activeJobs) {
        try {
          const statusResult = await api.get(`/api/status/${job.job_id}`);
          
          if (statusResult.status !== job.status) {
            // Update job state
            const updatedJob = { 
              ...job, 
              status: statusResult.status,
              completed_at: statusResult.completed_at,
              error: statusResult.error 
            };
            addJob(updatedJob);

            // If it just finished, fetch the results
            if (statusResult.status === 'done') {
              const resultData = await api.get(`/api/result/${job.job_id}`);
              // If it's a list or single result, load it
              if (resultData && !resultData.status) {
                // Save first result as primary viewed dataset
                const primaryResult = Array.isArray(resultData) ? resultData[0] : resultData;
                setCurrentResult(primaryResult);
              }
            }
          }
        } catch (err) {
          console.error(`Error polling status for job ${job.job_id}:`, err);
        }
      }
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [jobs, addJob, api, setCurrentResult]);
};

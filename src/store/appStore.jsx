import React, { createContext, useContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';

const AppStoreContext = createContext(null);

export const AppProvider = ({ children }) => {
  const [currentPage, setCurrentPage] = useState(() => {
    return localStorage.getItem('mainframe_ai_current_page') || 'upload';
  });
  const [activeTab, setActiveTab] = useState('overview');
  const [currentJobId, setCurrentJobId] = useState(() => {
    return localStorage.getItem('mainframe_ai_current_job_id') || null;
  });
  const [currentResult, setCurrentResult] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [backendOnline, setBackendOnline] = useState(false);
  const [settings, setSettings] = useState(() => {
    const saved = localStorage.getItem('mainframe_ai_settings');
    return saved ? JSON.parse(saved) : { apiBaseUrl: 'http://localhost:8000' };
  });

  useEffect(() => {
    localStorage.setItem('mainframe_ai_settings', JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    localStorage.setItem('mainframe_ai_current_page', currentPage);
  }, [currentPage]);

  useEffect(() => {
    if (currentJobId) {
      localStorage.setItem('mainframe_ai_current_job_id', currentJobId);
    } else {
      localStorage.removeItem('mainframe_ai_current_job_id');
    }
  }, [currentJobId]);

  // Ping backend to check health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${settings.apiBaseUrl}/api/health`);
        if (res.ok) {
          setBackendOnline(true);
        } else {
          setBackendOnline(false);
        }
      } catch (err) {
        setBackendOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, [settings.apiBaseUrl]);

  // Fetch jobs once on startup / backend connection
  useEffect(() => {
    if (!backendOnline) return;
    const loadInitialJobs = async () => {
      try {
        const res = await fetch(`${settings.apiBaseUrl}/api/jobs`);
        if (res.ok) {
          const data = await res.json();
          setJobs(data);
        }
      } catch (err) {
        console.error('Failed to load initial jobs:', err);
      }
    };
    loadInitialJobs();
  }, [backendOnline, settings.apiBaseUrl]);

  // Auto-select latest completed job on startup if none is active
  useEffect(() => {
    if (jobs.length > 0 && !currentJobId) {
      const completed = jobs.find(j => j.status === 'done');
      if (completed) {
        setCurrentJobId(completed.job_id);
      }
    }
  }, [jobs, currentJobId]);

  const updateSettings = (newSettings) => {
    setSettings((prev) => ({ ...prev, ...newSettings }));
  };

  const addJob = (job) => {
    setJobs((prev) => {
      const exists = prev.some((j) => j.job_id === job.job_id);
      if (exists) {
        return prev.map((j) => (j.job_id === job.job_id ? { ...j, ...job } : j));
      }
      return [job, ...prev];
    });
  };

  const deleteJobState = (jobId) => {
    setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    if (currentJobId === jobId) {
      setCurrentJobId(null);
      setCurrentResult(null);
    }
  };

  return (
    <AppStoreContext.Provider
      value={{
        currentPage,
        setCurrentPage,
        activeTab,
        setActiveTab,
        currentJobId,
        setCurrentJobId,
        currentResult,
        setCurrentResult,
        jobs,
        setJobs,
        addJob,
        deleteJobState,
        sidebarOpen,
        setSidebarOpen,
        settings,
        updateSettings,
        backendOnline,
      }}
    >
      {children}
    </AppStoreContext.Provider>
  );
};

AppProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

export const useAppStore = () => {
  const context = useContext(AppStoreContext);
  if (!context) {
    throw new Error('useAppStore must be used within an AppProvider');
  }
  return context;
};

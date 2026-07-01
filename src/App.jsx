import React, { lazy, Suspense } from 'react';
import Sidebar from './components/Sidebar';
import { useAppStore } from './store/appStore';

const UploadPage = lazy(() => import('./pages/UploadPage'));
const JobsPage = lazy(() => import('./pages/JobsPage'));
const ResultsPage = lazy(() => import('./pages/ResultsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

const App = () => {
  const { currentPage, sidebarOpen } = useAppStore();

  const renderPage = () => {
    switch (currentPage) {
      case 'upload':
        return <UploadPage />;
      case 'jobs':
        return <JobsPage />;
      case 'results':
        return <ResultsPage />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <UploadPage />;
    }
  };

  return (
    <div className="flex min-h-screen bg-[#f4f4f0] text-[#0d1117] font-sans selection:bg-[#00ff4c]/40 overflow-hidden">
      
      {/* Outer Brutalist Frame - Left Edge Column */}
      <div className="hidden md:flex w-10 border-r-2 border-black items-center justify-center bg-white select-none shrink-0">
        <div className="transform -rotate-90 text-[8px] font-mono tracking-[0.25em] font-bold text-[#0d1117]/50 uppercase whitespace-nowrap">
          MAINFRAMEAI SYSTEM PORTAL
        </div>
      </div>

      {/* Main Container Enclosure */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen border-r-2 md:border-r-0 border-black">
        


        <div className="flex-1 flex min-w-0 relative">
          {/* Collapsible Sidebar inside main content grid */}
          <Sidebar />

          {/* Page content panel */}
          <div
            className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${
              sidebarOpen ? 'md:pl-64' : 'pl-16'
            }`}
          >
            {/* Page Header */}
            <header className="flex h-14 items-center justify-between border-b-2 border-black bg-white px-6 shrink-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] font-bold tracking-widest text-[#0d1117]/50">WORKSPACE:</span>
                <span className="font-mono text-xs font-bold text-black border-b border-black">
                  mainframe-modernizer
                </span>
              </div>
              <div className="flex items-center gap-4 text-[10px] font-mono font-bold text-[#0d1117]/50">
                <span>V. 1.3</span>
              </div>
            </header>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto p-6 bg-[#f4f4f0]">
              <Suspense
                fallback={
                  <div className="flex h-full items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-black border-t-transparent" />
                  </div>
                }
              >
                {renderPage()}
              </Suspense>
            </div>

            {/* Bottom Footer block */}
            <footer className="border-t-2 border-black py-3 px-6 bg-white font-mono text-[9px] tracking-widest flex flex-col sm:flex-row justify-between gap-2 uppercase text-[#0d1117]/50 shrink-0">
              <div>Born from the spirit of Enterprise Dynamism</div>
              <div className="flex gap-4 sm:gap-6">
                <span>OPTIMIZE</span>
                <span>ADAPT</span>
                <span>EVOLVE</span>
              </div>
            </footer>
          </div>
        </div>
      </div>

      {/* Outer Brutalist Frame - Right Edge Column */}
      <div className="hidden md:flex w-10 border-l-2 border-black items-center justify-center bg-white select-none shrink-0">
        <div className="transform rotate-90 text-[8px] font-mono tracking-[0.25em] font-bold text-[#0d1117]/50 uppercase whitespace-nowrap">
          BORN FROM ENTERPRISE DYNAMISM
        </div>
      </div>
    </div>
  );
};

export default App;

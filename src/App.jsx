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
    <div className="flex min-h-screen bg-[#f3f4f6] text-gray-900 font-sans selection:bg-blue-100 overflow-hidden">
      
      {/* Main Container Enclosure */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        
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
            <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6 shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tracking-wider text-gray-500 uppercase">Workspace:</span>
                <span className="text-sm font-semibold text-gray-900">
                  mainframe-modernizer
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs font-semibold text-gray-500">
              </div>
            </header>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto p-6 bg-[#f3f4f6]">
              <Suspense
                fallback={
                  <div className="flex h-full items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                  </div>
                }
              >
                {renderPage()}
              </Suspense>
            </div>

            {/* Bottom Footer block */}
            <footer className="border-t border-gray-200 py-3 px-6 bg-white text-xs flex flex-col sm:flex-row justify-between gap-2 text-gray-500 shrink-0">
              <div>System Active</div>
              <div className="flex gap-4 sm:gap-6">
                <span>Help</span>
                <span>Privacy</span>
                <span>Terms</span>
              </div>
            </footer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;

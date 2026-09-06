import React from 'react';
import { useAppStore } from '../store/appStore';
import { 
  Upload, 
  Database, 
  FileText, 
  History,
  Settings, 
  ChevronLeft, 
  ChevronRight, 
  Radio, 
  Cpu 
} from 'lucide-react';

const Sidebar = () => {
  const { 
    currentPage, 
    setCurrentPage, 
    sidebarOpen, 
    setSidebarOpen, 
    backendOnline 
  } = useAppStore();

  const navItems = [
    { id: 'upload', name: 'Upload & Prompt', icon: Upload },
    { id: 'jobs', name: 'Pipeline Jobs', icon: Database },
    { id: 'results', name: 'Results Viewer', icon: FileText },
    { id: 'audit', name: 'Audit Trail', icon: History },
    { id: 'settings', name: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={`fixed bottom-0 top-0 left-0 z-20 flex flex-col bg-[#2d2d30] text-gray-300 transition-all duration-300 ${
        sidebarOpen ? 'w-64' : 'w-16'
      }`}
    >
      {/* Sidebar Header */}
      <div className="flex h-14 items-center justify-between px-4 bg-[#2d2d30] border-b border-gray-700">
        <div className="flex items-center gap-2 overflow-hidden">
          <Cpu className="h-5 w-5 text-gray-300 shrink-0" />
          {sidebarOpen && (
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-white">
              Fellow / AI
            </span>
          )}
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="rounded p-1 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
        >
          {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {/* Nav List */}
      <nav className="flex-1 space-y-1 p-3 bg-[#2d2d30]">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;

          return (
            <button
              key={item.id}
              onClick={() => setCurrentPage(item.id)}
              className={`flex w-full items-center gap-3 px-3 py-2 text-xs font-semibold rounded-md transition-all ${
                isActive
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:bg-gray-700 hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {sidebarOpen && <span className="truncate">{item.name}</span>}
            </button>
          );
        })}
      </nav>

      {/* Connection Indicator Footer */}
      <div className="border-t border-gray-700 p-3 bg-[#2d2d30]">
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase">
          <Radio
            className={`h-4 w-4 shrink-0 ${
              backendOnline ? 'text-green-500 animate-pulse' : 'text-red-500'
            }`}
          />
          {sidebarOpen && (
            <span className={backendOnline ? 'text-green-500' : 'text-red-500'}>
              {backendOnline ? 'API Connected' : 'API Offline'}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;

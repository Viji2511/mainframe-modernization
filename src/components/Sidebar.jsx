import React from 'react';
import { useAppStore } from '../store/appStore';
import { 
  Upload, 
  Database, 
  FileText, 
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
    { id: 'settings', name: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={`fixed bottom-0 top-0 left-0 z-20 flex flex-col border-r-2 border-black bg-white transition-all duration-300 ${
        sidebarOpen ? 'w-64' : 'w-16'
      }`}
    >
      {/* Sidebar Header */}
      <div className="flex h-14 items-center justify-between border-b-2 border-black px-4 bg-white">
        <div className="flex items-center gap-2 overflow-hidden">
          <Cpu className="h-5 w-5 text-black shrink-0" />
          {sidebarOpen && (
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-black">
              Fellow / AI
            </span>
          )}
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="rounded border border-transparent p-1 text-black hover:border-black hover:bg-[#f4f4f0]"
        >
          {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {/* Nav List */}
      <nav className="flex-1 space-y-2 p-3 bg-white">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;

          return (
            <button
              key={item.id}
              onClick={() => setCurrentPage(item.id)}
              className={`flex w-full items-center gap-3 px-3 py-2 text-xs font-mono font-bold uppercase transition-all ${
                isActive
                  ? 'bg-[#00ff4c] text-black border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]'
                  : 'text-black hover:bg-black hover:text-[#00ff4c] border-2 border-transparent'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {sidebarOpen && <span className="truncate">{item.name}</span>}
            </button>
          );
        })}
      </nav>

      {/* Connection Indicator Footer */}
      <div className="border-t-2 border-black p-3 bg-white">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase">
          <Radio
            className={`h-4 w-4 shrink-0 ${
              backendOnline ? 'text-green-600 animate-pulse' : 'text-red-600'
            }`}
          />
          {sidebarOpen && (
            <span className={backendOnline ? 'text-green-600' : 'text-red-600'}>
              {backendOnline ? 'API Connected' : 'API Offline'}
            </span>
          )}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;

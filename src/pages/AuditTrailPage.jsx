import React from 'react';
import { History } from 'lucide-react';
import AuditTrail from '../components/AuditTrail';
import { useAppStore } from '../store/appStore';

const AuditTrailPage = () => {
  const { currentJobId } = useAppStore();

  if (!currentJobId) {
    return (
      <div className="mx-auto flex min-h-[55vh] max-w-2xl flex-col items-center justify-center rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm">
        <History size={34} className="mb-3 text-zinc-400" />
        <h1 className="font-mono text-sm font-bold uppercase text-gray-900">Audit Trail</h1>
        <p className="mt-2 max-w-md text-xs text-zinc-500">No audit trail is available yet. Run or select a repository analysis to view execution and modernization decisions.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5 pb-4">
      <header className="border-b border-gray-200 pb-4">
        <h1 className="font-mono text-xl font-bold tracking-wide text-gray-900">AUDIT TRAIL</h1>
        <p className="mt-1 text-xs text-zinc-500">Persistent execution evidence and modernization decisions</p>
      </header>
      <AuditTrail jobId={currentJobId} showHeader={false} fullPage />
    </div>
  );
};

export default AuditTrailPage;

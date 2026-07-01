import React from 'react';
import PropTypes from 'prop-types';
import { CheckCircle2, XCircle, AlertCircle, Loader2 } from 'lucide-react';

const StatusBadge = ({ status }) => {
  const getBadgeStyle = () => {
    switch (status) {
      case 'done':
        return {
          text: 'COMPLETED',
          classes: 'bg-[#00ff4c]/20 text-green-700 border border-green-500/40 font-bold',
          icon: <CheckCircle2 size={10} className="shrink-0" />
        };
      case 'running':
        return {
          text: 'RUNNING',
          classes: 'bg-blue-600/10 text-blue-700 border border-blue-500/40 font-bold',
          icon: <Loader2 size={10} className="animate-spin shrink-0" />
        };
      case 'queued':
        return {
          text: 'QUEUED',
          classes: 'bg-zinc-100 text-zinc-700 border border-zinc-400 font-bold',
          icon: <AlertCircle size={10} className="shrink-0" />
        };
      case 'error':
        return {
          text: 'ERROR',
          classes: 'bg-red-100 text-red-700 border border-red-400 font-bold',
          icon: <XCircle size={10} className="shrink-0" />
        };
      default:
        return {
          text: status.toUpperCase(),
          classes: 'bg-zinc-700/20 text-[#8b949e] border-zinc-600/30',
          icon: null
        };
    }
  };

  const badge = getBadgeStyle();

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] font-bold tracking-wider ${badge.classes}`}
    >
      {badge.icon}
      {badge.text}
    </span>
  );
};

StatusBadge.propTypes = {
  status: PropTypes.string.isRequired,
};

export default StatusBadge;

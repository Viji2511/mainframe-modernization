import React from 'react';
import PropTypes from 'prop-types';
import { Database, FileCode2, FileText, Settings, Settings2 } from 'lucide-react';

const DependencyCategory = ({ title, items, icon: Icon, onSelectDependency }) => {
  if (!items || items.length === 0) return null;

  return (
    <div className="mb-3 shrink-0">
      <div className="font-bold text-gray-700 flex items-center gap-1 text-[11px] font-mono mb-1">
        {title}
      </div>
      <div className="pl-3 space-y-0.5">
        {items.map((item, i) => (
          <button
            key={i}
            onClick={() => onSelectDependency(item)}
            className="cursor-pointer text-blue-600 hover:underline flex items-center gap-1 text-[11px] font-mono text-left w-full focus:outline-none"
          >
            <Icon size={12} className="shrink-0" />
            <span className="truncate">{item}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

DependencyCategory.propTypes = {
  title: PropTypes.string.isRequired,
  items: PropTypes.array,
  icon: PropTypes.elementType.isRequired,
  onSelectDependency: PropTypes.func.isRequired,
};

const DependencyPanel = ({ dependencies, onSelectDependency }) => {
  if (!dependencies) return null;

  const hasDependencies = Object.values(dependencies).some((arr) => arr && arr.length > 0);

  if (!hasDependencies) {
    return (
      <div className="mb-4 shrink-0">
        <h4 className="font-mono text-[11px] font-bold text-gray-900 uppercase tracking-widest border-b pb-1 mb-2">
          Dependencies
        </h4>
        <div className="text-[11px] text-zinc-500 font-mono italic">No dependencies found.</div>
      </div>
    );
  }

  return (
    <div className="mb-4 shrink-0">
      <h4 className="font-mono text-[11px] font-bold text-gray-900 uppercase tracking-widest border-b pb-1 mb-2">
        Dependencies
      </h4>
      <div className="flex flex-col">
        <DependencyCategory
          title="Copybooks"
          items={dependencies.copybooks}
          icon={FileText}
          onSelectDependency={onSelectDependency}
        />
        <DependencyCategory
          title="Datasets"
          items={dependencies.datasets}
          icon={Database}
          onSelectDependency={onSelectDependency}
        />
        <DependencyCategory
          title="Called Programs"
          items={dependencies.calledPrograms}
          icon={FileCode2}
          onSelectDependency={onSelectDependency}
        />
        <DependencyCategory
          title="JCL References"
          items={dependencies.jclJobs}
          icon={FileCode2}
          onSelectDependency={onSelectDependency}
        />
        <DependencyCategory
          title="Utilities"
          items={dependencies.utilities}
          icon={Settings}
          onSelectDependency={onSelectDependency}
        />
        <DependencyCategory
          title="IDCAMS"
          items={dependencies.idcams}
          icon={Settings2}
          onSelectDependency={onSelectDependency}
        />
      </div>
    </div>
  );
};

DependencyPanel.propTypes = {
  dependencies: PropTypes.object,
  onSelectDependency: PropTypes.func.isRequired,
};

export default DependencyPanel;

import React from 'react';
import PropTypes from 'prop-types';

const ArtifactDetails = ({ details }) => {
  if (!details) return null;

  return (
    <div className="mb-4 shrink-0">
      <h4 className="font-mono text-[11px] font-bold text-gray-900 uppercase tracking-widest border-b pb-1 mb-2">
        Artifact Details
      </h4>
      <div className="grid grid-cols-[100px_1fr] gap-x-2 gap-y-1 text-[11px] font-mono text-gray-800">
        {details.type && (
          <>
            <div className="text-zinc-500">Type</div>
            <div className="truncate" title={details.type}>{details.type}</div>
          </>
        )}
        {details.name && (
          <>
            <div className="text-zinc-500">Name</div>
            <div className="truncate font-bold" title={details.name}>{details.name}</div>
          </>
        )}
        {details.physicalFile && (
          <>
            <div className="text-zinc-500">Physical File</div>
            <div className="truncate" title={details.physicalFile}>{details.physicalFile}</div>
          </>
        )}
        {details.repositoryPath && (
          <>
            <div className="text-zinc-500">Repository Path</div>
            <div className="truncate" title={details.repositoryPath}>{details.repositoryPath}</div>
          </>
        )}
        {details.language && (
          <>
            <div className="text-zinc-500">Language</div>
            <div className="truncate" title={details.language}>{details.language}</div>
          </>
        )}
        {details.parser && (
          <>
            <div className="text-zinc-500">Parser</div>
            <div className="truncate" title={details.parser}>{details.parser}</div>
          </>
        )}
        {details.id && (
          <>
            <div className="text-zinc-500">Artifact ID</div>
            <div className="truncate" title={details.id}>{details.id}</div>
          </>
        )}
      </div>
    </div>
  );
};

ArtifactDetails.propTypes = {
  details: PropTypes.object,
};

export default ArtifactDetails;

import React, { useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { UploadCloud, File, Trash2 } from 'lucide-react';
import { classifyFile } from '../utils/fileClassifier';

const FileDropzone = ({ files, onFilesSelected, onRemoveFile }) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFilesSelected(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      onFilesSelected(Array.from(e.target.files));
    }
  };

  const getStatsString = () => {
    const counts = { CBL: 0, CPY: 0, JCL: 0, TXT: 0, PLI: 0, NAT: 0, RPG: 0, OTHER: 0 };
    files.forEach((file) => {
      const typeInfo = classifyFile(file.name);
      if (typeInfo.label === 'COBOL') counts.CBL++;
      else if (typeInfo.label === 'Copybook') counts.CPY++;
      else if (typeInfo.label === 'JCL') counts.JCL++;
      else if (typeInfo.label === 'TXT') counts.TXT++;
      else if (typeInfo.label === 'PL/I') counts.PLI++;
      else if (typeInfo.label === 'Natural') counts.NAT++;
      else if (typeInfo.label === 'RPG') counts.RPG++;
      else counts.OTHER++;
    });

    const segments = [];
    if (counts.CBL > 0) segments.push(`${counts.CBL} CBL`);
    if (counts.CPY > 0) segments.push(`${counts.CPY} CPY`);
    if (counts.JCL > 0) segments.push(`${counts.JCL} JCL`);
    if (counts.TXT > 0) segments.push(`${counts.TXT} TXT`);
    if (counts.PLI > 0) segments.push(`${counts.PLI} PL/I`);
    if (counts.NAT > 0) segments.push(`${counts.NAT} Natural`);
    if (counts.RPG > 0) segments.push(`${counts.RPG} RPG`);
    if (counts.OTHER > 0) segments.push(`${counts.OTHER} Other`);

    return segments.length > 0 ? segments.join(' | ') : 'No files added';
  };

  return (
    <div className="space-y-4">
      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`flex flex-col items-center justify-center rounded border-2 border-dashed p-6 text-center cursor-pointer transition-all ${
          isDragActive 
            ? 'border-[#00ff4c] bg-[#00ff4c]/5' 
            : 'border-black bg-[#f4f4f0] hover:bg-zinc-100'
        }`}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileInput}
          multiple
          className="hidden"
        />
        <UploadCloud className="h-8 w-8 text-black mb-3" />
        <p className="text-xs font-mono font-bold text-black uppercase">
          Drag and drop ZIP or raw mainframe assets here
        </p>
        <p className="text-[10px] text-zinc-500 font-mono mt-1 uppercase">
          [cbl, cpy, jcl, txt, pli, rpgle]
        </p>
      </div>

      {/* Stats Summary */}
      {files.length > 0 && (
        <div className="rounded border-2 border-black bg-white px-4 py-2 font-mono text-[10px] font-bold uppercase text-black">
          {getStatsString()}
        </div>
      )}

      {/* Files List */}
      {files.length > 0 && (
        <div className="max-h-60 overflow-y-auto space-y-2 border-2 border-black rounded p-2 bg-[#f4f4f0]">
          {files.map((file, idx) => {
            const classInfo = classifyFile(file.name);
            return (
              <div
                key={idx}
                className="flex items-center justify-between rounded bg-white p-2 border border-black hover:bg-zinc-50 transition-colors"
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <File size={14} className="text-black shrink-0" />
                  <span className="truncate text-[10px] font-mono font-medium text-black">{file.name}</span>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase font-mono shrink-0 ${classInfo.color}`}>
                    {classInfo.label}
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveFile(idx);
                  }}
                  className="p-1 text-black hover:text-red-600"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

FileDropzone.propTypes = {
  files: PropTypes.array.isRequired,
  onFilesSelected: PropTypes.func.isRequired,
  onRemoveFile: PropTypes.func.isRequired,
};

export default FileDropzone;
// Change default tags styles inside classifyFile to have black borders for brutalist design

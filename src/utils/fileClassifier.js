/**
 * Classifies file extensions into specific mainframe dialect categories.
 */
export const classifyFile = (filename) => {
  const ext = filename.split('.').pop().toLowerCase();
  
  switch (ext) {
    case 'cbl':
    case 'cob':
    case 'cobol':
      return { label: 'COBOL', color: 'bg-blue-200 text-blue-900 border border-black font-bold' };
    case 'cpy':
    case 'copy':
      return { label: 'Copybook', color: 'bg-green-200 text-green-950 border border-black font-bold' };
    case 'jcl':
    case 'job':
    case 'cntl':
      return { label: 'JCL', color: 'bg-yellow-100 text-yellow-955 border border-black font-bold' };
    case 'txt':
    case 'lst':
    case 'log':
      return { label: 'TXT', color: 'bg-zinc-200 text-zinc-900 border border-black font-bold' };
    case 'pli':
    case 'pl1':
    case 'inc':
    case 'dcl':
      return { label: 'PL/I', color: 'bg-purple-200 text-purple-900 border border-black font-bold' };
    case 'ddm':
    case 'nsl':
      return { label: 'Natural', color: 'bg-pink-200 text-pink-900 border border-black font-bold' };
    case 'rpg':
    case 'rpgle':
      return { label: 'RPG', color: 'bg-indigo-200 text-indigo-900 border border-black font-bold' };
    default:
      return { label: 'Other', color: 'bg-zinc-700/20 text-zinc-400 border border-zinc-600/30' };
  }
};

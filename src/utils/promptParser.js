/**
 * Parses user prompt text offline to filter current pipeline results or guide interface states.
 */
export const parsePrompt = (promptText, currentResult, activeJob) => {
  const text = promptText.trim().toLowerCase();

  // 1. Help
  if (text === 'help' || text === '?') {
    return {
      type: 'text',
      content: `I can help you analyze modernizer results! Try these commands:
• "show vsam" or "list vsam" — Show discovered VSAM datasets.
• "analyse [DSN]" — Run pipeline for a specific DSN.
• "fields [DSN]" — Show fields table for a dataset.
• "operations [PROGRAM]" — Show CRUD operations for a program.
• "business rules [PROGRAM]" — Show business rules in a program.
• "status" — Check active job status.
• "compare [DSN1] [DSN2]" — Compare two datasets side-by-side.`
    };
  }

  // 2. Status
  if (text.includes('status')) {
    if (!activeJob) {
      return { type: 'text', content: 'No active modernization job is currently executing.' };
    }
    return {
      type: 'status',
      content: `Job **${activeJob.job_id}** is currently **${activeJob.status}**. (Target DB: ${activeJob.db})`
    };
  }

  // 3. Compare DSNs
  const compareMatch = text.match(/compare\s+([a-z0-9._-]+)\s+and\s+([a-z0-9._-]+)/i) || 
                       text.match(/compare\s+([a-z0-9._-]+)\s+([a-z0-9._-]+)/i);
  if (compareMatch) {
    const dsn1 = compareMatch[1].toUpperCase();
    const dsn2 = compareMatch[2].toUpperCase();
    return {
      type: 'compare',
      content: { dsn1, dsn2 }
    };
  }

  // 4. Fields check
  const fieldsMatch = text.match(/(?:fields|schema|layout)\s+for\s+([a-z0-9._-]+)/i) ||
                      text.match(/fields\s+([a-z0-9._-]+)/i) ||
                      text.match(/what\s+fields\s+does\s+([a-z0-9._-]+)\s+have/i);
  if (fieldsMatch) {
    const dsn = fieldsMatch[1].toUpperCase();
    if (!currentResult) {
      return { type: 'text', content: 'Please upload files and run the pipeline first to inspect fields.' };
    }
    
    // Look up dataset matching dsn
    const isMatch = currentResult.vsam_dataset.dsn.toUpperCase().includes(dsn);
    if (!isMatch) {
      return { type: 'text', content: `No matching fields found. Dataset DSN "${dsn}" was not matched in the current result.` };
    }

    if (!currentResult.copybook || currentResult.copybook.fields.length === 0) {
      return { type: 'text', content: `Dataset DSN "${dsn}" has no copybook fields associated.` };
    }

    return {
      type: 'fields',
      content: {
        dsn: currentResult.vsam_dataset.dsn,
        fields: currentResult.copybook.fields,
        filename: currentResult.copybook.filename
      }
    };
  }

  // 5. Operations in program
  const opsMatch = text.match(/(?:operations|verbs|ops)\s+(?:in|for)\s+([a-z0-9_-]+)/i) ||
                   text.match(/operations\s+([a-z0-9_-]+)/i) ||
                   text.match(/what\s+operations\s+in\s+([a-z0-9_-]+)/i);
  if (opsMatch) {
    const prog = opsMatch[1].toUpperCase();
    if (!currentResult || !currentResult.source_analyses) {
      return { type: 'text', content: 'No results loaded. Please run the pipeline first.' };
    }

    const progAnalysis = currentResult.source_analyses.find(
      (a) => a.program_name.toUpperCase().includes(prog) || prog.includes(a.program_name.toUpperCase())
    );

    if (!progAnalysis) {
      return { type: 'text', content: `Program "${prog}" was not found in the source code analysis.` };
    }

    return {
      type: 'ops',
      content: {
        program: progAnalysis.program_name,
        operations: progAnalysis.operations,
        key_fields: progAnalysis.key_fields
      }
    };
  }

  // 6. Business rules in program
  const rulesMatch = text.match(/(?:business\s+rules|rules)\s+(?:in|for)\s+([a-z0-9_-]+)/i) ||
                     text.match(/rules\s+([a-z0-9_-]+)/i);
  if (rulesMatch) {
    const prog = rulesMatch[1].toUpperCase();
    if (!currentResult || !currentResult.source_analyses) {
      return { type: 'text', content: 'No results loaded. Please run the pipeline first.' };
    }

    const progAnalysis = currentResult.source_analyses.find(
      (a) => a.program_name.toUpperCase().includes(prog) || prog.includes(a.program_name.toUpperCase())
    );

    if (!progAnalysis || !progAnalysis.business_rules.length) {
      return { type: 'text', content: `No business rules found for program "${prog}".` };
    }

    return {
      type: 'rules',
      content: {
        program: progAnalysis.program_name,
        rules: progAnalysis.business_rules
      }
    };
  }

  // 7. Show VSAM datasets
  if (text.includes('list vsam') || text.includes('show vsam') || text.includes('list datasets')) {
    if (!currentResult) {
      return { type: 'text', content: 'No dataset records are currently loaded.' };
    }
    return {
      type: 'vsam',
      content: {
        dsn: currentResult.vsam_dataset.dsn,
        type: currentResult.vsam_dataset.vsam_type,
        length: currentResult.vsam_dataset.record_length,
        confidence: currentResult.vsam_dataset.confidence
      }
    };
  }

  // 8. Analyse DSN command
  const analyseMatch = text.match(/analyse\s+([a-z0-9._-]+)/i) || text.match(/analyze\s+([a-z0-9._-]+)/i);
  if (analyseMatch) {
    return {
      type: 'analyse',
      content: analyseMatch[1].toUpperCase()
    };
  }

  // Generic fallback message
  return {
    type: 'text',
    content: `I received your message: "${promptText}". Type "help" or "?" to see the list of commands I can run on your current dataset.`
  };
};

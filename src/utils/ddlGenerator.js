/**
 * Converts COBOL field structures recursively into standard relational SQL DDL CREATE TABLE statements.
 */
export const generateDDL = (dsn, fields, dialect = 'postgresql') => {
  if (!dsn || !fields || fields.length === 0) {
    return '-- No fields or DSN available to generate DDL.';
  }

  // Create clean database table name
  const tableName = dsn.split('.').pop().toLowerCase() || 'migrated_table';
  
  // Recursively extract all leaf fields (actual data storage variables)
  const columns = [];
  const primaryKeys = [];

  const extractLeaves = (fieldList) => {
    fieldList.forEach((field) => {
      if (field.children && field.children.length > 0) {
        extractLeaves(field.children);
      } else {
        // Build SQL column details
        const columnName = field.name.toLowerCase().replace(/[^a-z0-9_]/g, '_');
        const sqlInfo = mapCobolToSqlType(field, dialect);
        
        // Track potential primary keys (if name contains ID, KEY, code)
        const isId = columnName.includes('id') || columnName.includes('key');
        if (isId && primaryKeys.length === 0) {
          primaryKeys.push(columnName);
        }

        columns.push({
          name: columnName,
          type: sqlInfo.type,
          pic: field.pic,
          cobolType: field.cobol_type,
          originalName: field.name
        });
      }
    });
  };

  extractLeaves(fields);

  if (columns.length === 0) {
    return `-- No storage variables parsed in copybook fields to form SQL columns.`;
  }

  // Build the CREATE TABLE DDL string
  let ddl = `-- SQL Generated for ${dialect.toUpperCase()} migration of ${dsn}\n`;
  ddl += `-- Translated from copybook fields\n\n`;
  ddl += `CREATE TABLE ${tableName} (\n`;

  const columnLines = columns.map((col) => {
    return `  ${col.name.padEnd(25)} ${col.type}`;
  });

  if (primaryKeys.length > 0) {
    columnLines.push(`  PRIMARY KEY (${primaryKeys.join(', ')})`);
  }

  ddl += columnLines.join(',\n');
  ddl += `\n);\n`;

  return ddl;
};

/**
 * Maps COBOL PIC clause structures to standard SQL types.
 */
const mapCobolToSqlType = (field, dialect) => {
  const pic = field.pic ? field.pic.toUpperCase().trim() : '';
  const cType = field.cobol_type ? field.cobol_type.toUpperCase().trim() : 'DISPLAY';

  // Check decimals first, e.g. S9(10)V99 or 9(5)V9(2)
  if (pic.includes('V')) {
    const parts = pic.split('V');
    const integerPart = parts[0].match(/\d+/);
    const decimalPart = parts[1].match(/\d+/);
    
    const m = integerPart ? parseInt(integerPart[0]) : 1;
    const n = decimalPart ? parseInt(decimalPart[0]) : 2;

    return { type: `DECIMAL(${m + n}, ${n})`, category: 'numeric' };
  }

  // Check integers
  if (pic.startsWith('9') || pic.startsWith('S9')) {
    const lenMatch = pic.match(/\d+/);
    const length = lenMatch ? parseInt(lenMatch[0]) : 1;

    if (length <= 4) {
      return { type: dialect === 'mysql' ? 'SMALLINT' : 'SMALLINT', category: 'integer' };
    } else if (length <= 9) {
      return { type: 'INTEGER', category: 'integer' };
    } else {
      return { type: 'BIGINT', category: 'integer' };
    }
  }

  // Check Alphanumerics (PIC X)
  if (pic.startsWith('X')) {
    const lenMatch = pic.match(/\d+/);
    const length = lenMatch ? parseInt(lenMatch[0]) : 255;
    
    return { type: `VARCHAR(${length})`, category: 'string' };
  }

  // Standard fallback
  return { type: 'VARCHAR(255)', category: 'string' };
};

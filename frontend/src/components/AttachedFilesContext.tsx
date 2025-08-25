import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Chip, 
  Collapse, 
  IconButton, 
  Stack, 
  Typography, 
  Tooltip,
  Paper
} from '@mui/material';
import { 
  AttachFile as AttachFileIcon,
  TableChart as ExcelIcon,
  GridOn as SheetsIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
} from '@mui/icons-material';
import { buildApiUrl } from '../config';

interface AttachedFile {
  id: string;
  name: string;
  type: 'excel' | 'google_sheets';
  mime?: string;
  sheets: Array<{
    name: string;
    totalRows: number;
    totalColumns: number;
  }>;
  status: 'loaded' | 'loading' | 'error';
  lastLoaded?: string;
}

interface AttachedFilesContextProps {
  threadId?: string;
  onFileContext?: (files: AttachedFile[]) => void;
}

const AttachedFilesContext: React.FC<AttachedFilesContextProps> = ({ threadId, onFileContext }) => {
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (threadId) {
      fetchAttachedFiles();
    }
  }, [threadId]);

  const fetchAttachedFiles = async () => {
    if (!threadId) return;
    
    setLoading(true);
    try {
      const token = localStorage.getItem('klaris_jwt');
      const tenant = JSON.parse(localStorage.getItem('klaris_tenant') || '{}');
      const tenantId = tenant.tenant_id;
      
      if (!tenantId) return;
      
      // Get active connectors
      const connectorsResp = await fetch(`${buildApiUrl('')}/tenants/${tenantId}/connectors`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (!connectorsResp.ok) return;
      
      const connectorsData = await connectorsResp.json();
      const activeConnectors = connectorsData.connectors?.filter((c: any) => c.status === 'active') || [];
      
      const files: AttachedFile[] = [];
      
      // Get schema for each active connector to find available files
      for (const connector of activeConnectors) {
        if (connector.type !== 'google_drive') continue;
        
        try {
          const schemaResp = await fetch(`${buildApiUrl('')}/tenants/${tenantId}/connectors/${connector.connector_id}/schema`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          
          if (!schemaResp.ok) continue;
          
          const schemaData = await schemaResp.json();
          const entities = schemaData.entities || [];
          
          // Group entities by file
          const fileMap = new Map<string, AttachedFile>();
          
          entities.forEach((entity: any) => {
            if (entity.kind !== 'sheet') return;
            
            const source = entity.source || {};
            const fileId = entity.id.split(':')[0];
            const sheetName = entity.name.split(' / ')[1] || entity.id.split(':')[1];
            
            if (!fileMap.has(fileId)) {
              fileMap.set(fileId, {
                id: fileId,
                name: source.path || 'Unknown File',
                type: source.type === 'excel' ? 'excel' : 'google_sheets',
                mime: source.mime,
                sheets: [],
                status: 'loaded'
              });
            }
            
            const file = fileMap.get(fileId)!;
            file.sheets.push({
              name: sheetName,
              totalRows: source.total_rows || 0,
              totalColumns: source.total_columns || 0
            });
          });
          
          files.push(...Array.from(fileMap.values()));
        } catch (err) {
          console.error('Error fetching schema for connector:', connector.connector_id, err);
        }
      }
      
      setAttachedFiles(files);
      onFileContext?.(files);
      
    } catch (error) {
      console.error('Error fetching attached files:', error);
    } finally {
      setLoading(false);
    }
  };

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'excel':
        return <ExcelIcon fontSize="small" sx={{ color: '#217346' }} />;
      case 'google_sheets':
        return <SheetsIcon fontSize="small" sx={{ color: '#34A853' }} />;
      default:
        return <AttachFileIcon fontSize="small" />;
    }
  };

  if (attachedFiles.length === 0 && !loading) {
    return null;
  }

  return (
    <Paper 
      variant="outlined" 
      sx={{ 
        mb: 2, 
        bgcolor: 'background.default',
        border: '1px solid',
        borderColor: 'divider'
      }}
    >
      <Box sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AttachFileIcon fontSize="small" color="primary" />
            <Typography variant="body2" fontWeight={500} color="primary">
              Attached Files ({attachedFiles.length})
            </Typography>
          </Box>
          <IconButton 
            size="small" 
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>
        
        <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
          {attachedFiles.slice(0, expanded ? undefined : 3).map((file) => (
            <Tooltip 
              key={file.id}
              title={
                <Box>
                  <Typography variant="body2" fontWeight={500}>{file.name}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {file.sheets.length} sheet{file.sheets.length !== 1 ? 's' : ''} • 
                    {file.sheets.reduce((sum, sheet) => sum + sheet.totalRows, 0)} total rows
                  </Typography>
                  <Box sx={{ mt: 0.5 }}>
                    {file.sheets.map((sheet, idx) => (
                      <Typography key={idx} variant="caption" display="block" color="text.secondary">
                        • {sheet.name} ({sheet.totalRows} rows, {sheet.totalColumns} cols)
                      </Typography>
                    ))}
                  </Box>
                </Box>
              }
            >
              <Chip
                icon={getFileIcon(file.type)}
                label={file.name}
                size="small"
                variant="outlined"
                sx={{ 
                  maxWidth: 200,
                  '& .MuiChip-label': {
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                  }
                }}
              />
            </Tooltip>
          ))}
          
          {!expanded && attachedFiles.length > 3 && (
            <Chip
              label={`+${attachedFiles.length - 3} more`}
              size="small"
              variant="outlined"
              onClick={() => setExpanded(true)}
              sx={{ cursor: 'pointer' }}
            />
          )}
        </Stack>
        
        <Collapse in={expanded}>
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">
              These files are loaded in memory and available for analysis. 
              Ask questions about your data and I'll query these files directly.
            </Typography>
          </Box>
        </Collapse>
      </Box>
    </Paper>
  );
};

export default AttachedFilesContext;
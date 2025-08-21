import React, { useState, useCallback } from 'react';
import { Button, Alert, CircularProgress, Box } from '@mui/material';
import { showGoogleDrivePicker, GOOGLE_DRIVE_MIME_TYPES } from '../utils/googlePicker';

interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
  url?: string;
  iconUrl?: string;
  lastEditedUtc?: number;
}

interface GoogleDrivePickerProps {
  /**
   * The OAuth access token for the user's Google Drive
   */
  accessToken: string;
  
  /**
   * Google Developer API key (from environment)
   */
  developerKey: string;
  
  /**
   * Callback when files are selected
   */
  onFilesSelected: (files: GoogleDriveFile[]) => void;
  
  /**
   * Callback when picker is cancelled
   */
  onCancel?: () => void;
  
  /**
   * Button text when no files are selected
   */
  buttonText?: string;
  
  /**
   * Button text when files are already selected
   */
  editButtonText?: string;
  
  /**
   * Whether to allow multiple file selection
   */
  multiselect?: boolean;
  
  /**
   * Whether to show folders in the picker
   */
  includeFolders?: boolean;
  
  /**
   * Array of MIME types to filter by
   */
  mimeTypes?: string[];
  
  /**
   * Custom title for the picker dialog
   */
  pickerTitle?: string;
  
  /**
   * Whether the component is currently disabled/loading
   */
  disabled?: boolean;
  
  /**
   * Current loading state
   */
  loading?: boolean;
  
  /**
   * Array of currently selected file IDs (for display purposes)
   */
  selectedFileIds?: string[];
  
  /**
   * Button variant
   */
  variant?: 'contained' | 'outlined' | 'text';
  
  /**
   * Button color
   */
  color?: 'primary' | 'secondary' | 'success' | 'error' | 'info' | 'warning';
}

const GoogleDrivePicker: React.FC<GoogleDrivePickerProps> = ({
  accessToken,
  developerKey,
  onFilesSelected,
  onCancel,
  buttonText = 'Select Google Drive Files',
  editButtonText = 'Edit Selection',
  multiselect = true,
  includeFolders = false,
  mimeTypes = GOOGLE_DRIVE_MIME_TYPES.ALL_DOCUMENTS,
  pickerTitle = 'Select files from Google Drive',
  disabled = false,
  loading = false,
  selectedFileIds = [],
  variant = 'outlined',
  color = 'primary'
}) => {
  const [isPickerLoading, setIsPickerLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleShowPicker = useCallback(async () => {
    if (!accessToken || !developerKey) {
      setError('Missing access token or developer key');
      return;
    }

    setIsPickerLoading(true);
    setError(null);

    try {
      await showGoogleDrivePicker(
        accessToken,
        developerKey,
        (documents) => {
          const files: GoogleDriveFile[] = documents.map(doc => ({
            id: doc.id,
            name: doc.name,
            mimeType: doc.mimeType,
            url: doc.url,
            iconUrl: doc.iconUrl,
            lastEditedUtc: doc.lastEditedUtc
          }));
          onFilesSelected(files);
        },
        () => {
          if (onCancel) {
            onCancel();
          }
        },
        {
          title: pickerTitle,
          multiselect,
          includeFolders,
          mimeTypes: Array.isArray(mimeTypes) ? mimeTypes : [mimeTypes]
        }
      );
    } catch (err: any) {
      console.error('Google Drive Picker error:', err);
      setError(err.message || 'Failed to load Google Drive Picker');
    } finally {
      setIsPickerLoading(false);
    }
  }, [
    accessToken,
    developerKey,
    onFilesSelected,
    onCancel,
    pickerTitle,
    multiselect,
    includeFolders,
    mimeTypes
  ]);

  const isLoading = loading || isPickerLoading;
  const hasSelectedFiles = selectedFileIds && selectedFileIds.length > 0;
  const displayText = hasSelectedFiles ? editButtonText : buttonText;

  return (
    <Box>
      <Button
        variant={variant}
        color={color}
        onClick={handleShowPicker}
        disabled={disabled || isLoading}
        startIcon={isLoading ? <CircularProgress size={16} /> : undefined}
      >
        {isLoading ? 'Loading...' : displayText}
      </Button>
      
      {error && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
};

export default GoogleDrivePicker;

// Export types for use in other components
export type { GoogleDriveFile, GoogleDrivePickerProps };

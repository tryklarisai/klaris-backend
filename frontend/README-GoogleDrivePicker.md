# Google Drive Picker Integration

This project now includes the official Google Drive Picker API integration, which provides a native Google Drive file selection experience instead of the previous modal-based file list.

## Features

- **Native Google Drive Interface**: Uses the official Google Drive Picker that users are familiar with
- **Folder Navigation**: Browse your Google Drive folder structure naturally
- **File-Only Selection**: Navigate through folders but only select files (folders are not selectable)
- **Real-time File Access**: Browse and select files directly from Google Drive
- **File Type Filtering**: Automatically filters to show only supported document types
- **Multi-selection Support**: Select multiple files at once
- **Seamless Integration**: Maintains the same workflow as before but with better UX

## Setup Requirements

### 1. Google Cloud Console Configuration

You need to set up a Google Cloud Project and enable the necessary APIs:

1. **Go to Google Cloud Console** (https://console.cloud.google.com/)
2. **Create or select a project**
3. **Enable the following APIs**:
   - Google Drive API
   - Google Picker API

4. **Create API Credentials**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "API Key"
   - Copy the API key (this will be your `REACT_APP_GOOGLE_API_KEY`)
   - Optionally, restrict the API key to specific APIs and domains for security

5. **OAuth 2.0 Client ID** (if not already configured):
   - Create or use existing OAuth 2.0 Client ID
   - Make sure your domain is added to authorized JavaScript origins
   - Copy the Client ID (this will be your `REACT_APP_GOOGLE_CLIENT_ID`)

### 2. Environment Configuration

Add the following environment variable to your `.env.development` file:

```bash
# Google API configuration for Google Drive Picker
REACT_APP_GOOGLE_API_KEY=your_google_api_key_here
```

**Important Notes:**
- The `REACT_APP_GOOGLE_API_KEY` is used for the Google Picker API
- The OAuth Client ID is only used in your backend OAuth flow, not in the frontend
- The API key is a public client-side credential, so it will be visible in the browser

### 3. Domain Authorization

Make sure your domain (both development and production) is authorized in your Google Cloud Console:

1. Go to "APIs & Services" > "Credentials"
2. Edit your OAuth 2.0 Client ID
3. Add your domains to "Authorized JavaScript origins":
   - `http://localhost:3000` (for development)
   - `https://yourdomain.com` (for production)

## How It Works

### Fallback Behavior

The implementation includes intelligent fallback behavior:

- **When Google API key is configured**: Shows the native Google Drive Picker
- **When Google API key is missing**: Falls back to the original modal-based file selection
- **When access token is unavailable**: Shows appropriate error messages

### File Selection Flow

1. User clicks "Select Google Drive Files" button
2. Google Drive Picker opens in a popup/overlay
3. User browses and selects files from their Google Drive
4. Selected files are automatically saved to the connector
5. The UI updates to show selected files
6. User can proceed to schema generation

### Supported File Types

The picker is configured to show only supported document types:

- Google Workspace files (Sheets, Docs, Slides)
- Microsoft Office files (Excel, Word, PowerPoint)
- PDF files
- CSV and text files

## Security Considerations

1. **API Key Restrictions**: Restrict your Google API key to specific APIs and domains
2. **CORS Configuration**: Ensure your domains are properly configured in Google Cloud Console
3. **Token Handling**: Access tokens are handled securely and not logged
4. **Error Handling**: Comprehensive error handling prevents token leakage

## Troubleshooting

### Common Issues

1. **"Missing access token or developer key" error**:
   - Check that `REACT_APP_GOOGLE_API_KEY` is set correctly
   - Verify the Google Drive connector has a valid OAuth access token

2. **Picker fails to load**:
   - Check browser console for CORS errors
   - Verify your domain is authorized in Google Cloud Console
   - Ensure Google Drive API and Picker API are enabled

3. **Files don't appear in picker**:
   - Check that the user has files in their Google Drive
   - Verify the access token has appropriate scopes
   - Ensure the user has granted necessary permissions

4. **Fallback to modal appears**:
   - This happens when Google API key is not configured
   - Set `REACT_APP_GOOGLE_API_KEY` in your environment variables

### Debug Mode

Enable debug logging by opening browser console when using the picker. Error messages will help identify configuration issues.

## Implementation Details

### Components

- **`GoogleDrivePicker`**: Main React component for the picker
- **`googlePicker.ts`**: Utility functions for loading and managing the Google Picker API
- **Configuration**: Environment-based configuration in `config.ts`

### API Integration

The picker integrates with existing backend endpoints:
- Uses the same connector PATCH endpoint for saving selections
- Maintains compatibility with existing schema generation flow
- Preserves all existing functionality while enhancing UX

## Migration Notes

If you're upgrading from the modal-based selection:

1. **No breaking changes**: Existing functionality is preserved
2. **Gradual rollout**: Set environment variables when ready to enable the new picker
3. **Fallback support**: Users without proper configuration will see the original interface
4. **Same data flow**: Backend integration remains unchanged

## Browser Support

The Google Drive Picker supports:
- Chrome (recommended)
- Firefox
- Safari
- Edge

Note: Some features may have limited support in older browsers.

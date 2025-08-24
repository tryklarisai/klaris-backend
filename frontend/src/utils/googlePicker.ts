/**
 * Google Drive Picker API utilities
 * Handles loading the Google Picker API and provides helper functions
 */

// Global declarations for Google Picker
declare global {
  interface Window {
    google: {
      picker: {
        api: {
          load: (callback: () => void) => void;
        };
        PickerBuilder: new () => GooglePickerBuilder;
        DocsView: new (viewId: string) => GoogleDocsView;
        ViewId: {
          DOCS: string;
          FOLDERS: string;
          SPREADSHEETS: string;
          PRESENTATIONS: string;
          DOCS_IMAGES_AND_VIDEOS: string;
          DOCS_VIDEOS: string;
          DOCS_IMAGES: string;
          PDFS: string;
        };
        Action: {
          PICKED: string;
          CANCEL: string;
        };
        Feature: {
          MULTISELECT_ENABLED: number;
        };
        Document: {
          ID: string;
          NAME: string;
          URL: string;
          MIME_TYPE: string;
          LAST_EDITED_UTC: string;
          ICON_URL: string;
          DESCRIPTION: string;
          AUDIENCE: string;
          AUDIENCE_CAN_VIEW: string;
          AUDIENCE_CAN_COMMENT: string;
          AUDIENCE_CAN_EDIT: string;
        };
        Response: {
          ACTION: string;
          DOCUMENTS: string;
        };
      };
    };
    gapi: {
      load: (api: string, callback: () => void) => void;
      auth2: {
        getAuthInstance: () => any;
      };
    };
  }
}

interface GooglePickerBuilder {
  addView(view: GoogleDocsView | string): GooglePickerBuilder;
  setOAuthToken(token: string): GooglePickerBuilder;
  setDeveloperKey(key: string): GooglePickerBuilder;
  setCallback(callback: (data: any) => void): GooglePickerBuilder;
  setOrigin(origin: string): GooglePickerBuilder;
  setSize(width: number, height: number): GooglePickerBuilder;
  setTitle(title: string): GooglePickerBuilder;
  enableFeature(feature: number): GooglePickerBuilder;
  setSelectableMimeTypes(mimeTypes: string): GooglePickerBuilder;
  build(): GooglePicker;
}

interface GoogleDocsView {
  setIncludeFolders(includeFolders: boolean): GoogleDocsView;
  setSelectFolderEnabled(enabled: boolean): GoogleDocsView;
  setParent(parentId: string): GoogleDocsView;
  setOwnedByMe(ownedByMe: boolean): GoogleDocsView;
}

interface GooglePicker {
  setVisible(visible: boolean): void;
}

interface PickerDocument {
  id: string;
  name: string;
  url: string;
  mimeType: string;
  lastEditedUtc: number;
  iconUrl: string;
  description?: string;
}

interface PickerResponse {
  action: string;
  docs?: PickerDocument[];
}

let isPickerApiLoaded = false;
let isPickerApiLoading = false;
let pickerApiLoadPromise: Promise<void> | null = null;

/**
 * Load the Google Picker API
 */
export const loadPickerApi = (): Promise<void> => {
  if (isPickerApiLoaded) {
    return Promise.resolve();
  }

  if (pickerApiLoadPromise) {
    return pickerApiLoadPromise;
  }

  pickerApiLoadPromise = new Promise((resolve, reject) => {
    if (isPickerApiLoading) return;
    isPickerApiLoading = true;

    // Load the Google API script first
    if (!window.gapi) {
      const script = document.createElement('script');
      script.src = 'https://apis.google.com/js/api.js';
      script.onload = () => {
        window.gapi.load('picker', () => {
          isPickerApiLoaded = true;
          isPickerApiLoading = false;
          resolve();
        });
      };
      script.onerror = () => {
        isPickerApiLoading = false;
        reject(new Error('Failed to load Google APIs script'));
      };
      document.head.appendChild(script);
    } else {
      window.gapi.load('picker', () => {
        isPickerApiLoaded = true;
        isPickerApiLoading = false;
        resolve();
      });
    }
  });

  return pickerApiLoadPromise;
};

/**
 * Create and show Google Drive Picker
 */
export const showGoogleDrivePicker = (
  accessToken: string,
  developerKey: string,
  onPicked: (documents: PickerDocument[]) => void,
  onCancel: () => void,
  options: {
    title?: string;
    multiselect?: boolean;
    includeFolders?: boolean;
    mimeTypes?: string[];
  } = {}
): Promise<void> => {
  return loadPickerApi().then(() => {
    const picker = new window.google.picker.PickerBuilder();

    // Create a docs view that shows folder navigation but prevents folder selection
    const docsView = new window.google.picker.DocsView(window.google.picker.ViewId.DOCS);
    
    // Enable folder navigation
    docsView.setIncludeFolders(true);
    
    // Set selectability to files only (not folders)
    docsView.setSelectFolderEnabled(false);
    
    // Add the configured docs view
    picker.addView(docsView);
    
    // Set OAuth token and developer key
    picker.setOAuthToken(accessToken);
    picker.setDeveloperKey(developerKey);

    // Set title
    picker.setTitle(options.title || 'Select files from Google Drive');

    // Set size for better UX - larger size makes cancel button more visible
    picker.setSize(1051, 650);

    // Set origin to current domain
    picker.setOrigin(window.location.origin);

    // Configure picker for better UX
    // The Google Picker should have a built-in cancel/close button (X) in the top-right corner
    // Users can also press Escape key to cancel

    // Filter by MIME types if specified
    if (options.mimeTypes && options.mimeTypes.length > 0) {
      picker.setSelectableMimeTypes(options.mimeTypes.join(','));
    }

    // Set callback
    picker.setCallback((data: any) => {
      if (data[window.google.picker.Response.ACTION] === window.google.picker.Action.PICKED) {
        const docs = data[window.google.picker.Response.DOCUMENTS] || [];
        
        // Filter out folders - only allow files
        const fileDocsOnly = docs.filter((doc: any) => {
          const mimeType = doc[window.google.picker.Document.MIME_TYPE];
          return mimeType !== 'application/vnd.google-apps.folder';
        });
        
        if (fileDocsOnly.length === 0) {
          console.warn('Only folders were selected, but folders are not allowed');
          return; // Don't call onPicked if only folders were selected
        }
        
        const processedDocs: PickerDocument[] = fileDocsOnly.map((doc: any) => ({
          id: doc[window.google.picker.Document.ID],
          name: doc[window.google.picker.Document.NAME],
          url: doc[window.google.picker.Document.URL],
          mimeType: doc[window.google.picker.Document.MIME_TYPE],
          lastEditedUtc: doc[window.google.picker.Document.LAST_EDITED_UTC],
          iconUrl: doc[window.google.picker.Document.ICON_URL],
          description: doc[window.google.picker.Document.DESCRIPTION]
        }));
        onPicked(processedDocs);
      } else if (data[window.google.picker.Response.ACTION] === window.google.picker.Action.CANCEL) {
        onCancel();
      }
    });

    // Always enable multiselect if requested, with robust fallback
    if (options.multiselect) {
      let multiselectEnabled = false;
      try {
        picker.enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED);
        multiselectEnabled = true;
      } catch (error) {
        console.warn('MULTISELECT_ENABLED feature not available via enum:', error);
      }
      if (!multiselectEnabled) {
        try {
          picker.enableFeature(1); // Fallback: 1 is the documented constant for multiselect
          multiselectEnabled = true;
        } catch (fallbackError) {
          console.warn('Multiselect fallback also failed:', fallbackError);
        }
      }
      if (!multiselectEnabled) {
        console.warn('Google Picker multiselect could not be enabled. Only single file selection may be available.');
      }
    }

    // Build and show picker
    const pickerInstance = picker.build();
    pickerInstance.setVisible(true);
  });
};

/**
 * Common MIME types for filtering
 */
export const GOOGLE_DRIVE_MIME_TYPES = {
  // Google Workspace files
  GOOGLE_SHEETS: 'application/vnd.google-apps.spreadsheet',
  GOOGLE_DOCS: 'application/vnd.google-apps.document',
  GOOGLE_SLIDES: 'application/vnd.google-apps.presentation',
  GOOGLE_FORMS: 'application/vnd.google-apps.form',
  
  // Microsoft Office files
  EXCEL: 'application/vnd.ms-excel',
  EXCEL_XLSX: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  WORD: 'application/msword',
  WORD_DOCX: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  POWERPOINT: 'application/vnd.ms-powerpoint',
  POWERPOINT_PPTX: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  
  // Other common formats
  PDF: 'application/pdf',
  CSV: 'text/csv',
  TEXT: 'text/plain',
  JSON: 'application/json',
  
  // Images
  PNG: 'image/png',
  JPEG: 'image/jpeg',
  GIF: 'image/gif',
  
  // All documents (for filtering)
  ALL_DOCUMENTS: [
    'application/vnd.google-apps.spreadsheet',
    'application/vnd.google-apps.document',
    'application/vnd.google-apps.presentation',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/pdf',
    'text/csv',
    'text/plain'
  ]
};

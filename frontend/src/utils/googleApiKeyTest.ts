/**
 * Google API Key validation utility
 * Tests if the Google API key is valid and has proper permissions
 */

export const testGoogleApiKey = async (apiKey: string): Promise<{ valid: boolean; error?: string }> => {
  if (!apiKey) {
    return { valid: false, error: 'No API key provided' };
  }

  try {
    // Test the API key by making a simple request to the Google API Discovery service
    // This endpoint requires an API key but doesn't need OAuth
    const response = await fetch(
      `https://www.googleapis.com/discovery/v1/apis/drive/v3/rest?key=${apiKey}`,
      {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      }
    );

    if (response.ok) {
      return { valid: true };
    } else if (response.status === 403) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.error?.message || 'API key forbidden';
      return { 
        valid: false, 
        error: `API key forbidden (403): ${errorMessage}. Check if Google Drive API and Picker API are enabled, and verify domain restrictions.` 
      };
    } else if (response.status === 400) {
      return { 
        valid: false, 
        error: 'Invalid API key format or API key not found' 
      };
    } else {
      return { 
        valid: false, 
        error: `API key validation failed with status ${response.status}` 
      };
    }
  } catch (error) {
    return { 
      valid: false, 
      error: `Network error testing API key: ${error instanceof Error ? error.message : 'Unknown error'}` 
    };
  }
};

export const logGoogleApiKeyDebugInfo = (apiKey?: string) => {
  console.log('=== Google API Key Debug Info ===');
  console.log('API Key configured:', !!apiKey);
  console.log('API Key length:', apiKey?.length || 0);
  console.log('API Key prefix:', apiKey?.substring(0, 10) + '...' || 'N/A');
  console.log('Current domain:', window.location.origin);
  console.log('==================================');
};
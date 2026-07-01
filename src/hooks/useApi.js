import { useAppStore } from '../store/appStore';

export const useApi = () => {
  const { settings } = useAppStore();

  const request = async (endpoint, options = {}) => {
    const url = `${settings.apiBaseUrl}${endpoint}`;
    
    // Set headers
    const headers = options.isMultipart 
      ? {} 
      : { 'Content-Type': 'application/json', ...(options.headers || {}) };

    const config = {
      ...options,
      headers,
    };

    if (config.isMultipart) {
      delete config.isMultipart;
    }

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Request failed with status ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`API Error on ${endpoint}:`, error);
      throw error;
    }
  };

  return {
    get: (endpoint, options = {}) => request(endpoint, { ...options, method: 'GET' }),
    post: (endpoint, body, options = {}) => {
      const isMultipart = body instanceof FormData;
      return request(endpoint, {
        ...options,
        method: 'POST',
        body: isMultipart ? body : JSON.stringify(body),
        isMultipart,
      });
    },
    delete: (endpoint, options = {}) => request(endpoint, { ...options, method: 'DELETE' }),
  };
};

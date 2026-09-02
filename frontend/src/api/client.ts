// API Client Configuration
// Allows switching between synthetic mock services and live FastAPI endpoints
export const API_BASE_URL = import.meta.env.VITE_API_URL || '';
export const IS_MOCK_MODE = !API_BASE_URL;

export async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  if (IS_MOCK_MODE) {
    throw new Error(`Mock mode active: Direct fetch called for ${endpoint}`);
  }
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { NotificationProvider } from './context/NotificationContext.jsx'
import { ErrorLogProvider } from './context/ErrorLogContext.jsx'
import './index.css'

// Global fetch interceptor to inject JWT authorization token for secured routes
const originalFetch = window.fetch;
window.fetch = async function (url, options = {}) {
  const token = localStorage.getItem('orbitavanya_token');
  const strUrl = String(url);
  const apiBase = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5050';
  
  const isApiRoute =
    strUrl.startsWith('/api/') ||
    strUrl.startsWith(apiBase) ||
    strUrl.startsWith('http://127.0.0.1:5050') ||
    strUrl.startsWith('http://localhost:5050');

  if (token && isApiRoute) {
    const newOptions = { ...options };
    if (newOptions.headers instanceof Headers) {
      const headers = new Headers(newOptions.headers);
      if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      newOptions.headers = headers;
    } else if (Array.isArray(newOptions.headers)) {
      const headers = [...newOptions.headers];
      const hasAuth = headers.some(([k]) => k.toLowerCase() === 'authorization');
      if (!hasAuth) {
        headers.push(['Authorization', `Bearer ${token}`]);
      }
      newOptions.headers = headers;
    } else {
      const headers = { ...(newOptions.headers || {}) };
      const hasAuth = Object.keys(headers).some(k => k.toLowerCase() === 'authorization');
      if (!hasAuth) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      newOptions.headers = headers;
    }
    return originalFetch(url, newOptions);
  }
  return originalFetch(url, options);
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <NotificationProvider>
          <ErrorLogProvider>
            <App />
          </ErrorLogProvider>
        </NotificationProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

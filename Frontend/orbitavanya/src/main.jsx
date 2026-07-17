import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { NotificationProvider } from './context/NotificationContext.jsx'
import './index.css'

// Global fetch interceptor to inject JWT authorization token for secured routes
const originalFetch = window.fetch;
window.fetch = async function (url, options = {}) {
  const token = localStorage.getItem('orbitavanya_token');
  // Check if target is backend API
  const strUrl = String(url);
  if (token && (strUrl.startsWith('http://localhost:5050') || strUrl.startsWith('/api/'))) {
    options.headers = options.headers || {};
    if (options.headers instanceof Headers) {
      if (!options.headers.has('Authorization')) {
        options.headers.set('Authorization', `Bearer ${token}`);
      }
    } else if (Array.isArray(options.headers)) {
      const hasAuth = options.headers.some(([k]) => k.toLowerCase() === 'authorization');
      if (!hasAuth) {
        options.headers.push(['Authorization', `Bearer ${token}`]);
      }
    } else {
      const hasAuth = Object.keys(options.headers).some(k => k.toLowerCase() === 'authorization');
      if (!hasAuth) {
        options.headers = {
          ...options.headers,
          'Authorization': `Bearer ${token}`,
        };
      }
    }
  }
  return originalFetch(url, options);
};

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <NotificationProvider>
          <App />
        </NotificationProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

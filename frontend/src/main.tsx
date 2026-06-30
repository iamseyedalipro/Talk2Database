import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { configureClient } from './api/client';
import { useAuthStore } from './store/auth';
import { initTheme } from './store/theme';
import './styles.css';

// Apply the resolved theme before the first paint to avoid a flash.
initTheme();

// Wire the API client to the auth store so it can read the token and react to
// 401 responses by clearing auth (the route guards then redirect to /login).
configureClient({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: () => useAuthStore.getState().clear(),
});

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Root element #root not found');
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

import { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../lib/api.jsx';

const AuthContext = createContext(null);
const TOKEN_KEY = 'orbitavanya_token';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(({ user }) => setUser(user))
      .catch((err) => {
        if (err.message && err.message.includes('401')) {
          setUser(null);
        } else {
          console.warn('Could not verify session, will retry on next action:', err.message);
          const currentToken = localStorage.getItem('orbitavanya_token');
          if (!currentToken) setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function completeAuth(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    setUser(user);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }

  function updateUser(patch) {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev));
  }

  return (
    <AuthContext.Provider value={{ user, loading, completeAuth, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

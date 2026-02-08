'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as authService from '@/services/auth';
import type { User } from '@/types/auth';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  isAuthenticated: boolean;
  isResearcher: boolean;
  isDeveloper: boolean;
  isAdmin: boolean;
  isSuperAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      if (authService.isAuthenticated()) {
        try {
          const userData = await authService.getProfile();
          setUser(userData);
        } catch {
          // Token expired or invalid
          authService.logout();
        }
      }
      setLoading(false);
    };

    checkAuth();
  }, []);

  const login = useCallback(async (identifier: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const response = await authService.login({ identifier, password });
      setUser(response.user);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al iniciar sesión';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (username: string, email: string, password: string) => {
    setError(null);
    setLoading(true);
    try {
      const response = await authService.register({ username, email, password });
      setUser(response.user);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al registrarse';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    authService.logout();
    setUser(null);
    setError(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Role checks
  const roleType = user?.role?.type?.toLowerCase() || '';
  const isAuthenticated = !!user;
  const isResearcher = ['researcher', 'developer', 'admin', 'superadmin'].includes(roleType);
  const isDeveloper = ['developer', 'admin', 'superadmin'].includes(roleType);
  const isAdmin = ['admin', 'superadmin'].includes(roleType);
  const isSuperAdmin = roleType === 'superadmin';

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
        register,
        logout,
        clearError,
        isAuthenticated,
        isResearcher,
        isDeveloper,
        isAdmin,
        isSuperAdmin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  // Return a safe default if no provider (e.g., during static generation)
  if (!context) {
    return {
      user: null,
      token: null,
      loading: true,
      error: null,
      login: async () => {},
      register: async () => {},
      logout: () => {},
      clearError: () => {},
      isAuthenticated: false,
      isResearcher: false,
      isDeveloper: false,
      isAdmin: false,
      isSuperAdmin: false,
    };
  }
  return context;
}

// HOC for protected routes
export function withAuth<P extends object>(
  Component: React.ComponentType<P>,
  options?: { requiredRole?: 'researcher' | 'admin' | 'superadmin' }
) {
  return function AuthenticatedComponent(props: P) {
    const { user, loading, isAdmin, isSuperAdmin, isResearcher } = useAuth();

    if (loading) {
      return (
        <div className="flex items-center justify-center min-h-screen">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      );
    }

    if (!user) {
      // Redirect to login
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      return null;
    }

    // Check role requirements
    if (options?.requiredRole) {
      const hasRole =
        options.requiredRole === 'superadmin' ? isSuperAdmin :
        options.requiredRole === 'admin' ? isAdmin :
        isResearcher;

      if (!hasRole) {
        return (
          <div className="flex items-center justify-center min-h-screen">
            <div className="text-center">
              <h1 className="text-2xl font-bold text-red-600">Acceso Denegado</h1>
              <p className="mt-2 text-gray-600">No tienes permisos para acceder a esta página.</p>
            </div>
          </div>
        );
      }
    }

    return <Component {...props} />;
  };
}

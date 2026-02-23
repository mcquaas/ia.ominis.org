'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { getGoogleAuthUrl, getToken } from '@/services/auth';
import Link from 'next/link';

interface LoginFormProps {
  onSuccess?: () => void;
  redirectTo?: string;
}

export function LoginForm({ onSuccess, redirectTo = '/' }: LoginFormProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login, error, clearError } = useAuth();

  // If already logged in and we have an OIDC return URL, redirect immediately (no form)
  useEffect(() => {
    const target = redirectTo ?? '/';
    if (!target || !target.includes('/oidc/authorize')) return;
    const token = getToken();
    if (!token) return;
    const sep = target.includes('?') ? '&' : '?';
    window.location.replace(target + sep + 'token=' + encodeURIComponent(token));
  }, [redirectTo]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setIsLoading(true);

    try {
      await login(identifier, password);
      if (onSuccess) {
        onSuccess();
      } else if (typeof window !== 'undefined') {
        let target = redirectTo ?? '/';
        // If redirecting back to OIDC authorize (e.g. LibreChat), append JWT so backend can issue code
        if (target && target.includes('/oidc/authorize')) {
          const token = getToken();
          if (token) {
            const sep = target.includes('?') ? '&' : '?';
            target = `${target}${sep}token=${encodeURIComponent(token)}`;
          }
        }
        window.location.href = target;
      }
    } catch {
      // Error is handled by useAuth
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <form onSubmit={handleSubmit} className="glass rounded-2xl px-8 pt-8 pb-8">
        <h2 className="text-2xl font-bold text-center text-white mb-6">
          Iniciar Sesión
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="mb-4">
          <label 
            htmlFor="identifier" 
            className="block text-gray-300 text-sm font-medium mb-2"
          >
            Email o Usuario
          </label>
          <input
            id="identifier"
            type="text"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            required
            autoComplete="username"
            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
            placeholder="tu@email.com"
          />
        </div>

        <div className="mb-6">
          <label 
            htmlFor="password" 
            className="block text-gray-300 text-sm font-medium mb-2"
          >
            Contraseña
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
            placeholder="••••••••"
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full bg-accent hover:bg-accent-light text-white font-medium py-3 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {isLoading ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Ingresando...
            </span>
          ) : (
            'Ingresar'
          )}
        </button>

        <div className="mt-4 flex items-center gap-4">
          <div className="flex-1 h-px bg-white/10" />
          <span className="text-gray-500 text-xs">o</span>
          <div className="flex-1 h-px bg-white/10" />
        </div>

        <a
          href={getGoogleAuthUrl()}
          className="mt-4 flex items-center justify-center gap-2 w-full py-3 px-4 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-all border border-white/10"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Continuar con Google
        </a>

        <div className="mt-4 text-center">
          <Link 
            href="/forgot-password" 
            className="text-sm text-accent-light hover:text-white transition-colors"
          >
            ¿Olvidaste tu contraseña?
          </Link>
        </div>

        <div className="mt-6 text-center border-t border-white/10 pt-4">
          <p className="text-sm text-gray-400">
            ¿No tienes cuenta?{' '}
            <Link 
              href="/register" 
              className="text-accent-light hover:text-white font-medium transition-colors"
            >
              Regístrate
            </Link>
          </p>
        </div>
      </form>
    </div>
  );
}

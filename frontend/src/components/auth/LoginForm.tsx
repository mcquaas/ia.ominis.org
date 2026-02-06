'use client';

import { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setIsLoading(true);

    try {
      await login(identifier, password);
      if (onSuccess) {
        onSuccess();
      } else if (typeof window !== 'undefined') {
        window.location.href = redirectTo;
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

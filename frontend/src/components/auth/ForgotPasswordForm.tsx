'use client';

import { useState } from 'react';
import { forgotPassword } from '@/services/auth';
import Link from 'next/link';

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await forgotPassword(email);
      setSuccess(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al enviar el correo';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="w-full max-w-md mx-auto">
        <div className="glass rounded-2xl px-8 pt-8 pb-8 text-center">
          <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">
            Correo Enviado
          </h2>
          <p className="text-gray-400 mb-6">
            Hemos enviado un enlace de recuperación a <span className="text-white">{email}</span>. 
            Revisa tu bandeja de entrada y sigue las instrucciones.
          </p>
          <p className="text-gray-500 text-sm mb-6">
            ¿No recibiste el correo? Revisa tu carpeta de spam o intenta de nuevo.
          </p>
          <div className="flex flex-col gap-3">
            <button
              onClick={() => setSuccess(false)}
              className="w-full bg-white/10 hover:bg-white/20 text-white font-medium py-3 px-4 rounded-lg transition-all"
            >
              Enviar de nuevo
            </button>
            <Link 
              href="/login"
              className="text-accent-light hover:text-white transition-colors text-sm"
            >
              Volver a Iniciar Sesión
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md mx-auto">
      <form onSubmit={handleSubmit} className="glass rounded-2xl px-8 pt-8 pb-8">
        <div className="w-16 h-16 bg-accent/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-accent-light" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-center text-white mb-6">
          Recuperar Contraseña
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="mb-6">
          <label 
            htmlFor="email" 
            className="block text-gray-300 text-sm font-medium mb-2"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
            placeholder="tu@email.com"
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
              Enviando...
            </span>
          ) : (
            'Enviar Enlace de Recuperación'
          )}
        </button>

        <div className="mt-6 text-center border-t border-white/10 pt-4">
          <p className="text-sm text-gray-400">
            ¿Recordaste tu contraseña?{' '}
            <Link 
              href="/login" 
              className="text-accent-light hover:text-white font-medium transition-colors"
            >
              Inicia Sesión
            </Link>
          </p>
        </div>
      </form>
    </div>
  );
}

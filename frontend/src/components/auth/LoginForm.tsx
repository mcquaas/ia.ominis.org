'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { getToken } from '@/services/auth';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

interface LoginFormProps {
  onSuccess?: () => void;
  redirectTo?: string;
}

export function LoginForm({ onSuccess, redirectTo = '/' }: LoginFormProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { login, error, clearError } = useAuth();
  const searchParams = useSearchParams();
  const [urlError, setUrlError] = useState<string | null>(null);

  const ciasSsoUrl = `/api/connect/cias`;
  const googleAuthUrl = `/api/connect/google`;
  const didactivaAuthUrl = `/api/connect/didactiva`;

  // Parse error from URL params (e.g. from OAuth redirect failure)
  useEffect(() => {
    const errParam = searchParams.get('error');
    if (errParam) {
      if (errParam === 'cias_member_required') {
        setUrlError('Acceso restringido: Tu cuenta no cuenta con una membresía activa y verificada en la Red CIAS.');
      } else if (errParam === 'google_denied' || errParam === 'cias_denied') {
        setUrlError('Se canceló el inicio de sesión.');
      } else if (errParam === 'didactiva_denied') {
        setUrlError('Se canceló el inicio de sesión con Didactiva.');
      } else if (errParam === 'account_blocked') {
        setUrlError('Tu cuenta se encuentra desactivada.');
      } else {
        setUrlError('No fue posible completar la autenticación con el proveedor.');
      }
    }
  }, [searchParams]);

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
    setUrlError(null);
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
      // Error is handled by useAuth state
    } finally {
      setIsLoading(false);
    }
  };

  const activeError = error || urlError;
  const isMemberError = activeError && (
    activeError.toLowerCase().includes('miembro') ||
    activeError.toLowerCase().includes('membresía') ||
    activeError.toLowerCase().includes('restringido') ||
    activeError.toLowerCase().includes('cias')
  );

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="glass rounded-2xl px-8 pt-8 pb-8 border border-white/10 shadow-2xl backdrop-blur-xl">
        {/* CIAS & OMINIS Badge */}
        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-teal-500/15 text-teal-300 border border-teal-500/30">
            <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
            Acceso Exclusivo Miembros CIAS
          </span>
        </div>

        <h2 className="text-2xl font-bold text-center text-white mb-2">
          Iniciar Sesión
        </h2>
        <p className="text-xs text-center text-gray-400 mb-6 leading-relaxed">
          Autentícate con tu cuenta de la <strong className="text-teal-300">Red CIAS</strong> (Google, Didactiva, LinkedIn o correo) para acceder a OMINIS.
        </p>

        {activeError && (
          <div className={`mb-5 p-4 rounded-xl border ${
            isMemberError
              ? 'bg-amber-500/10 border-amber-500/40 text-amber-200'
              : 'bg-red-500/10 border-red-500/30 text-red-300'
          }`}>
            <p className="text-xs leading-relaxed font-medium">{activeError}</p>
            {isMemberError && (
              <div className="mt-3 pt-3 border-t border-amber-500/20 flex flex-col gap-2">
                <a
                  href="https://www.cias.ai/auth"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 px-3 py-2 rounded-lg transition-colors"
                >
                  Ir a cias.ai para solicitar o activar membresía →
                </a>
              </div>
            )}
          </div>
        )}

        {/* Primary SSO Button */}
        <div className="space-y-3 mb-6">
          <a
            href={ciasSsoUrl}
            className="w-full flex items-center justify-center gap-2.5 py-3.5 px-4 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold text-sm rounded-xl transition-all shadow-lg shadow-teal-500/25 group"
          >
            <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
            </svg>
            <span>Entrar con cuenta Red CIAS (SSO)</span>
          </a>

          {/* Secondary Quick OAuth Buttons */}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <a
              href={googleAuthUrl}
              className="flex items-center justify-center gap-2 py-2.5 px-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-lg text-white font-medium text-xs transition-all"
            >
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                <path
                  fill="#EA4335"
                  d="M12 5c1.6 0 3 .6 4.1 1.7l3.1-3.1C17.3 1.8 14.8 1 12 1 7.5 1 3.7 3.6 1.9 7.3l3.7 2.9C6.5 7.3 9 5 12 5z"
                />
                <path
                  fill="#4285F4"
                  d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.7l3.7 2.9c2.2-2 3.7-5 3.7-8.8z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.6 14.8c-.2-.7-.4-1.5-.4-2.3s.2-1.6.4-2.3L1.9 7.3C.7 9.7 0 12.3 0 15s.7 5.3 1.9 7.7l3.7-2.9z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3 0-5.5-2.3-6.4-5.2L1.9 16C3.7 19.7 7.5 23 12 23z"
                />
              </svg>
              <span>Google</span>
            </a>

            <a
              href={didactivaAuthUrl}
              className="flex items-center justify-center gap-2 py-2.5 px-3 bg-teal-500/10 hover:bg-teal-500/20 border border-teal-500/20 hover:border-teal-500/40 rounded-lg text-teal-200 font-medium text-xs transition-all"
            >
              <svg className="w-4 h-4 shrink-0 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 14l9-5-9-5-9 5 9 5z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
              </svg>
              <span>Didactiva</span>
            </a>
          </div>
        </div>

        <div className="relative flex py-2 items-center mb-5">
          <div className="flex-grow border-t border-white/10" />
          <span className="flex-shrink mx-3 text-[11px] uppercase tracking-wider text-gray-400">
            o con credenciales CIAS
          </span>
          <div className="flex-grow border-t border-white/10" />
        </div>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label 
              htmlFor="identifier" 
              className="block text-gray-300 text-xs font-semibold uppercase tracking-wider mb-2"
            >
              Correo Electrónico en CIAS
            </label>
            <input
              id="identifier"
              type="email"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoComplete="email"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent transition-all text-sm"
              placeholder="tu-correo@ejemplo.com"
            />
          </div>

          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <label 
                htmlFor="password" 
                className="block text-gray-300 text-xs font-semibold uppercase tracking-wider"
              >
                Contraseña
              </label>
              <a
                href="https://www.cias.ai/auth"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-teal-400 hover:text-teal-300 transition-colors"
              >
                ¿Olvidaste tu contraseña?
              </a>
            </div>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full pl-4 pr-12 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent transition-all text-sm"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-md text-gray-400 hover:text-white focus:outline-none focus:ring-2 focus:ring-teal-400 transition-colors"
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                aria-pressed={showPassword}
              >
                {showPassword ? (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75} aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75} aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-white/10 hover:bg-white/15 text-white font-semibold py-3 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-400 focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed transition-all border border-white/10"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Validando membresía...
              </span>
            ) : (
              'Entrar con correo y contraseña'
            )}
          </button>
        </form>

        <div className="mt-6 text-center border-t border-white/10 pt-5">
          <p className="text-xs text-gray-400 leading-relaxed">
            ¿Aún no eres miembro de la Red CIAS?{' '}
            <a 
              href="https://www.cias.ai/auth" 
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-300 hover:text-white font-medium transition-colors underline-offset-2 hover:underline block mt-1"
            >
              Únete en cias.ai →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

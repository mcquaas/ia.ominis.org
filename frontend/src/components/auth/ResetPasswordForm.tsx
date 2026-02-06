'use client';

import { useState } from 'react';
import { resetPassword } from '@/services/auth';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

export function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const code = searchParams.get('code') || '';
  
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validate code
    if (!code) {
      setError('Enlace de recuperación inválido. Por favor, solicita un nuevo enlace.');
      return;
    }

    // Validate passwords match
    if (password !== confirmPassword) {
      setError('Las contraseñas no coinciden');
      return;
    }

    // Validate password strength
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    setIsLoading(true);

    try {
      await resetPassword(code, password, confirmPassword);
      setSuccess(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al restablecer la contraseña';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  // Password strength indicator
  const getPasswordStrength = (pwd: string) => {
    if (pwd.length === 0) return { level: 0, text: '', color: '' };
    if (pwd.length < 8) return { level: 1, text: 'Débil', color: 'bg-red-500' };
    if (pwd.length < 12 && /[A-Z]/.test(pwd) && /[0-9]/.test(pwd)) 
      return { level: 2, text: 'Media', color: 'bg-yellow-500' };
    if (pwd.length >= 12 && /[A-Z]/.test(pwd) && /[0-9]/.test(pwd) && /[^A-Za-z0-9]/.test(pwd)) 
      return { level: 3, text: 'Fuerte', color: 'bg-green-500' };
    return { level: 2, text: 'Media', color: 'bg-yellow-500' };
  };

  const passwordStrength = getPasswordStrength(password);

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
            Contraseña Actualizada
          </h2>
          <p className="text-gray-400 mb-6">
            Tu contraseña ha sido restablecida exitosamente. Ya puedes iniciar sesión con tu nueva contraseña.
          </p>
          <Link 
            href="/login"
            className="block w-full bg-accent hover:bg-accent-light text-white font-medium py-3 px-4 rounded-lg transition-all text-center"
          >
            Iniciar Sesión
          </Link>
        </div>
      </div>
    );
  }

  if (!code) {
    return (
      <div className="w-full max-w-md mx-auto">
        <div className="glass rounded-2xl px-8 pt-8 pb-8 text-center">
          <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">
            Enlace Inválido
          </h2>
          <p className="text-gray-400 mb-6">
            Este enlace de recuperación no es válido o ha expirado. Por favor, solicita un nuevo enlace.
          </p>
          <Link 
            href="/forgot-password"
            className="block w-full bg-accent hover:bg-accent-light text-white font-medium py-3 px-4 rounded-lg transition-all text-center"
          >
            Solicitar Nuevo Enlace
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md mx-auto">
      <form onSubmit={handleSubmit} className="glass rounded-2xl px-8 pt-8 pb-8">
        <div className="w-16 h-16 bg-accent/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-accent-light" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-center text-white mb-6">
          Nueva Contraseña
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="mb-4">
          <label 
            htmlFor="password" 
            className="block text-gray-300 text-sm font-medium mb-2"
          >
            Nueva Contraseña
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            minLength={8}
            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
            placeholder="••••••••"
          />
          {password.length > 0 && (
            <div className="mt-2">
              <div className="flex gap-1 mb-1">
                {[1, 2, 3].map((level) => (
                  <div
                    key={level}
                    className={`h-1 flex-1 rounded-full transition-all ${
                      passwordStrength.level >= level ? passwordStrength.color : 'bg-white/10'
                    }`}
                  />
                ))}
              </div>
              <p className="text-xs text-gray-400">
                Seguridad: <span className={passwordStrength.level >= 2 ? 'text-green-400' : 'text-yellow-400'}>{passwordStrength.text}</span>
              </p>
            </div>
          )}
          <p className="text-xs text-gray-500 mt-1">Mínimo 8 caracteres</p>
        </div>

        <div className="mb-6">
          <label 
            htmlFor="confirmPassword" 
            className="block text-gray-300 text-sm font-medium mb-2"
          >
            Confirmar Contraseña
          </label>
          <input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
            className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all ${
              confirmPassword && confirmPassword !== password 
                ? 'border-red-500/50' 
                : 'border-white/10'
            }`}
            placeholder="••••••••"
          />
          {confirmPassword && confirmPassword !== password && (
            <p className="text-xs text-red-400 mt-1">Las contraseñas no coinciden</p>
          )}
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
              Actualizando...
            </span>
          ) : (
            'Restablecer Contraseña'
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

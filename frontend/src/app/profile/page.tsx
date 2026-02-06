'use client';

import { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { changePassword } from '@/services/auth';
import Header from '@/components/Header';
import Link from 'next/link';

export default function ProfilePage() {
  const { user, loading, isAuthenticated } = useAuth();
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess(false);

    if (newPassword !== confirmPassword) {
      setPasswordError('Las contraseñas no coinciden');
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    setPasswordLoading(true);

    try {
      await changePassword(currentPassword, newPassword);
      setPasswordSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setIsChangingPassword(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al cambiar la contraseña';
      setPasswordError(message);
    } finally {
      setPasswordLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center pt-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
        </main>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    return null;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      
      <main className="flex-1 pt-20 pb-8 px-4">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-3xl font-bold text-white mb-8">Mi Perfil</h1>

          {/* User Info Card */}
          <div className="glass rounded-2xl p-6 mb-6">
            <div className="flex items-center gap-4 mb-6">
              <div className="w-16 h-16 rounded-full bg-accent/30 flex items-center justify-center text-white text-2xl font-bold">
                {user.username.charAt(0).toUpperCase()}
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">{user.username}</h2>
                <p className="text-gray-400">{user.email}</p>
                {user.role && (
                  <span className="inline-block mt-1 px-3 py-1 bg-accent/20 text-accent-light text-sm rounded-full">
                    {user.role.name}
                  </span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-gray-400 mb-1">ID de Usuario</p>
                <p className="text-white font-mono">{user.id}</p>
              </div>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-gray-400 mb-1">Estado</p>
                <p className={user.confirmed ? 'text-green-400' : 'text-yellow-400'}>
                  {user.confirmed ? 'Confirmado' : 'Pendiente de confirmación'}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-gray-400 mb-1">Creado</p>
                <p className="text-white">
                  {new Date(user.createdAt).toLocaleDateString('es-MX', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg p-4">
                <p className="text-gray-400 mb-1">Última actualización</p>
                <p className="text-white">
                  {new Date(user.updatedAt).toLocaleDateString('es-MX', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              </div>
            </div>
          </div>

          {/* Password Change Section */}
          <div className="glass rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Seguridad</h3>
            </div>

            {passwordSuccess && (
              <div className="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                <p className="text-green-400 text-sm">Contraseña actualizada exitosamente</p>
              </div>
            )}

            {!isChangingPassword ? (
              <button
                onClick={() => setIsChangingPassword(true)}
                className="flex items-center gap-2 text-accent-light hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                Cambiar Contraseña
              </button>
            ) : (
              <form onSubmit={handlePasswordChange} className="space-y-4">
                {passwordError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                    <p className="text-red-400 text-sm">{passwordError}</p>
                  </div>
                )}

                <div>
                  <label htmlFor="currentPassword" className="block text-gray-300 text-sm font-medium mb-2">
                    Contraseña Actual
                  </label>
                  <input
                    id="currentPassword"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
                    placeholder="••••••••"
                  />
                </div>

                <div>
                  <label htmlFor="newPassword" className="block text-gray-300 text-sm font-medium mb-2">
                    Nueva Contraseña
                  </label>
                  <input
                    id="newPassword"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
                    placeholder="••••••••"
                  />
                  <p className="text-xs text-gray-500 mt-1">Mínimo 8 caracteres</p>
                </div>

                <div>
                  <label htmlFor="confirmPassword" className="block text-gray-300 text-sm font-medium mb-2">
                    Confirmar Nueva Contraseña
                  </label>
                  <input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className={`w-full px-4 py-3 bg-white/5 border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all ${
                      confirmPassword && confirmPassword !== newPassword
                        ? 'border-red-500/50'
                        : 'border-white/10'
                    }`}
                    placeholder="••••••••"
                  />
                  {confirmPassword && confirmPassword !== newPassword && (
                    <p className="text-xs text-red-400 mt-1">Las contraseñas no coinciden</p>
                  )}
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={passwordLoading}
                    className="bg-accent hover:bg-accent-light text-white font-medium py-2 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    {passwordLoading ? (
                      <span className="flex items-center">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Guardando...
                      </span>
                    ) : (
                      'Guardar'
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsChangingPassword(false);
                      setCurrentPassword('');
                      setNewPassword('');
                      setConfirmPassword('');
                      setPasswordError('');
                    }}
                    className="bg-white/10 hover:bg-white/20 text-white font-medium py-2 px-4 rounded-lg transition-all"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Quick Links */}
          <div className="mt-6 flex flex-wrap gap-4">
            <Link
              href="/api-keys"
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              Administrar API Keys
            </Link>
            <Link
              href="/"
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Ir al Chat
            </Link>
          </div>
        </div>
      </main>
      
      <footer className="py-6 text-center text-gray-500 text-sm">
        <p>© {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.</p>
      </footer>
    </div>
  );
}

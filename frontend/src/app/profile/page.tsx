'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { useAuth } from '@/hooks/useAuth';
import { changePassword, getUserUsage, updateProfile } from '@/services/auth';
import { purgeConversations } from '@/services/chat';
import Header from '@/components/Header';
import Link from 'next/link';
import type { UserUsage } from '@/types/auth';

const HISTORY_ENABLED_KEY = 'ominis_history_enabled';

export default function ProfilePage() {
  const { user, loading, isAuthenticated } = useAuth();
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [profileBio, setProfileBio] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  const [historyEnabled, setHistoryEnabled] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    const fullName = user.full_name || '';
    const parts = fullName.split(' ').filter(Boolean);
    setFirstName(parts[0] || '');
    setLastName(parts.slice(1).join(' '));
    setOrganization(user.institution || '');
    setProfileBio(user.bio || '');

    if (typeof window !== 'undefined') {
      const storedPhoto = localStorage.getItem(`ominis_profile_photo_url:${user.id}`);
      setPhotoUrl(storedPhoto || '');
      const storedHistory = localStorage.getItem(HISTORY_ENABLED_KEY);
      if (storedHistory !== null) setHistoryEnabled(storedHistory === 'true');
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let isMounted = true;
    setUsageLoading(true);
    getUserUsage('month')
      .then((data) => {
        if (isMounted) setUsage(data);
      })
      .catch(() => {
        if (isMounted) setUsage(null);
      })
      .finally(() => {
        if (isMounted) setUsageLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [user]);

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

  const resetProfileForm = () => {
    if (!user) return;
    const fullName = user.full_name || '';
    const parts = fullName.split(' ').filter(Boolean);
    setFirstName(parts[0] || '');
    setLastName(parts.slice(1).join(' '));
    setOrganization(user.institution || '');
    setProfileBio(user.bio || '');
    if (typeof window !== 'undefined') {
      const storedPhoto = localStorage.getItem(`ominis_profile_photo_url:${user.id}`);
      setPhotoUrl(storedPhoto || '');
    }
    setProfileError('');
    setProfileSuccess(false);
  };

  const handleProfileSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess(false);
    setProfileSaving(true);

    const fullName = [firstName.trim(), lastName.trim()].filter(Boolean).join(' ');

    try {
      await updateProfile({
        full_name: fullName,
        institution: organization.trim(),
        bio: profileBio.trim(),
      });
      if (typeof window !== 'undefined' && user) {
        localStorage.setItem(`ominis_profile_photo_url:${user.id}`, photoUrl.trim());
      }
      setProfileSuccess(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error al guardar el perfil';
      setProfileError(message);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleHistoryToggle = async (enabled: boolean) => {
    setHistoryError('');
    if (!enabled) {
      const confirmed = window.confirm(
        'Al desactivar el historial se borrarán todas tus investigaciones y no podrás recuperarlas. ¿Deseas continuar?'
      );
      if (!confirmed) return;
      try {
        setHistoryLoading(true);
        await purgeConversations();
      } catch (err) {
        const message = err instanceof Error ? err.message : 'No se pudo borrar el historial';
        setHistoryError(message);
        setHistoryLoading(false);
        return;
      } finally {
        setHistoryLoading(false);
      }
    }
    setHistoryEnabled(enabled);
    if (typeof window !== 'undefined') {
      localStorage.setItem(HISTORY_ENABLED_KEY, String(enabled));
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen relative">
        <div className="absolute inset-0 z-0">
          <Image src="/background.jpg" alt="" fill className="object-cover" priority />
          <div className="absolute inset-0 bg-[#0a1628]/80" />
        </div>
        <Header />
        <main className="relative z-10 flex-1 flex items-center justify-center pt-16 min-h-screen">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
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

  const displayName = [firstName, lastName].filter(Boolean).join(' ') || user.username;

  return (
    <div className="min-h-screen relative">
      {/* Background */}
      <div className="fixed inset-0 z-0">
        <Image src="/background.jpg" alt="" fill className="object-cover" priority />
        <div className="absolute inset-0 bg-[#0a1628]/80" />
      </div>

      <Header />
      
      <main className="relative z-10 pt-24 pb-12 px-4">
        <div className="max-w-2xl mx-auto">
          {/* Page title */}
          <div className="flex items-center gap-3 mb-8">
            <Link href="/" className="text-gray-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </Link>
            <h1 className="text-2xl font-bold text-white">Mi Perfil</h1>
          </div>

          {/* User Info Card */}
          <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 mb-6">
            <div className="flex items-center gap-4 mb-6">
              <div className="w-14 h-14 rounded-full bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-blue-400 text-xl font-bold overflow-hidden">
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt="Foto de perfil"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  user.username.charAt(0).toUpperCase()
                )}
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">{displayName}</h2>
                <p className="text-gray-400 text-sm">{user.email}</p>
                {user.role && (
                  <span className="inline-block mt-1 px-2.5 py-0.5 bg-blue-500/15 border border-blue-400/20 text-blue-400 text-xs rounded-full">
                    {user.role.name}
                  </span>
                )}
              </div>
            </div>

            <form onSubmit={handleProfileSave} className="space-y-4">
              {profileSuccess && (
                <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-xl">
                  <p className="text-green-400 text-sm">Perfil actualizado exitosamente</p>
                </div>
              )}
              {profileError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                  <p className="text-red-400 text-sm">{profileError}</p>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <label htmlFor="firstName" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Nombre
                  </label>
                  <input
                    id="firstName"
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="Nombre"
                  />
                </div>
                <div>
                  <label htmlFor="lastName" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Apellidos
                  </label>
                  <input
                    id="lastName"
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="Apellidos"
                  />
                </div>
                <div>
                  <label htmlFor="organization" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Organización
                  </label>
                  <input
                    id="organization"
                    type="text"
                    value={organization}
                    onChange={(e) => setOrganization(e.target.value)}
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="Nombre de la organización"
                  />
                </div>
                <div>
                  <label htmlFor="photoUrl" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Fotografía (URL)
                  </label>
                  <input
                    id="photoUrl"
                    type="url"
                    value={photoUrl}
                    onChange={(e) => setPhotoUrl(e.target.value)}
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="https://..."
                  />
                </div>
              </div>
              <div>
                <label htmlFor="profileBio" className="block text-gray-400 text-xs font-medium mb-1.5">
                  Perfil para el agente
                </label>
                <textarea
                  id="profileBio"
                  value={profileBio}
                  onChange={(e) => setProfileBio(e.target.value)}
                  rows={4}
                  className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all resize-none"
                  placeholder="Intereses, área de investigación, preferencias..."
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={profileSaving}
                  className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2.5 px-5 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {profileSaving ? 'Guardando...' : 'Guardar cambios'}
                </button>
                <button
                  type="button"
                  onClick={resetProfileForm}
                  className="bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 text-sm font-medium py-2.5 px-5 rounded-xl transition-colors"
                >
                  Restablecer
                </button>
              </div>
            </form>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm mt-6">
              <div className="bg-white/5 border border-white/5 rounded-xl p-3.5">
                <p className="text-gray-500 text-xs mb-1">Creado</p>
                <p className="text-white">
                  {new Date(user.createdAt).toLocaleDateString('es-MX', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              </div>
              <div className="bg-white/5 border border-white/5 rounded-xl p-3.5">
                <p className="text-gray-500 text-xs mb-1">Última actualización</p>
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

          {/* Security Section */}
          <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 mb-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              Seguridad
            </h3>

            {passwordSuccess && (
              <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-xl">
                <p className="text-green-400 text-sm flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Contraseña actualizada exitosamente
                </p>
              </div>
            )}

            {!isChangingPassword ? (
              <button
                onClick={() => setIsChangingPassword(true)}
                className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                Cambiar Contraseña
              </button>
            ) : (
              <form onSubmit={handlePasswordChange} className="space-y-4">
                {passwordError && (
                  <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                    <p className="text-red-400 text-sm">{passwordError}</p>
                  </div>
                )}

                <div>
                  <label htmlFor="currentPassword" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Contraseña Actual
                  </label>
                  <input
                    id="currentPassword"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="••••••••"
                  />
                </div>

                <div>
                  <label htmlFor="newPassword" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Nueva Contraseña
                  </label>
                  <input
                    id="newPassword"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                    className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                    placeholder="••••••••"
                  />
                  <p className="text-[11px] text-gray-600 mt-1">Mínimo 8 caracteres</p>
                </div>

                <div>
                  <label htmlFor="confirmPassword" className="block text-gray-400 text-xs font-medium mb-1.5">
                    Confirmar Nueva Contraseña
                  </label>
                  <input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className={`w-full px-4 py-2.5 bg-white/5 border rounded-xl text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all ${
                      confirmPassword && confirmPassword !== newPassword
                        ? 'border-red-500/40'
                        : 'border-white/10'
                    }`}
                    placeholder="••••••••"
                  />
                  {confirmPassword && confirmPassword !== newPassword && (
                    <p className="text-[11px] text-red-400 mt-1">Las contraseñas no coinciden</p>
                  )}
                </div>

                <div className="flex gap-3 pt-1">
                  <button
                    type="submit"
                    disabled={passwordLoading}
                    className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2.5 px-5 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {passwordLoading ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Guardando...
                      </span>
                    ) : (
                      'Guardar cambios'
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
                    className="bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 text-sm font-medium py-2.5 px-5 rounded-xl transition-colors"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            )}

            <div className="mt-6 border-t border-white/10 pt-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h4 className="text-sm font-medium text-white">Historial de trabajos</h4>
                  <p className="text-xs text-gray-500">
                    Al inhabilitarlo se borrará tu historial y no podrás recuperarlo.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleHistoryToggle(!historyEnabled)}
                  disabled={historyLoading}
                  className={`w-10 h-5 rounded-full transition-colors relative flex-shrink-0 ${
                    historyEnabled ? 'bg-blue-500' : 'bg-gray-600'
                  }`}
                  aria-pressed={historyEnabled}
                >
                  <span
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                      historyEnabled ? 'translate-x-[1.15rem]' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
              {historyError && (
                <div className="mt-3 p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                  <p className="text-red-400 text-sm">{historyError}</p>
                </div>
              )}
            </div>
          </div>

          {/* Usage Section */}
          <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Uso del periodo</h3>
              <span className="text-xs text-gray-500">Últimos 30 días</span>
            </div>
            {usageLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400"></div>
                Cargando estadísticas...
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                <div className="bg-white/5 border border-white/5 rounded-xl p-3.5">
                  <p className="text-gray-500 text-xs mb-1">Consultas</p>
                  <p className="text-white text-lg font-semibold">{usage?.totalQueries ?? 0}</p>
                </div>
                <div className="bg-white/5 border border-white/5 rounded-xl p-3.5">
                  <p className="text-gray-500 text-xs mb-1">Tokens consumidos</p>
                  <p className="text-white text-lg font-semibold">{usage?.totalTokens ?? 0}</p>
                </div>
                <div className="bg-white/5 border border-white/5 rounded-xl p-3.5">
                  <p className="text-gray-500 text-xs mb-1">Investigaciones</p>
                  <p className="text-white text-lg font-semibold">
                    {historyEnabled ? (usage?.totalInvestigations ?? 0) : '—'}
                  </p>
                  {!historyEnabled && (
                    <p className="text-[11px] text-gray-600 mt-1">Historial inhabilitado</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Quick Links */}
          <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-5">
            <div className="flex flex-wrap gap-5 justify-center">
              <Link
                href="/api-keys"
                className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
                Administrar API Keys
              </Link>
              <span className="text-white/10">|</span>
              <Link
                href="/profile/api-docs"
                className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Documentación API
              </Link>
              <span className="text-white/10">|</span>
              <Link
                href="/"
                className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Ir al Chat
              </Link>
            </div>
          </div>

          {/* Footer */}
          <p className="text-center text-gray-600 text-xs mt-6">
            © {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.
          </p>
        </div>
      </main>
    </div>
  );
}

"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/hooks/useAuth";
import { getSiteConfig } from "@/services/auth";

export default function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState<string>("");
  const [menuPosition, setMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const [bannerMessage, setBannerMessage] = useState<string | null>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const bannerRef = useRef<HTMLDivElement>(null);
  const { user, isAuthenticated, isAdmin, isDeveloper, logout, loading } = useAuth();

  useEffect(() => {
    const load = () => getSiteConfig().then((c) => setBannerMessage(c.banner_message || null)).catch(() => {});
    load();
    window.addEventListener('focus', load);
    return () => window.removeEventListener('focus', load);
  }, []);

  // Sync --banner-height with actual banner height so content shifts down and title isn't cut off. useLayoutEffect runs before paint.
  useLayoutEffect(() => {
    if (!bannerMessage) {
      document.documentElement.style.setProperty('--banner-height', '0px');
      return () => { document.documentElement.style.removeProperty('--banner-height'); };
    }
    const el = bannerRef.current;
    if (el) {
      const h = el.offsetHeight;
      document.documentElement.style.setProperty('--banner-height', `${h}px`);
    } else {
      document.documentElement.style.setProperty('--banner-height', '2.5rem');
    }
    return () => { document.documentElement.style.removeProperty('--banner-height'); };
  }, [bannerMessage]);

  // Update --banner-height when banner content might change height (e.g. wrap)
  useEffect(() => {
    if (!bannerMessage || !bannerRef.current) return;
    const el = bannerRef.current;
    const ro = new ResizeObserver(() => {
      document.documentElement.style.setProperty('--banner-height', `${el.offsetHeight}px`);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [bannerMessage]);

  const displayName = user?.full_name?.trim() || user?.username || "";

  useEffect(() => {
    if (user?.id && typeof window !== "undefined") {
      setPhotoUrl(localStorage.getItem(`ominis_profile_photo_url:${user.id}`) || "");
    }
  }, [user?.id]);

  // Clear menu position when closing
  useEffect(() => {
    if (!isUserMenuOpen) setMenuPosition(null);
  }, [isUserMenuOpen]);

  const openUserMenu = () => {
    if (profileButtonRef.current) {
      const rect = profileButtonRef.current.getBoundingClientRect();
      setMenuPosition({ top: rect.bottom + 8, right: window.innerWidth - rect.right });
    }
    setIsUserMenuOpen(true);
  };

  // Close user menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (userMenuRef.current && !userMenuRef.current.contains(target) && !(target as Element).closest?.("[data-profile-menu]")) {
        setIsUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    setIsUserMenuOpen(false);
    window.location.href = '/c';
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-[9999] bg-[#0a1628]/90 backdrop-blur-sm border-b border-white/10 pt-[env(safe-area-inset-top)]">
      {bannerMessage && (
        <div ref={bannerRef} className="bg-amber-500/20 text-amber-200 border-b border-amber-500/30 px-4 sm:px-6 lg:px-8 py-2 text-center text-sm min-h-[2.5rem] flex items-center justify-center">
          {bannerMessage}
        </div>
      )}
      <nav className="px-4 sm:px-6 lg:px-8 w-full min-w-0 overflow-x-hidden">
        <div className="flex items-center justify-between h-16">
          {/* Logo + Title */}
          <Link href="/c" className="flex items-center gap-3">
            <Image
              src="/logo.png"
              alt="OMINIS"
              width={140}
              height={40}
              className="h-7 w-auto"
              priority
            />
            <span className="hidden md:inline text-gray-300 text-xs border-l border-white/20 pl-3">
              Observatorio Mexicano para la Investigación y la Inteligencia en Salud
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-6">

            {/* Main nav links — solo admin/superadmin (no mostrar a investigadores ni developers) */}
            {isAuthenticated && isAdmin && (
              <>
                <Link
                  href="/live"
                  className="text-gray-400 hover:text-cyan-300 transition-colors text-sm flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Live Avatar
                </Link>
                <Link
                  href="https://chat.ominis.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-400 hover:text-cyan-300 transition-colors text-sm flex items-center gap-1.5"
                >
                  Agentes (Pro)
                </Link>
                <Link
                  href="/sinba"
                  className="text-gray-400 hover:text-cyan-300 transition-colors text-sm flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                  </svg>
                  Cubos SINBA
                </Link>
              </>
            )}

            {/* Auth Section */}
            {loading ? (
              <div className="w-8 h-8 rounded-full bg-white/10 animate-pulse" />
            ) : isAuthenticated && user ? (
              <div className="relative" ref={userMenuRef}>
                <button
                  ref={profileButtonRef}
                  onClick={() => (isUserMenuOpen ? setIsUserMenuOpen(false) : openUserMenu())}
                  className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-accent/30 flex items-center justify-center text-white text-sm font-medium overflow-hidden">
                    {photoUrl ? (
                      <img src={photoUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      user.username.charAt(0).toUpperCase()
                    )}
                  </div>
                  <span className="text-sm hidden lg:inline">{displayName || user.username}</span>
                  <svg 
                    className={`w-4 h-4 transition-transform ${isUserMenuOpen ? 'rotate-180' : ''}`} 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* User Dropdown Menu — rendered via Portal to escape stacking context */}
                {isUserMenuOpen && menuPosition && typeof document !== "undefined" && createPortal(
                  <div
                    data-profile-menu
                    className="fixed w-56 bg-[#0f1d32]/95 backdrop-blur-md border border-white/15 rounded-xl py-2 shadow-2xl animate-fade-in"
                    style={{
                      top: menuPosition.top,
                      right: menuPosition.right,
                      zIndex: 2147483647,
                    }}
                  >
                    <div className="px-4 py-2 border-b border-white/10">
                      <p className="text-white font-medium truncate">{displayName || user.username}</p>
                      <p className="text-gray-400 text-xs truncate">{user.email}</p>
                      {user.role && (
                        <span className="inline-block mt-1 px-2 py-0.5 bg-accent/20 text-accent-light text-xs rounded-full">
                          {user.role.name}
                        </span>
                      )}
                    </div>
                    <div className="py-1">
                      <Link
                        href="/profile"
                        onClick={() => setIsUserMenuOpen(false)}
                        className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                          </svg>
                          Mi Perfil
                        </span>
                      </Link>
                      <Link
                        href="/api-keys"
                        onClick={() => setIsUserMenuOpen(false)}
                        className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                          </svg>
                          API Keys
                        </span>
                      </Link>
                      <Link
                        href="/profile/api-docs"
                        onClick={() => setIsUserMenuOpen(false)}
                        className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          Documentación API
                        </span>
                      </Link>
                      <Link
                        href="/c"
                        onClick={() => setIsUserMenuOpen(false)}
                        className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                          </svg>
                          Ir al Chat
                        </span>
                      </Link>
                      {(isAdmin || isDeveloper) && (
                        <>
                          {isAdmin && (
                            <Link
                              href="/dashboard"
                              onClick={() => setIsUserMenuOpen(false)}
                              className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                            >
                              <span className="flex items-center gap-2">
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                                </svg>
                                Dashboard
                              </span>
                            </Link>
                          )}
                          <Link
                            href="/rag"
                            onClick={() => setIsUserMenuOpen(false)}
                            className="block px-4 py-2 text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-sm"
                          >
                            <span className="flex items-center gap-2">
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                              </svg>
                              DataStore
                            </span>
                          </Link>
                        </>
                      )}
                    </div>
                    <div className="border-t border-white/10 py-1">
                      <button
                        onClick={handleLogout}
                        className="w-full text-left px-4 py-2 text-red-400 hover:text-red-300 hover:bg-white/5 transition-colors text-sm"
                      >
                        <span className="flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                          </svg>
                          Cerrar Sesión
                        </span>
                      </button>
                    </div>
                  </div>,
                  document.body
                )}
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <Link 
                  href="/login"
                  className="text-gray-300 hover:text-white transition-colors text-sm"
                >
                  Iniciar Sesión
                </Link>
                <Link 
                  href="/register"
                  className="bg-accent hover:bg-accent-light text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                >
                  Registrarse
                </Link>
              </div>
            )}
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden text-white p-2"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Toggle menu"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {isMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile Navigation */}
        {isMenuOpen && (
          <div className="md:hidden py-4 border-t border-white/10">
            <div className="flex flex-col gap-4">
              {/* Mobile Auth Section */}
              <div className="border-t border-white/10 pt-4 mt-2">
                {loading ? (
                  <div className="h-10 bg-white/10 rounded-lg animate-pulse" />
                ) : isAuthenticated && user ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3 pb-3 border-b border-white/10">
                      <div className="w-10 h-10 rounded-full bg-accent/30 flex items-center justify-center text-white font-medium overflow-hidden">
                        {photoUrl ? (
                          <img src={photoUrl} alt="" className="w-full h-full object-cover" />
                        ) : (
                          user.username.charAt(0).toUpperCase()
                        )}
                      </div>
                      <div>
                        <p className="text-white font-medium">{displayName || user.username}</p>
                        <p className="text-gray-400 text-xs">{user.email}</p>
                      </div>
                    </div>
                    <Link 
                      href="/profile"
                      className="block text-gray-300 hover:text-white transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      Mi Perfil
                    </Link>
                    <Link 
                      href="/api-keys"
                      className="block text-gray-300 hover:text-white transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      API Keys
                    </Link>
                    <Link 
                      href="/profile/api-docs"
                      className="block text-gray-300 hover:text-white transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      Documentación API
                    </Link>
                    {isAuthenticated && isAdmin && (
                      <>
                        <Link 
                          href="/live"
                          className="block text-gray-300 hover:text-white transition-colors"
                          onClick={() => setIsMenuOpen(false)}
                        >
                          Live Avatar
                        </Link>
                        <Link 
                          href="https://chat.ominis.org"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block text-gray-300 hover:text-white transition-colors"
                          onClick={() => setIsMenuOpen(false)}
                        >
                          Agentes (Pro)
                        </Link>
                        <Link 
                          href="/sinba"
                          className="block text-gray-300 hover:text-white transition-colors"
                          onClick={() => setIsMenuOpen(false)}
                        >
                          Cubos SINBA
                        </Link>
                      </>
                    )}
                    <Link 
                      href="/c"
                      className="block text-gray-300 hover:text-white transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      Ir al Chat
                    </Link>
                    {(isAdmin || isDeveloper) && (
                      <>
                        {isAdmin && (
                        <Link 
                          href="/dashboard"
                          className="block text-gray-300 hover:text-white transition-colors"
                          onClick={() => setIsMenuOpen(false)}
                        >
                          Dashboard
                        </Link>
                        )}
                        <Link 
                          href="/rag"
                          className="block text-gray-300 hover:text-white transition-colors"
                          onClick={() => setIsMenuOpen(false)}
                        >
                          DataStore
                        </Link>
                      </>
                    )}
                    <button
                      onClick={handleLogout}
                      className="text-red-400 hover:text-red-300 transition-colors"
                    >
                      Cerrar Sesión
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    <Link 
                      href="/login"
                      className="text-gray-300 hover:text-white transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      Iniciar Sesión
                    </Link>
                    <Link 
                      href="/register"
                      className="bg-accent hover:bg-accent-light text-white text-center font-medium px-4 py-2 rounded-lg transition-colors"
                      onClick={() => setIsMenuOpen(false)}
                    >
                      Registrarse
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </nav>
    </header>
  );
}

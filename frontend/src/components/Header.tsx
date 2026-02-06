"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const { user, isAuthenticated, logout, loading } = useAuth();

  // Close user menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    setIsUserMenuOpen(false);
    window.location.href = '/';
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-[#0a1628]/90 backdrop-blur-sm border-b border-white/10">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo + Title */}
          <Link href="/" className="flex items-center gap-3">
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
            <Link 
              href="https://ominis.org" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              Observatorio
            </Link>
            <Link 
              href="https://roclab.ominis.org" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              ROCLab
            </Link>
            <Link 
              href="https://funsalud.org.mx" 
              target="_blank"
              className="text-gray-300 hover:text-white transition-colors text-sm"
            >
              FUNSALUD
            </Link>

            {/* Separator */}
            <div className="w-px h-6 bg-white/20" />

            {/* Auth Section */}
            {loading ? (
              <div className="w-8 h-8 rounded-full bg-white/10 animate-pulse" />
            ) : isAuthenticated && user ? (
              <div className="relative" ref={userMenuRef}>
                <button
                  onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                  className="flex items-center gap-2 text-gray-300 hover:text-white transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-accent/30 flex items-center justify-center text-white text-sm font-medium">
                    {user.username.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm hidden lg:inline">{user.username}</span>
                  <svg 
                    className={`w-4 h-4 transition-transform ${isUserMenuOpen ? 'rotate-180' : ''}`} 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* User Dropdown Menu */}
                {isUserMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 glass rounded-xl py-2 shadow-xl animate-fade-in">
                    <div className="px-4 py-2 border-b border-white/10">
                      <p className="text-white font-medium truncate">{user.username}</p>
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
                  </div>
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
              <Link 
                href="https://ominis.org" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
                onClick={() => setIsMenuOpen(false)}
              >
                Observatorio
              </Link>
              <Link 
                href="https://roclab.ominis.org" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
                onClick={() => setIsMenuOpen(false)}
              >
                ROCLab
              </Link>
              <Link 
                href="https://funsalud.org.mx" 
                target="_blank"
                className="text-gray-300 hover:text-white transition-colors"
                onClick={() => setIsMenuOpen(false)}
              >
                FUNSALUD
              </Link>

              {/* Mobile Auth Section */}
              <div className="border-t border-white/10 pt-4 mt-2">
                {loading ? (
                  <div className="h-10 bg-white/10 rounded-lg animate-pulse" />
                ) : isAuthenticated && user ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3 pb-3 border-b border-white/10">
                      <div className="w-10 h-10 rounded-full bg-accent/30 flex items-center justify-center text-white font-medium">
                        {user.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-white font-medium">{user.username}</p>
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

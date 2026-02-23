'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import { useAuth } from '@/hooks/useAuth';
import { getToken } from '@/services/auth';

// Docs endpoint is at the app root (not under /v1)
const API_DOCS_BASE = (process.env.NEXT_PUBLIC_API_URL || 'https://api.ominis.org').replace(/\/v1$/, '');

export default function ApiDocsPage() {
  const { user, loading: authLoading, isAuthenticated } = useAuth();
  const [docsUrl, setDocsUrl] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      const token = getToken();
      if (token) {
        setDocsUrl(`${API_DOCS_BASE}/docs?token=${encodeURIComponent(token)}`);
      }
    }
  }, [isAuthenticated]);

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center pt-16">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-red-400">Acceso Denegado</h1>
            <p className="mt-2 text-gray-400">
              Inicia sesión para acceder a la documentación de la API.
            </p>
            <Link href="/login" className="mt-4 inline-block text-cyan-400 hover:underline">
              Iniciar Sesión
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a1628]">
      <Header />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Documentación de la API</h1>
            <p className="text-gray-400 text-sm mt-1">
              Referencia completa de la API de Ominis para interactuar con el modelo ominis-2.0.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/api-keys"
              className="text-sm text-gray-300 hover:text-white transition-colors"
            >
              Ver API Keys
            </Link>
            {docsUrl && (
              <a
                href={docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                Abrir en nueva pestaña
              </a>
            )}
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          {docsUrl ? (
            <>
              <div className="px-5 py-3 border-b border-white/10 bg-white/5">
                <p className="text-gray-300 text-sm">
                  Si la vista embebida no carga, usa el botón &quot;Abrir en nueva pestaña&quot;.
                </p>
              </div>
              <div className="h-[70vh] bg-black/20">
                <iframe
                  title="Documentación de la API de Ominis"
                  src={docsUrl}
                  className="w-full h-full"
                  referrerPolicy="no-referrer"
                />
              </div>
            </>
          ) : (
            <div className="p-8 text-center text-gray-400">
              <p>Cargando documentación...</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { storeAuth } from '@/services/auth';
import type { User } from '@/types/auth';
import Image from 'next/image';
import Link from 'next/link';

function DidactivaRedirectContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    const jwt = searchParams.get('jwt') || searchParams.get('access_token');
    const userParam = searchParams.get('user');

    if (jwt && userParam) {
      try {
        const user = JSON.parse(decodeURIComponent(userParam)) as User;
        storeAuth(jwt, user);
        setStatus('success');
        window.location.href = '/c';
      } catch {
        setError('Error procesando la autenticación de Didactiva');
        setStatus('error');
      }
    } else if (jwt) {
      // JWT only - fetch user profile
      fetch(`${process.env.NEXT_PUBLIC_API_URL || 'https://api.ominis.org'}/v1/api/users/me?populate=role`, {
        headers: { Authorization: `Bearer ${jwt}` },
      })
        .then((res) => res.json())
        .then((user) => {
          storeAuth(jwt, user);
          setStatus('success');
          window.location.href = '/c';
        })
        .catch(() => {
          setError('Error obteniendo datos del usuario');
          setStatus('error');
        });
    } else {
      setError('No se recibió el token de autenticación');
      setStatus('error');
    }
  }, [searchParams]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center relative">
        <div className="absolute inset-0 z-0">
          <Image src="/background.jpg" alt="" fill className="object-cover" priority />
          <div className="absolute inset-0 bg-[#0a1628]/70" />
        </div>
        <div className="relative z-10 glass rounded-2xl px-12 py-10 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-teal-400 mx-auto mb-4" />
          <p className="text-white font-medium">Completando inicio de sesión con Didactiva...</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center relative">
        <div className="absolute inset-0 z-0">
          <Image src="/background.jpg" alt="" fill className="object-cover" priority />
          <div className="absolute inset-0 bg-[#0a1628]/70" />
        </div>
        <div className="relative z-10 glass rounded-2xl px-12 py-10 text-center max-w-md border border-white/10">
          <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Error de autenticación</h2>
          <p className="text-gray-400 mb-6 text-sm">{error}</p>
          <Link
            href="/login"
            className="block w-full bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold py-3 px-4 rounded-lg text-center"
          >
            Volver al inicio de sesión
          </Link>
        </div>
      </div>
    );
  }

  return null;
}

export default function DidactivaRedirectPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex flex-col items-center justify-center relative">
        <div className="absolute inset-0 z-0">
          <Image src="/background.jpg" alt="" fill className="object-cover" priority />
          <div className="absolute inset-0 bg-[#0a1628]/70" />
        </div>
        <div className="relative z-10 glass rounded-2xl px-12 py-10 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-teal-400 mx-auto mb-4" />
          <p className="text-white font-medium">Completando inicio de sesión...</p>
        </div>
      </div>
    }>
      <DidactivaRedirectContent />
    </Suspense>
  );
}

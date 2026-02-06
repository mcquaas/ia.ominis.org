'use client';

import { Suspense } from 'react';
import Image from 'next/image';
import { ResetPasswordForm } from '@/components/auth';
import Header from '@/components/Header';

function ResetPasswordContent() {
  return <ResetPasswordForm />;
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex flex-col relative">
      {/* Background */}
      <div className="absolute inset-0 z-0">
        <Image
          src="/background.jpg"
          alt=""
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 bg-[#0a1628]/70"></div>
      </div>

      <Header />
      
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 pt-20 pb-8">
        <div className="w-full max-w-md animate-fade-in">
          <Suspense fallback={
            <div className="glass rounded-2xl px-8 pt-8 pb-8 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent mx-auto"></div>
              <p className="text-gray-400 mt-4">Cargando...</p>
            </div>
          }>
            <ResetPasswordContent />
          </Suspense>
        </div>
      </main>
      
      <footer className="relative z-10 py-6 text-center text-gray-500 text-sm">
        <p>© {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.</p>
      </footer>
    </div>
  );
}

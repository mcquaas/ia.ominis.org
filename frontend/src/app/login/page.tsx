import Image from 'next/image';
import { Suspense } from 'react';
import { LoginForm } from '@/components/auth';
import Header from '@/components/Header';
import LoginPageClient from './LoginPageClient';

export const metadata = {
  title: 'Acceso Miembros CIAS | OMINIS',
  description: 'Inicia sesión con tu cuenta de miembro de la Red CIAS en OMINIS',
};

export default function LoginPage() {
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
            <div className="glass rounded-2xl p-8 text-center border border-white/10">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-400 mx-auto mb-2" />
              <p className="text-gray-300 text-xs">Cargando formulario de acceso...</p>
            </div>
          }>
            <LoginPageClient />
          </Suspense>
        </div>
      </main>
      
      <footer className="relative z-10 py-6 text-center text-gray-500 text-sm">
        <p>© {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.</p>
      </footer>
    </div>
  );
}

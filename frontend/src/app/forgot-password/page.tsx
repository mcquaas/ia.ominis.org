import Image from 'next/image';
import { ForgotPasswordForm } from '@/components/auth';
import Header from '@/components/Header';

export const metadata = {
  title: 'Recuperar Contraseña | Ominis AI',
  description: 'Recupera tu contraseña de Ominis AI',
};

export default function ForgotPasswordPage() {
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
          <ForgotPasswordForm />
        </div>
      </main>
      
      <footer className="relative z-10 py-6 text-center text-gray-500 text-sm">
        <p>© {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.</p>
      </footer>
    </div>
  );
}

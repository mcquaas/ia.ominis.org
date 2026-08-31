'use client';

import Link from 'next/link';

export function ResetPasswordForm() {
  return (
    <div className="w-full max-w-md mx-auto">
      <div className="glass rounded-2xl px-8 pt-8 pb-8 border border-white/10 shadow-2xl backdrop-blur-xl text-center">
        <div className="w-16 h-16 bg-teal-500/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-teal-500/30">
          <svg className="w-8 h-8 text-teal-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>

        <h2 className="text-2xl font-bold text-white mb-3">
          Restablecer Contraseña
        </h2>
        <p className="text-sm text-gray-300 mb-6 leading-relaxed">
          Las credenciales de acceso se gestionan de forma centralizada y segura a través de <strong className="text-teal-300">cias.ai</strong>.
        </p>

        <div className="space-y-3">
          <a
            href="https://www.cias.ai/auth"
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold py-3 px-4 rounded-lg transition-all shadow-lg shadow-teal-500/20 text-center text-sm"
          >
            Ir a cias.ai para restablecer contraseña →
          </a>

          <Link
            href="/login"
            className="block w-full py-3 px-4 bg-white/10 hover:bg-white/15 text-white font-medium rounded-lg transition-all border border-white/10 text-center text-sm"
          >
            Volver al Inicio de Sesión
          </Link>
        </div>
      </div>
    </div>
  );
}

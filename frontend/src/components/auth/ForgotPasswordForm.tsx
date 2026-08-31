'use client';

import Link from 'next/link';

export function ForgotPasswordForm() {
  return (
    <div className="w-full max-w-md mx-auto">
      <div className="glass rounded-2xl px-8 pt-8 pb-8 border border-white/10 shadow-2xl backdrop-blur-xl text-center">
        <div className="w-16 h-16 bg-teal-500/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-teal-500/30">
          <svg className="w-8 h-8 text-teal-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
        </div>

        <h2 className="text-2xl font-bold text-white mb-3">
          Recuperación de Contraseña
        </h2>
        <p className="text-sm text-gray-300 mb-6 leading-relaxed">
          Las cuentas y contraseñas de <strong className="text-white font-semibold">ia.ominis.org</strong> se gestionan directamente a través de la plataforma de la <strong className="text-teal-300">Red CIAS</strong>.
        </p>

        <div className="bg-white/5 border border-white/10 rounded-xl p-4 mb-6 text-left">
          <p className="text-xs text-gray-300 leading-relaxed">
            Para restablecer tu contraseña, ingresa a <span className="text-white font-medium">cias.ai</span> e inicia el proceso de recuperación de cuenta o solicita un enlace de acceso seguro.
          </p>
        </div>

        <div className="space-y-3">
          <a
            href="https://www.cias.ai/auth"
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold py-3 px-4 rounded-lg transition-all shadow-lg shadow-teal-500/20 text-center text-sm"
          >
            Ir a cias.ai para recuperar contraseña →
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

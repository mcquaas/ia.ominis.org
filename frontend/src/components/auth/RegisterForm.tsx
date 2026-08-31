'use client';

import Link from 'next/link';

export function RegisterForm() {
  return (
    <div className="w-full max-w-md mx-auto">
      <div className="glass rounded-2xl px-8 pt-8 pb-8 border border-white/10 shadow-2xl backdrop-blur-xl text-center">
        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-teal-500/15 text-teal-300 border border-teal-500/30">
            <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
            Membresía CIAS Requerida
          </span>
        </div>

        <h2 className="text-2xl font-bold text-white mb-3">
          Registro en la Red CIAS
        </h2>
        <p className="text-sm text-gray-300 mb-6 leading-relaxed">
          El acceso a <strong className="text-white font-semibold">ia.ominis.org</strong> es exclusivo para miembros verificados del Centro de Inteligencia Artificial en Salud (<strong className="text-teal-300">CIAS</strong>).
        </p>

        <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-6 text-left">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-teal-400 mb-2">
            Pasos para obtener acceso:
          </h3>
          <ol className="text-xs text-gray-300 space-y-2 list-decimal list-inside leading-relaxed">
            <li>Crea tu cuenta en la plataforma oficial de <span className="text-white font-medium">cias.ai</span>.</li>
            <li>Verifica tu correo electrónico y completa tu perfil.</li>
            <li>Activa tu membresía de la Red de Especialistas en Salud.</li>
            <li>Inicia sesión en OMINIS con tus credenciales de CIAS.</li>
          </ol>
        </div>

        <div className="space-y-3">
          <a
            href="https://www.cias.ai/auth"
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-400 hover:to-cyan-400 text-slate-950 font-bold py-3 px-4 rounded-lg transition-all shadow-lg shadow-teal-500/20 text-center text-sm"
          >
            Crear cuenta en cias.ai →
          </a>

          <Link
            href="/login"
            className="block w-full py-3 px-4 bg-white/10 hover:bg-white/15 text-white font-medium rounded-lg transition-all border border-white/10 text-center text-sm"
          >
            Ya soy miembro, Iniciar Sesión
          </Link>
        </div>
      </div>
    </div>
  );
}

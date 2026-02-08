import Image from "next/image";
import Link from "next/link";

export default function Footer() {
  return (
    <footer className="bg-[#060e1a] border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {/* Col 1: FUNSALUD */}
          <div>
            <div className="flex items-center gap-3 mb-3">
              <Image
                src="/funsalud-logo.png"
                alt="FUNSALUD"
                width={90}
                height={36}
                className="h-9 w-auto flex-shrink-0"
              />
            </div>
            <p className="text-gray-400 text-xs leading-relaxed mb-2">
              OMINIS es una iniciativa sin fines de lucro de la{" "}
              <Link href="https://funsalud.org.mx" target="_blank" className="text-white hover:text-blue-400 transition-colors">
                Fundación Mexicana para la Salud A.C.
              </Link>{" "}
              para facilitar la investigación en salud apoyada por inteligencia artificial
              y respaldada por miles de fuentes de información curadas por un equipo humano.
            </p>
            <div className="flex items-center gap-2 mt-3">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-green-400 text-xs">100% Datos en México</span>
            </div>
          </div>

          {/* Col 2: Technology */}
          <div>
            <h3 className="text-white font-semibold text-sm mb-3 flex items-center gap-2">
              <span className="text-green-400">🇲🇽</span> Tecnología
            </h3>
            <p className="text-gray-400 text-xs leading-relaxed mb-2">
              Potenciado por{" "}
              <Link href="/modelo" className="text-blue-400 hover:underline font-medium">ominis-2.0</Link>,
              modelo de IA mexicano especializado en salud. Entrenado con protocolos, datos y artículos
              hospedados exclusivamente en México (S3 mx-central-1).
            </p>
            <p className="text-green-400 text-xs font-medium mb-2">
              No usamos modelos de terceros (OpenAI, Google, Anthropic, Meta).
            </p>
            <p className="text-gray-500 text-xs">
              Infraestructura 100% administrada por FUNSALUD.{" "}
              <Link href="/modelo" className="text-blue-400 hover:underline">Ver más →</Link>
            </p>
          </div>

          {/* Col 3: Resources */}
          <div>
            <h3 className="text-white font-semibold text-sm mb-3">Recursos</h3>
            <ul className="space-y-2.5">
              <li>
                <Link
                  href="https://ominis.org"
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-xs flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  </svg>
                  Observatorio OMINIS
                </Link>
              </li>
              <li>
                <Link
                  href="https://roclab.ominis.org"
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-xs flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  ROCLab — Machine learning sin código
                </Link>
              </li>
              <li>
                <Link
                  href="https://funsalud.org.mx"
                  target="_blank"
                  className="text-gray-400 hover:text-white transition-colors text-xs flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                  FUNSALUD
                </Link>
              </li>
              <li>
                <Link
                  href="/modelo"
                  className="text-gray-400 hover:text-white transition-colors text-xs flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  Modelo ominis-2.0
                </Link>
              </li>
            </ul>
          </div>

          {/* Col 4: Contact */}
          <div>
            <h3 className="text-white font-semibold text-sm mb-3">Contacto</h3>
            <div className="space-y-3">
              <div>
                <p className="text-gray-400 text-xs leading-relaxed">
                  Estamos mejorando OMINIS constantemente. Compártenos
                  cualquier comportamiento inesperado o ideas de mejora.
                </p>
              </div>
              <a
                href="mailto:ominis@funsalud.org.mx"
                className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 text-xs transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                ominis@funsalud.org.mx
              </a>
              <div className="pt-2">
                <p className="text-gray-500 text-xs mb-1">
                  ¿Quieres integrar ominis-2.0 en tu aplicación de salud?
                </p>
                <a
                  href="mailto:ominis@funsalud.org.mx?subject=Solicitud%20de%20acceso%20a%20ominis-2.0"
                  className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                >
                  Solicitar acceso →
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-white/10 mt-8 pt-6">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-3">
              <Image
                src="/logo.png"
                alt="OMINIS"
                width={100}
                height={28}
                className="h-6 w-auto"
              />
              <span className="text-gray-600 text-xs">
                © {new Date().getFullYear()} Fundación Mexicana para la Salud A.C.
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Datos en México
              </span>
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
                Fuentes verificadas
              </span>
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                Privacidad
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}

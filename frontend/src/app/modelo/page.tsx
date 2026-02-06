import Image from "next/image";
import Link from "next/link";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

export const metadata = {
  title: "ominis-2.0 - Primer LLM Mexicano de Salud | OMINIS",
  description: "Conoce ominis-2.0, el primer Gran Modelo de Lenguaje (LLM) mexicano especializado en salud y dedicado a la investigación clínica, epidemiológica y administrativa del sector salud.",
};

export default function ModeloPage() {
  return (
    <main className="min-h-screen bg-[#0a1628]">
      <Header />
      
      <section className="pt-24 pb-16 relative">
        {/* Background */}
        <div className="absolute inset-0 z-0">
          <Image
            src="/background.jpg"
            alt=""
            fill
            className="object-cover"
            priority
          />
          <div className="absolute inset-0 bg-[#0a1628]/90"></div>
        </div>

        <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Back link */}
          <Link 
            href="/" 
            className="inline-flex items-center gap-2 text-gray-400 hover:text-white text-sm mb-8 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Volver al inicio
          </Link>

          {/* Hero */}
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 bg-green-500/10 border border-green-500/30 rounded-full px-4 py-2 mb-6">
              <span className="text-green-400 text-lg">🇲🇽</span>
              <span className="text-green-400 text-sm font-medium">Hecho en México</span>
            </div>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-4">
              ominis-2.0
            </h1>
            <p className="text-xl md:text-2xl text-blue-400 font-medium mb-6">
              Primer LLM Mexicano Especializado en Salud
            </p>
            <p className="text-gray-300 max-w-3xl mx-auto text-lg leading-relaxed">
              El primer Gran Modelo de Lenguaje (LLM) mexicano dedicado a la investigación 
              clínica, epidemiológica y administrativa del sector salud. Desarrollado por 
              la Fundación Mexicana para la Salud para impulsar la investigación médica en México.
            </p>
          </div>

          {/* Key Features */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-blue-400 mb-1">7B</div>
              <div className="text-gray-400 text-sm">Parámetros</div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-green-400 mb-1">32K</div>
              <div className="text-gray-400 text-sm">Contexto (tokens)</div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-purple-400 mb-1">78%</div>
              <div className="text-gray-400 text-sm">Precisión Médica</div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-yellow-400 mb-1">100%</div>
              <div className="text-gray-400 text-sm">Datos en México</div>
            </div>
          </div>

          {/* Specifications */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              Especificaciones del Modelo
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Especificación</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3">Valor</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Parámetros</td>
                    <td className="text-white font-medium py-3">7 mil millones</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Ventana de Contexto</td>
                    <td className="text-white font-medium py-3">32,768 tokens</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Arquitectura</td>
                    <td className="text-white font-medium py-3">Transformer (decoder-only)</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Capas</td>
                    <td className="text-white font-medium py-3">32</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Cabezas de Atención</td>
                    <td className="text-white font-medium py-3">32</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Dimensión Oculta</td>
                    <td className="text-white font-medium py-3">4,096</td>
                  </tr>
                  <tr>
                    <td className="text-gray-300 py-3 pr-4">Tipo de Atención</td>
                    <td className="text-white font-medium py-3">Grouped-Query Attention (GQA)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Training Data */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              Fuentes de Entrenamiento
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Fuente</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Documentos</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3">Tokens</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">PubMed Central (Open Access)</td>
                    <td className="text-white font-medium py-3 pr-4">~3,000,000 artículos</td>
                    <td className="text-white font-medium py-3">~14B</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Resúmenes Médicos</td>
                    <td className="text-white font-medium py-3 pr-4">~30,000,000</td>
                    <td className="text-white font-medium py-3">~3B</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Guías Clínicas</td>
                    <td className="text-white font-medium py-3 pr-4">~50,000</td>
                    <td className="text-white font-medium py-3">~500M</td>
                  </tr>
                  <tr>
                    <td className="text-gray-300 py-3 pr-4">Fuentes y datasets mantenidos y curados por FUNSALUD</td>
                    <td className="text-white font-medium py-3 pr-4">+1,400</td>
                    <td className="text-white font-medium py-3">(RAG)</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="mt-4 pt-4 border-t border-white/10">
              <p className="text-gray-400 text-sm">
                <strong className="text-white">Total:</strong> Más de 33 millones de documentos, 17.5 mil millones de tokens de texto médico especializado, 
                y más de 1,400 fuentes de información y datasets mantenidos y curados por FUNSALUD.
              </p>
            </div>
          </div>

          {/* Medical Domains */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              Dominios Médicos Cubiertos
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {[
                "Medicina Interna",
                "Cardiología",
                "Endocrinología",
                "Diabetes",
                "Oncología",
                "Pediatría",
                "Enfermedades Infecciosas",
                "Farmacología",
                "Salud Pública",
                "Nutrición",
                "Salud Mental",
                "Epidemiología"
              ].map((domain, i) => (
                <div 
                  key={i}
                  className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-center"
                >
                  <span className="text-gray-300 text-sm">{domain}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Performance Benchmarks */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Métricas de Rendimiento
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-300">Precisión en preguntas clínicas</span>
                  <span className="text-white font-bold">78%</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: '78%' }}></div>
                </div>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-300">Fluidez en Español</span>
                  <span className="text-white font-bold">92%</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2">
                  <div className="bg-green-500 h-2 rounded-full" style={{ width: '92%' }}></div>
                </div>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-300">Atribución de Fuentes</span>
                  <span className="text-white font-bold">95%</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2">
                  <div className="bg-purple-500 h-2 rounded-full" style={{ width: '95%' }}></div>
                </div>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-300">Cumplimiento de Seguridad</span>
                  <span className="text-white font-bold">98%</span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-2">
                  <div className="bg-yellow-500 h-2 rounded-full" style={{ width: '98%' }}></div>
                </div>
              </div>
            </div>
          </div>

          {/* Privacy & Security */}
          <div className="bg-gradient-to-r from-green-500/10 to-blue-500/10 border border-green-500/20 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-3">
              <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Privacidad y Seguridad
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="md:col-span-2">
                <h3 className="text-white font-semibold mb-2">Infraestructura 100% Administrada por FUNSALUD</h3>
                <p className="text-gray-400 text-sm">
                  Todos los datos son hospedados en México por AWS en su centro de datos en Querétaro, QRO. 
                  Las inferencias más complejas pueden viajar a un centro de datos administrado por FUNSALUD 
                  en EUA debido a la falta de infraestructura GPU en México. Todas las inferencias son 
                  procesadas por el LLM mexicano ominis-2.0. Ningún dato es compartido o inferido con modelos 
                  de IA de terceros como Google (Gemini), OpenAI (GPT), Anthropic (Claude) o Meta (Llama).
                </p>
              </div>
              <div>
                <h3 className="text-white font-semibold mb-2">Sin Almacenamiento de Consultas</h3>
                <p className="text-gray-400 text-sm">
                  Las consultas de los usuarios no se almacenan. Cada sesión es 
                  procesada de forma transitoria sin guardar historial.
                </p>
              </div>
              <div>
                <h3 className="text-white font-semibold mb-2">Curación Humana</h3>
                <p className="text-gray-400 text-sm">
                  Todas las fuentes de información son curadas y verificadas por 
                  un equipo humano de curadores especializados en salud.
                </p>
              </div>
            </div>
          </div>

          {/* CTA */}
          <div className="text-center">
            <h3 className="text-xl font-bold text-white mb-4">¿Quieres integrar ominis-2.0 en tu aplicación?</h3>
            <p className="text-gray-400 mb-6">
              Si deseas utilizar el modelo ominis-2.0 para una aplicación de salud en México, contáctanos para solicitar acceso.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href="mailto:curacion-ominis@funsalud.org.mx"
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-full font-medium transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                Solicitar Acceso
              </a>
              <Link
                href="/"
                className="inline-flex items-center gap-2 bg-white/10 hover:bg-white/20 text-white px-6 py-3 rounded-full font-medium transition-colors"
              >
                Probar el Asistente
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  );
}

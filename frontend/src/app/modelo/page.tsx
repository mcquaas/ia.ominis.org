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
              <span className="text-green-400 text-sm font-medium">IA hecha en México</span>
            </div>
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-4">
              ominis-2.0
            </h1>
            <p className="text-xl md:text-2xl text-blue-400 font-medium mb-6">
              LLM Mexicano Especializado en Salud
            </p>
            <p className="text-gray-300 max-w-3xl mx-auto text-lg leading-relaxed">
              Gran Modelo de Lenguaje (LLM) especializado en investigación clínica, 
              epidemiológica y administrativa del sector salud mexicano. Desarrollado y operado 
              por la Fundación Mexicana para la Salud (FUNSALUD) con infraestructura exclusiva 
              en México.
            </p>
          </div>

          {/* Key Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-blue-400 mb-1">7B</div>
              <div className="text-gray-400 text-sm">Parámetros</div>
            </div>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-green-400 mb-1">32K</div>
              <div className="text-gray-400 text-sm">Contexto (tokens)</div>
            </div>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-purple-400 mb-1">1,400+</div>
              <div className="text-gray-400 text-sm">Fuentes curadas</div>
            </div>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-yellow-400 mb-1">100%</div>
              <div className="text-gray-400 text-sm">Datos en México</div>
            </div>
          </div>

          {/* How it works */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Cómo funciona
            </h2>
            <p className="text-gray-300 text-sm leading-relaxed mb-6">
              ominis-2.0 combina un modelo de lenguaje fine-tuned con un sistema de 
              Retrieval-Augmented Generation (RAG) que consulta múltiples fuentes de información 
              en tiempo real para generar respuestas fundamentadas en evidencia.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white/5 rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-7 h-7 bg-cyan-500/20 rounded-lg flex items-center justify-center text-cyan-400 text-xs font-bold">1</span>
                  <h4 className="text-white text-sm font-semibold">Consulta del usuario</h4>
                </div>
                <p className="text-gray-400 text-xs leading-relaxed">
                  La pregunta se procesa y se enriquece con contexto de la conversación activa 
                  para generar una búsqueda semántica precisa.
                </p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-7 h-7 bg-blue-500/20 rounded-lg flex items-center justify-center text-blue-400 text-xs font-bold">2</span>
                  <h4 className="text-white text-sm font-semibold">Búsqueda multi-fuente</h4>
                </div>
                <p className="text-gray-400 text-xs leading-relaxed">
                  El sistema RAG consulta simultáneamente: la base vectorial OMINIS (pgvector), 
                  búsqueda web, y artículos de PubMed — priorizando fuentes relevantes.
                </p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-7 h-7 bg-purple-500/20 rounded-lg flex items-center justify-center text-purple-400 text-xs font-bold">3</span>
                  <h4 className="text-white text-sm font-semibold">Generación con citas</h4>
                </div>
                <p className="text-gray-400 text-xs leading-relaxed">
                  ominis-2.0 sintetiza la información recuperada y genera una respuesta en 
                  español con citas verificables a las fuentes originales.
                </p>
              </div>
            </div>
          </div>

          {/* Architecture */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              Arquitectura del Modelo
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Componente</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3">Detalle</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Parámetros</td>
                    <td className="text-white font-medium py-3">7 mil millones</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Ventana de contexto</td>
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
                    <td className="text-gray-300 py-3 pr-4">Cabezas de atención</td>
                    <td className="text-white font-medium py-3">32 (con Grouped-Query Attention)</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Dimensión oculta</td>
                    <td className="text-white font-medium py-3">4,096</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Fine-tuning</td>
                    <td className="text-white font-medium py-3">Instruction-tuning con datos médicos en español</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Embeddings (RAG)</td>
                    <td className="text-white font-medium py-3">Sentence Transformers (384 dim)</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Vector store</td>
                    <td className="text-white font-medium py-3">pgvector (PostgreSQL)</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Inferencia</td>
                    <td className="text-white font-medium py-3">GPU dedicada con Ollama</td>
                  </tr>
                  <tr>
                    <td className="text-gray-300 py-3 pr-4">Framework</td>
                    <td className="text-white font-medium py-3">Haystack 2.x (pipeline RAG)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Training Data */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
              Fuentes de Conocimiento
            </h2>
            <p className="text-gray-400 text-sm mb-4">
              ominis-2.0 se alimenta de dos vertientes: datos de entrenamiento y datos en tiempo real vía RAG.
            </p>
            <div className="overflow-x-auto mb-6">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Fuente</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3 pr-4">Volumen</th>
                    <th className="text-left text-gray-400 text-sm font-medium py-3">Tipo</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">PubMed Central (Open Access)</td>
                    <td className="text-white font-medium py-3 pr-4">~3,000,000 artículos</td>
                    <td className="text-gray-400 py-3">Entrenamiento + RAG</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Resúmenes médicos especializados</td>
                    <td className="text-white font-medium py-3 pr-4">~30,000,000</td>
                    <td className="text-gray-400 py-3">Entrenamiento</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Guías de práctica clínica</td>
                    <td className="text-white font-medium py-3 pr-4">~50,000</td>
                    <td className="text-gray-400 py-3">Entrenamiento</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Fuentes y datasets curados por FUNSALUD</td>
                    <td className="text-white font-medium py-3 pr-4">+1,400 fuentes</td>
                    <td className="text-gray-400 py-3">RAG (tiempo real)</td>
                  </tr>
                  <tr className="border-b border-white/5">
                    <td className="text-gray-300 py-3 pr-4">Búsqueda web (DuckDuckGo)</td>
                    <td className="text-white font-medium py-3 pr-4">En tiempo real</td>
                    <td className="text-gray-400 py-3">RAG (tiempo real)</td>
                  </tr>
                  <tr>
                    <td className="text-gray-300 py-3 pr-4">PubMed API</td>
                    <td className="text-white font-medium py-3 pr-4">+36M artículos indexados</td>
                    <td className="text-gray-400 py-3">RAG (tiempo real)</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="bg-white/5 rounded-xl p-4 border border-white/5">
              <p className="text-gray-300 text-sm">
                <strong className="text-white">Datos de entrenamiento:</strong> Más de 33 millones de documentos 
                y 17.5 mil millones de tokens de texto médico especializado.
              </p>
              <p className="text-gray-300 text-sm mt-2">
                <strong className="text-white">RAG en tiempo real:</strong> Más de 1,400 fuentes curadas por FUNSALUD, 
                búsqueda web, y acceso a la base completa de PubMed — todo consultado en cada pregunta para 
                ofrecer respuestas actualizadas con citas verificables.
              </p>
            </div>
          </div>

          {/* Medical Domains */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              Dominios Médicos
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
                "Epidemiología",
                "Ginecología",
                "Neumología",
                "Nefrología",
                "Políticas de Salud"
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

          {/* Capabilities */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              Capacidades
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Respuestas con citas</h4>
                  <p className="text-gray-400 text-xs">Cada afirmación puede incluir referencias verificables a las fuentes originales.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Búsqueda multi-fuente</h4>
                  <p className="text-gray-400 text-xs">Consulta simultánea a base OMINIS, búsqueda web y PubMed en tiempo real.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Análisis de imágenes</h4>
                  <p className="text-gray-400 text-xs">Interpretación de imágenes médicas, gráficas y documentos mediante modelo de visión dedicado.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Generación de tablas</h4>
                  <p className="text-gray-400 text-xs">Datos comparativos renderizados como tablas con opción de copiar y descargar como CSV.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Streaming en tiempo real</h4>
                  <p className="text-gray-400 text-xs">Respuestas desplegadas progresivamente con formato markdown mientras el modelo genera.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 bg-white/5 rounded-xl p-4">
                <svg className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <div>
                  <h4 className="text-white text-sm font-semibold mb-1">Especializado en español</h4>
                  <p className="text-gray-400 text-xs">Instruction-tuning optimizado para comprensión y generación de texto médico en español.</p>
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
                <h3 className="text-white font-semibold mb-2">Infraestructura 100% administrada por FUNSALUD</h3>
                <p className="text-gray-400 text-sm">
                  Todos los datos son hospedados en México por AWS en su centro de datos en Querétaro, QRO 
                  (región mx-central-1). Las inferencias que requieren GPU dedicada viajan a un centro de datos 
                  administrado exclusivamente por FUNSALUD. Todas las inferencias son procesadas por 
                  ominis-2.0 — ningún dato es compartido ni inferido con modelos de IA de terceros 
                  como Google (Gemini), OpenAI (GPT), Anthropic (Claude) o Meta (Llama).
                </p>
              </div>
              <div>
                <h3 className="text-white font-semibold mb-2">Sin modelos de terceros</h3>
                <p className="text-gray-400 text-sm">
                  ominis-2.0 opera de forma completamente independiente. No se envían datos a APIs 
                  externas de IA. El modelo corre en infraestructura propia a través de Ollama, 
                  garantizando soberanía total sobre los datos.
                </p>
              </div>
              <div>
                <h3 className="text-white font-semibold mb-2">Curación humana</h3>
                <p className="text-gray-400 text-sm">
                  Todas las fuentes de información del sistema RAG son curadas y verificadas por 
                  un equipo humano de especialistas en salud, asegurando la calidad y relevancia 
                  de la información.
                </p>
              </div>
            </div>
          </div>

          {/* Tech Stack */}
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 md:p-8 mb-8">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              Stack Tecnológico
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { name: "Haystack 2.x", desc: "Pipeline RAG" },
                { name: "Ollama", desc: "Inferencia LLM" },
                { name: "pgvector", desc: "Vector store" },
                { name: "PostgreSQL", desc: "Base de datos" },
                { name: "FastAPI", desc: "Backend API" },
                { name: "Next.js", desc: "Frontend" },
                { name: "AWS mx-central-1", desc: "Infraestructura" },
                { name: "Nginx + PM2", desc: "Producción" },
              ].map((tech, i) => (
                <div key={i} className="bg-white/5 border border-white/5 rounded-lg px-3 py-2.5 text-center">
                  <div className="text-white text-sm font-medium">{tech.name}</div>
                  <div className="text-gray-500 text-xs">{tech.desc}</div>
                </div>
              ))}
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
                href="mailto:ominis@funsalud.org.mx?subject=Solicitud%20de%20acceso%20a%20ominis-2.0"
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

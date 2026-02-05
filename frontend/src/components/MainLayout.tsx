"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";

interface Source {
  title: string;
  url: string;
  score?: number;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

const API_ENDPOINT = process.env.NEXT_PUBLIC_API_ENDPOINT || "https://api.ominis.org/query";
const TEST_ENDPOINT = "https://api.ominis.org/test";

export default function MainLayout() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "¡Hola! Soy el asistente de OMINIS para la investigación en salud. Puedo responder preguntas sobre el sistema de salud en México, fuentes de datos, estudios y proyectos de investigación. ¿En qué puedo ayudarte?",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const generateId = () => Math.random().toString(36).substring(2, 9);

  // Test connectivity on mount
  useEffect(() => {
    const testConnection = async () => {
      try {
        console.log("Testing connection to:", TEST_ENDPOINT);
        const response = await fetch(TEST_ENDPOINT);
        const data = await response.json();
        console.log("Connection test result:", data);
      } catch (error) {
        console.error("Connection test failed:", error);
      }
    };
    testConnection();
  }, []);

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: question,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Long timeout for CPU inference (2 minutes)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);
      
      console.log("Fetching from:", API_ENDPOINT);
      
      // Build chat history for context (last 6 messages, excluding welcome)
      const history = messages
        .filter(m => m.id !== "welcome")
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));
      
      const response = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: question,
          history: history,
          num_sources: 5,
        }),
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);

      if (!response.ok) {
        const text = await response.text();
        console.error("API Error:", response.status, text);
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      const data = await response.json();
      console.log("API Response:", data);

      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: data.answer || "No pude generar una respuesta.",
        sources: data.sources,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Fetch error:", error);
      let errorText = "";
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorText = "La solicitud tardó demasiado (>2 min). El servidor puede estar ocupado.";
        } else {
          errorText = error.message;
        }
      }
      const errorMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: `Lo siento, hubo un error: ${errorText}. Por favor intenta de nuevo.`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const suggestedQuestions = [
    "¿Qué fuentes de datos de salud hay en México?",
    "¿Cómo funciona el sistema de salud mexicano?",
    "¿Qué estudios hay sobre el paciente digital?",
  ];

  return (
    <section className="min-h-screen pt-16 relative">
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

      {/* Content */}
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Main Grid: Chat Left, Info Right */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Chat */}
          <div className="lg:col-span-7 order-2 lg:order-1">
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden h-[600px] flex flex-col">
              {/* Chat Header */}
              <div className="bg-white/5 border-b border-white/10 px-4 py-3 flex items-center gap-3">
                <Image
                  src="/icon.png"
                  alt="OMINIS AI"
                  width={32}
                  height={32}
                  className="rounded-lg"
                />
                <div>
                  <h2 className="text-white font-semibold text-sm">OMINIS AI</h2>
                  <p className="text-gray-400 text-xs">Asistente para la Investigación en Salud</p>
                </div>
              </div>

              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] ${
                        message.role === "user"
                          ? "bg-blue-600 text-white rounded-2xl rounded-br-sm"
                          : "bg-white/10 text-gray-100 rounded-2xl rounded-bl-sm"
                      } p-3`}
                    >
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>

                      {/* Sources */}
                      {message.sources && message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-white/10">
                          <p className="text-blue-300 text-xs font-medium mb-2">📚 Fuentes:</p>
                          <ul className="space-y-1">
                            {message.sources.map((source, i) => (
                              <li key={i} className="text-xs">
                                <a
                                  href={source.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-400 hover:text-blue-300 transition-colors hover:underline"
                                >
                                  [{i + 1}] {source.title}
                                </a>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Loading indicator */}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 text-gray-100 rounded-2xl rounded-bl-sm p-3">
                      <div className="flex items-center gap-2">
                        <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                        <span className="text-gray-300 text-xs">Investigando en más de 1,400 fuentes curadas...</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Suggested Questions */}
              {messages.length === 1 && (
                <div className="px-4 pb-2">
                  <div className="flex flex-wrap gap-2">
                    {suggestedQuestions.map((q, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          setInput(q);
                          inputRef.current?.focus();
                        }}
                        className="text-xs bg-white/5 hover:bg-white/10 text-gray-300 px-3 py-1.5 rounded-full transition-colors border border-white/10"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Input Area */}
              <div className="p-3 border-t border-white/10 bg-black/20">
                <div className="flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Escribe tu pregunta..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-full px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                    disabled={isLoading}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={isLoading || !input.trim()}
                    className="bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            {/* Disclaimer under chat */}
            <p className="text-gray-500 text-xs text-center mt-3">
              ⚠️ Herramienta de apoyo para investigadores. Verifica siempre la información con las fuentes originales.
            </p>
          </div>

          {/* Right Column: Info Cards */}
          <div className="lg:col-span-5 order-1 lg:order-2 space-y-4">
            {/* FUNSALUD - Top */}
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-4">
              <div className="flex items-center gap-4 mb-3">
                <Image
                  src="/funsalud-logo.png"
                  alt="FUNSALUD"
                  width={100}
                  height={40}
                  className="h-10 w-auto flex-shrink-0"
                />
                <div>
                  <p className="text-gray-400 text-xs mb-0.5">Una iniciativa de</p>
                  <Link
                    href="https://funsalud.org.mx"
                    target="_blank"
                    className="text-white font-medium text-sm hover:text-blue-400 transition-colors"
                  >
                    Fundación Mexicana para la Salud A.C.
                  </Link>
                </div>
              </div>
              <p className="text-gray-400 text-xs">
                OMINIS es una iniciativa sin fines de lucro para facilitar la investigación en salud 
                apoyada por inteligencia artificial y respaldada por miles de fuentes de información 
                curadas por un equipo humano de curadores especializados.
              </p>
            </div>

            {/* Technology & Contact Card */}
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-4">
              <div className="flex items-start gap-2 mb-3">
                <span className="text-green-400 text-lg">🇲🇽</span>
                <div>
                  <h3 className="text-white font-semibold text-sm">Potenciado por ominis-2.0</h3>
                  <p className="text-gray-400 text-xs mt-1">
                    Primer modelo de IA generativa mexicano especializado en salud. No usamos OpenAI, Gemini, Claude ni Llama. 
                    Tus consultas y datos nunca salen del territorio mexicano.
                  </p>
                </div>
              </div>
              <div className="border-t border-white/10 pt-3 mt-3">
                <h4 className="text-white font-medium text-xs mb-1">¿Tienes comentarios?</h4>
                <p className="text-gray-400 text-xs mb-2">
                  Estamos mejorando OMINIS constantemente. Ayúdanos a perfeccionarlo compartiéndonos 
                  cualquier comportamiento inesperado o ideas de mejora.
                </p>
                <a
                  href="mailto:curacion-ominis@funsalud.org.mx"
                  className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                >
                  curacion-ominis@funsalud.org.mx
                </a>
              </div>
              <div className="border-t border-white/10 pt-3 mt-3">
                <h4 className="text-white font-medium text-xs mb-1">¿Quieres usar ominis-2.0?</h4>
                <p className="text-gray-400 text-xs mb-2">
                  Si deseas integrar el modelo ominis-2.0 en una aplicación de salud en México, 
                  contáctanos para solicitar acceso.
                </p>
                <a
                  href="mailto:curacion-ominis@funsalud.org.mx"
                  className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                >
                  curacion-ominis@funsalud.org.mx
                </a>
              </div>
            </div>

            {/* ROCLab Card - Bottom, smaller */}
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden hover:bg-white/10 transition-all">
              <div className="flex gap-4 p-4">
                <div className="relative w-24 h-20 flex-shrink-0 rounded-lg overflow-hidden">
                  <Image
                    src="/roclab-preview.png"
                    alt="ROCLab"
                    fill
                    className="object-cover"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-white font-semibold text-sm mb-1">ROCLab: Machine learning sin código</h3>
                  <p className="text-gray-400 text-xs mb-2 line-clamp-2">
                    Análisis de datasets y optimización de curvas ROC con IA.
                  </p>
                  <Link
                    href="https://roclab.ominis.org"
                    target="_blank"
                    className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 text-xs font-medium transition-colors"
                  >
                    Probar ahora
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Feature badges - below columns */}
        <div className="flex flex-wrap justify-center gap-3 mt-8">
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
            <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span className="text-gray-300 text-xs">100% Datos en México</span>
          </div>
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            <span className="text-gray-300 text-xs">Fuentes Verificadas</span>
          </div>
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span className="text-gray-300 text-xs">Sin almacenamiento de consultas</span>
          </div>
        </div>
      </div>
    </section>
  );
}

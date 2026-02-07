"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";

interface Source {
  title: string;
  url: string;
  score?: number;
  type?: "rag" | "web" | "pubmed";
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  images?: string[];
}

interface ModelOption {
  id: string;
  displayName: string;
  description: string;
  isDefault: boolean;
}

// ominis-2.0 (Mexican LLM by FUNSALUD)
// Data is stored in Mexico (S3 mx-central-1), no 3rd party models
// Inference runs on GPU for speed via /api/query-stream

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
  const [loadingStatus, setLoadingStatus] = useState("");
  const [ragSearchEnabled, setRagSearchEnabled] = useState(true);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [pubmedSearchEnabled, setPubmedSearchEnabled] = useState(true);
  const [uploadedImages, setUploadedImages] = useState<Array<{ data: string; name: string }>>([]);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([
    { id: "ominis-2.0", displayName: "Ominis 2.0 (BioMistral)", description: "Medical-specialized LLM", isDefault: true },
  ]);
  const [selectedModel, setSelectedModel] = useState<string>("ominis-2.0");
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);

  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
    // Always refocus the input after messages change
    inputRef.current?.focus();
  }, [messages]);

  // Also scroll when loading status changes (keeps spinner in view)
  useEffect(() => {
    if (isLoading) scrollToBottom();
  }, [isLoading, loadingStatus]);

  const generateId = () => Math.random().toString(36).substring(2, 9);

  // Extract sources from URLs embedded in LLM-generated text
  // When the LLM includes URLs (e.g. <https://...> or standalone), auto-create Source objects
  const extractSourcesFromContent = (content: string): Source[] => {
    const sources: Source[] = [];
    const lines = content.split("\n");
    for (const line of lines) {
      // Match URLs in angle brackets: <https://...>
      const angleBracketMatch = line.match(/<(https?:\/\/[^>]+)>/);
      if (angleBracketMatch) {
        const url = angleBracketMatch[1];
        if (!sources.some(s => s.url === url)) {
          // Extract title from text before the URL on the same line
          const beforeUrl = line.slice(0, line.indexOf("<")).trim();
          let title = beforeUrl.replace(/^\[\d+\]\s*/, "").replace(/^\d+\.\s*/, "").replace(/[:\s]+$/, "").trim();
          if (!title || title.length < 3) {
            try { title = new URL(url).hostname; } catch { title = url; }
          }
          sources.push({ title, url, type: "web" });
        }
        continue; // Don't double-match standalone URL in same line
      }
      // Match standalone URLs (not in brackets)
      const standaloneMatch = line.match(/(?:^|\s)(https?:\/\/[^\s<>)]+)/);
      if (standaloneMatch) {
        const url = standaloneMatch[1];
        if (!sources.some(s => s.url === url)) {
          const beforeUrl = line.slice(0, line.indexOf("http")).trim();
          let title = beforeUrl.replace(/^\[\d+\]\s*/, "").replace(/^\d+\.\s*/, "").replace(/[:\s]+$/, "").trim();
          if (!title || title.length < 3) {
            try { title = new URL(url).hostname; } catch { title = url; }
          }
          sources.push({ title, url, type: "web" });
        }
      }
    }
    return sources;
  };

  // Merge existing sources with any URLs found in content that aren't already covered
  // Extracted URL sources go FIRST since the LLM references them as [1], [2], etc.
  const getEffectiveSources = (content: string, existingSources?: Source[]): Source[] | undefined => {
    const extracted = extractSourcesFromContent(content);
    if (extracted.length === 0) return existingSources;
    if (!existingSources || existingSources.length === 0) return extracted.length > 0 ? extracted : undefined;
    // Extracted URL sources first (match LLM's in-text [1], [2], etc.)
    // Then add existing (RAG/backend) sources that aren't duplicates
    const result = [...extracted];
    for (const existing of existingSources) {
      const alreadyCovered = result.some(s =>
        s.url === existing.url || existing.url.includes(s.url) || s.url.includes(existing.url.replace(/\/$/, ""))
      );
      if (!alreadyCovered) result.push(existing);
    }
    return result;
  };

  // Format content with citation references [1], [2], etc.
  const formatContentWithCitations = (content: string, sources?: Source[]) => {
    if (!sources || sources.length === 0) return content;

    let formattedContent = content;

    // Pre-process: on lines that contain URLs, strip leading [N] or N. numbering
    // This prevents duplicate citations since the URL will be converted to [N] below
    const lines = formattedContent.split("\n");
    formattedContent = lines.map(line => {
      if (/^\[\d+\]/.test(line) && (/<https?:\/\/[^>]+>/.test(line) || /https?:\/\/[^\s<>)]+/.test(line))) {
        return line.replace(/^\[\d+\]\s*/, "");
      }
      if (/^\d+\.\s/.test(line) && (/<https?:\/\/[^>]+>/.test(line) || /https?:\/\/[^\s<>)]+/.test(line))) {
        return line.replace(/^\d+\.\s*/, "");
      }
      return line;
    }).join("\n");

    // Replace URLs with source references
    // Handle URLs in angle brackets like <https://...>
    formattedContent = formattedContent.replace(
      /<(https?:\/\/[^>]+)>/gi,
      (_, url) => {
        const sourceIndex = sources.findIndex(s => 
          s.url === url || url.includes(s.url) || s.url.includes(url.replace(/\/$/, ""))
        );
        if (sourceIndex !== -1) {
          return `[${sourceIndex + 1}]`;
        }
        return ""; // Remove URL if no matching source
      }
    );

    // Handle URLs in parentheses like (https://...)
    formattedContent = formattedContent.replace(
      /\s*\((https?:\/\/[^\s)]+)\)/gi,
      (_, url) => {
        const sourceIndex = sources.findIndex(s => 
          s.url === url || url.includes(s.url) || s.url.includes(url.replace(/\/$/, ""))
        );
        if (sourceIndex !== -1) {
          return ` [${sourceIndex + 1}]`;
        }
        return ""; // Remove URL if no matching source
      }
    );

    // Handle standalone URLs (not in brackets or parentheses)
    formattedContent = formattedContent.replace(
      /\s*(https?:\/\/[^\s<>)]+)/gi,
      (_, url) => {
        const sourceIndex = sources.findIndex(s => 
          s.url === url || url.includes(s.url) || s.url.includes(url.replace(/\/$/, ""))
        );
        if (sourceIndex !== -1) {
          return ` [${sourceIndex + 1}]`;
        }
        return ""; // Remove URL if no matching source
      }
    );

    // Replace patterns like "(Fuente 1, Fuente 2)" or "(Fuente 1)" with "[1][2]" or "[1]"
    formattedContent = formattedContent.replace(
      /\(Fuente\s*(\d+)(?:\s*,\s*Fuente\s*(\d+))*\)/gi,
      (match) => {
        const numbers = match.match(/\d+/g);
        if (numbers) {
          return numbers.map((n) => `[${n}]`).join("");
        }
        return match;
      }
    );

    // Also handle "[Fuente 1]" format
    formattedContent = formattedContent.replace(
      /\[Fuente\s*(\d+)\]/gi,
      (_, num) => `[${num}]`
    );

    // Handle "Fuente 1" without parentheses (standalone)
    formattedContent = formattedContent.replace(
      /Fuente\s+(\d+)/gi,
      (_, num) => `[${num}]`
    );

    // Handle author-style citations like [Author, et al., Year] or [Author et al., Year]
    // These are common when PubMed results are summarized by the LLM
    // Strategy: collect all author citations in order, map sequentially to sources
    const authorCitationPattern = /\[([A-Z][a-zA-ZÀ-ÿ]+(?:\s+[A-Z][a-zA-ZÀ-ÿ]*)*(?:\s*,?\s*et\s*al\.?)?)(?:\s*,?\s*\(?(\d{4})\)?)?\]/g;
    let authorCitationIndex = 0;
    const usedSourceIndices = new Set<number>();
    formattedContent = formattedContent.replace(
      authorCitationPattern,
      (match, authorPart: string) => {
        // Skip if it looks like an already-converted numeric citation
        if (/^\[\d+\]$/.test(match)) return match;
        
        // Extract the first author surname for matching
        const surname = authorPart.split(/[\s,]/)[0].toLowerCase();
        
        // Try to find a matching source by author surname in title
        let sourceIdx = sources.findIndex((s, i) => {
          if (usedSourceIndices.has(i)) return false;
          const titleWords = s.title.toLowerCase().split(/[\s,.:;]+/);
          return titleWords.some(w => w === surname || (surname.length >= 4 && w.startsWith(surname.slice(0, 4))));
        });
        
        // If no match by name, assign sequentially based on appearance order
        if (sourceIdx === -1 && authorCitationIndex < sources.length) {
          sourceIdx = authorCitationIndex;
        }
        
        authorCitationIndex++;
        if (sourceIdx !== -1 && sourceIdx < sources.length) {
          usedSourceIndices.add(sourceIdx);
          return `[${sourceIdx + 1}]`;
        }
        return match; // Keep original if no match found
      }
    );

    // Clean up extra spaces and empty parentheses (but preserve newlines)
    formattedContent = formattedContent.replace(/\(\s*\)/g, "");
    formattedContent = formattedContent.replace(/[^\S\n]{2,}/g, " "); // collapse spaces but NOT newlines
    formattedContent = formattedContent.replace(/\s+\./g, ".");
    formattedContent = formattedContent.replace(/\s+,/g, ",");

    return formattedContent.trim();
  };

  // Render a citation capsule - maps [N] to source by ref_num or array index
  const renderCitationCapsule = (sourceNum: string, sources: Source[], key: string | number) => {
    const num = parseInt(sourceNum, 10);
    // First try to find by ref_num (Perplexity-style backend numbering)
    let source = sources.find((s: any) => s.ref_num === num);
    // Fallback to array index
    if (!source) {
      source = sources[num - 1];
    }
    if (source && source.url) {
      return (
        <a
          key={key}
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center w-3.5 h-3.5 text-[9px] font-medium bg-blue-500 hover:bg-blue-400 text-white rounded-full align-super mx-0.5 transition-colors"
          title={source.title}
        >
          {sourceNum}
        </a>
      );
    }
    // No URL or source not found - render grey (non-clickable)
    return (
      <span
        key={key}
        className="inline-flex items-center justify-center w-3.5 h-3.5 text-[9px] font-medium bg-gray-500 text-white rounded-full align-super mx-0.5"
        title="Fuente no disponible"
      >
        {sourceNum}
      </span>
    );
  };

  // Render inline text with citations and markdown bold/italic
  const renderInlineContent = (text: string, sources: Source[], keyPrefix: string) => {
    // Split by citations [N], bold **text**, and italic *text*
    const parts = text.split(/(\[\d+\]|\*\*[^*]+\*\*|\*[^*]+\*)/g);
    return parts.map((part, i) => {
      const citationMatch = part.match(/^\[(\d+)\]$/);
      if (citationMatch) {
        return renderCitationCapsule(citationMatch[1], sources, `${keyPrefix}-${i}`);
      }
      const boldMatch = part.match(/^\*\*(.+)\*\*$/);
      if (boldMatch) {
        return <strong key={`${keyPrefix}-${i}`} className="font-semibold text-white">{boldMatch[1]}</strong>;
      }
      const italicMatch = part.match(/^\*(.+)\*$/);
      if (italicMatch) {
        return <em key={`${keyPrefix}-${i}`}>{italicMatch[1]}</em>;
      }
      return <span key={`${keyPrefix}-${i}`}>{part}</span>;
    });
  };

  // Render content with clickable citation links, preserving paragraphs and formatting
  const renderContentWithCitations = (content: string, sources?: Source[]) => {
    const formattedContent = formatContentWithCitations(content, sources);
    
    if (!sources || sources.length === 0) {
      // Still render paragraphs and basic markdown even without sources
      const paragraphs = formattedContent.split(/\n{2,}/);
      if (paragraphs.length <= 1) {
        // Single paragraph - render with line breaks
        const lines = formattedContent.split("\n");
        return (
          <span>
            {lines.map((line, i) => (
              <span key={i}>
                {line}
                {i < lines.length - 1 && <br />}
              </span>
            ))}
          </span>
        );
      }
      return (
        <div className="space-y-3">
          {paragraphs.map((para, i) => {
            const trimmed = para.trim();
            if (!trimmed) return null;
            const lines = trimmed.split("\n");
            return (
              <p key={i}>
                {lines.map((line, j) => (
                  <span key={j}>
                    {line}
                    {j < lines.length - 1 && <br />}
                  </span>
                ))}
              </p>
            );
          })}
        </div>
      );
    }

    // Split into paragraphs (double newline)
    const paragraphs = formattedContent.split(/\n{2,}/);

    return (
      <div className="space-y-3">
        {paragraphs.map((para, pIdx) => {
          const trimmed = para.trim();
          if (!trimmed) return null;

          // Check for markdown headers (### Header, ## Header, # Header)
          const headerMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
          if (headerMatch) {
            const level = headerMatch[1].length;
            const headerText = headerMatch[2];
            const className = level === 1
              ? "text-base font-bold text-white mt-2"
              : level === 2
                ? "text-sm font-semibold text-white mt-1"
                : "text-sm font-medium text-gray-200 mt-1";
            return (
              <div key={pIdx} className={className}>
                {renderInlineContent(headerText, sources, `h-${pIdx}`)}
              </div>
            );
          }

          // Handle lines within a paragraph (single newlines = line breaks)
          const lines = trimmed.split("\n");
          return (
            <p key={pIdx}>
              {lines.map((line, lIdx) => {
                const trimmedLine = line.trim();
                if (!trimmedLine) return null;

                // Check for bullet points (- item or * item or • item)
                const bulletMatch = trimmedLine.match(/^[-*•]\s+(.+)$/);
                if (bulletMatch) {
                  return (
                    <span key={lIdx} className="block ml-3 relative">
                      <span className="absolute -left-3 text-gray-500">•</span>
                      {renderInlineContent(bulletMatch[1], sources, `p${pIdx}-l${lIdx}`)}
                      {lIdx < lines.length - 1 && <br />}
                    </span>
                  );
                }

                // Check for numbered list (1. item, 2. item)
                const numberedMatch = trimmedLine.match(/^(\d+)\.\s+(.+)$/);
                if (numberedMatch) {
                  return (
                    <span key={lIdx} className="block ml-4 relative">
                      <span className="absolute -left-4 text-gray-400 text-xs">{numberedMatch[1]}.</span>
                      {renderInlineContent(numberedMatch[2], sources, `p${pIdx}-l${lIdx}`)}
                      {lIdx < lines.length - 1 && <br />}
                    </span>
                  );
                }

                return (
                  <span key={lIdx}>
                    {renderInlineContent(trimmedLine, sources, `p${pIdx}-l${lIdx}`)}
                    {lIdx < lines.length - 1 && <br />}
                  </span>
                );
              })}
            </p>
          );
        })}
      </div>
    );
  };

  // Handle image upload (multiple files)
  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach((file) => {
        if (file.type.startsWith("image/")) {
          const reader = new FileReader();
          reader.onload = (event) => {
            setUploadedImages((prev) => [
              ...prev,
              { data: event.target?.result as string, name: file.name },
            ]);
          };
          reader.readAsDataURL(file);
        }
      });
    }
    setShowPlusMenu(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Handle paste event for images
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith("image/")) {
          const file = items[i].getAsFile();
          if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
              setUploadedImages((prev) => [
                ...prev,
                { data: event.target?.result as string, name: "Imagen pegada" },
              ]);
            };
            reader.readAsDataURL(file);
          }
        }
      }
    }
  };

  // Remove uploaded image by index
  const removeImage = (index: number) => {
    setUploadedImages((prev) => prev.filter((_, i) => i !== index));
  };

  // Clear all images
  const clearAllImages = () => {
    setUploadedImages([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Fetch available models from backend
  useEffect(() => {
    const fetchModels = async () => {
      try {
        // Try fetching models list from the backend
        const modelsRes = await fetch(
          (process.env.NEXT_PUBLIC_STRAPI_URL || "http://localhost:8000") + "/v1/models"
        ).catch(() => null);
        if (modelsRes && modelsRes.ok) {
          const data = await modelsRes.json();
          if (data.models?.length > 0) {
            setAvailableModels(data.models);
            if (data.default) setSelectedModel(data.default);
          }
        }
      } catch {
        // Silently keep defaults if backend is unreachable
      }
    };
    fetchModels();
  }, []);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (plusMenuRef.current && !plusMenuRef.current.contains(event.target as Node)) {
        setShowPlusMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const sendMessage = async () => {
    const question = input.trim();
    if ((!question && uploadedImages.length === 0) || isLoading) return;

    // Build user message content (with image indicator if present)
    const imageNames = uploadedImages.map((img) => img.name).join(", ");
    const messageContent = uploadedImages.length > 0
      ? `${question}${question ? "\n" : ""}[${uploadedImages.length} imagen${uploadedImages.length > 1 ? "es" : ""} adjunta${uploadedImages.length > 1 ? "s" : ""}: ${imageNames}]`
      : question;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: messageContent,
      images: uploadedImages.length > 0 ? uploadedImages.map((img) => img.data) : undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const currentImages = uploadedImages.map((img) => img.data);
    const currentRagSearch = ragSearchEnabled;
    const currentWebSearch = webSearchEnabled;
    const currentPubmedSearch = pubmedSearchEnabled;
    clearAllImages(); // Clear images after capturing
    setIsLoading(true);
    setLoadingStatus("Analizando...");

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 120000); // 120s timeout for streaming

      // Build chat history for context
      const history = messages
        .filter(m => m.id !== "welcome")
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      // Use streaming endpoint
      
      const response = await fetch("/api/query-stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: question || "Describe esta imagen",
          history: history,
          images: currentImages.length > 0 ? currentImages : undefined,
          model: selectedModel,
          rag_search: currentRagSearch,
          web_search: currentWebSearch,
          pubmed_search: currentPubmedSearch,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new Error(`HTTP ${response.status}`);
      }

      // Read the SSE stream
      const reader = response.body?.getReader();
      if (!reader) {
        clearTimeout(timeoutId);
        throw new Error("No response body");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let receivedData = false;
      let streamedContent = "";
      let streamedSources: Source[] = [];
      const assistantId = generateId();
      let messageAdded = false;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // Clear timeout once we start receiving data
          if (!receivedData) {
            receivedData = true;
            clearTimeout(timeoutId);
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const jsonStr = line.slice(6);
              if (!jsonStr.trim()) continue;

              try {
                const eventData = JSON.parse(jsonStr);

                if (eventData.type === "status") {
                  setLoadingStatus(eventData.message);

                } else if (eventData.type === "chunk") {
                  // Token-by-token streaming: append text as it arrives
                  streamedContent += eventData.text || "";
                  if (!messageAdded) {
                    // First chunk: create the assistant message
                    messageAdded = true;
                    setIsLoading(false);
                    setLoadingStatus("");
                    const newMsg: Message = {
                      id: assistantId,
                      role: "assistant",
                      content: streamedContent,
                    };
                    setMessages((prev) => [...prev, newMsg]);
                  } else {
                    // Subsequent chunks: update content in-place
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, content: streamedContent }
                          : m
                      )
                    );
                  }

                } else if (eventData.type === "sources") {
                  // RAG sources arrived (may come during or after streaming)
                  if (eventData.sources && eventData.sources.length > 0) {
                    streamedSources = eventData.sources;
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, sources: streamedSources }
                          : m
                      )
                    );
                  }

                } else if (eventData.type === "done") {
                  // Final event: ensure message is complete
                  const finalContent = eventData.answer || streamedContent || "No pude generar una respuesta.";
                  const finalSources = eventData.sources?.length > 0 ? eventData.sources : streamedSources;

                  if (!messageAdded) {
                    // Fallback: no chunks were sent (legacy protocol)
                    const assistantMessage: Message = {
                      id: assistantId,
                      role: "assistant",
                      content: finalContent,
                      sources: finalSources.length > 0 ? finalSources : undefined,
                    };
                    setMessages((prev) => [...prev, assistantMessage]);
                  } else {
                    // Update with final content and sources
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, content: finalContent, sources: finalSources.length > 0 ? finalSources : m.sources }
                          : m
                      )
                    );
                  }

                  setIsLoading(false);
                  setLoadingStatus("");
                  inputRef.current?.focus();
                  return;

                } else if (eventData.type === "error") {
                  throw new Error(eventData.message);
                }
              } catch (parseError) {
                // Re-throw actual errors
                if (parseError instanceof Error && parseError.message === (JSON.parse(jsonStr) as { message?: string })?.message) {
                  throw parseError;
                }
              }
            }
          }
        }

        // Stream ended without a done event: finalize with what we have
        if (streamedContent && !messageAdded) {
          const assistantMessage: Message = {
            id: assistantId,
            role: "assistant",
            content: streamedContent,
            sources: streamedSources.length > 0 ? streamedSources : undefined,
          };
          setMessages((prev) => [...prev, assistantMessage]);
        }
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (error) {
      let errorText = "Error desconocido";
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorText = "Tiempo de espera agotado. Por favor intenta de nuevo.";
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
      setLoadingStatus("");
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

  // Start editing a message
  const startEditing = (messageId: string, content: string) => {
    // Remove the image indicator from content for editing
    const cleanContent = content.replace(/\n?\[\d+ imágenes? adjuntas?: [^\]]+\]/, "").trim();
    setEditingMessageId(messageId);
    setEditingText(cleanContent);
  };

  // Cancel editing
  const cancelEditing = () => {
    setEditingMessageId(null);
    setEditingText("");
  };

  // Submit edited message - sends directly without using input field
  const submitEdit = async () => {
    if (!editingMessageId || !editingText.trim() || isLoading) return;

    const question = editingText.trim();

    // Find the index of the message being edited
    const messageIndex = messages.findIndex(m => m.id === editingMessageId);
    if (messageIndex === -1) return;

    // Get the original message to preserve images if any
    const originalMessage = messages[messageIndex];

    // Remove this message and all messages after it
    const newMessages = messages.slice(0, messageIndex);

    // Clear editing state
    setEditingMessageId(null);
    setEditingText("");

    // Create the new user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: originalMessage.images && originalMessage.images.length > 0
        ? `${question}\n[${originalMessage.images.length} imagen${originalMessage.images.length > 1 ? "es" : ""} adjunta${originalMessage.images.length > 1 ? "s" : ""}]`
        : question,
      images: originalMessage.images,
    };

    setMessages([...newMessages, userMessage]);
    setIsLoading(true);
    setLoadingStatus("Analizando...");

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      const history = newMessages
        .filter(m => m.id !== "welcome")
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      // Use streaming endpoint
      const response = await fetch("/api/query-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          history: history,
          images: originalMessage.images || undefined,
          model: selectedModel,
          rag_search: ragSearchEnabled,
          web_search: webSearchEnabled,
          pubmed_search: pubmedSearchEnabled,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new Error(`HTTP ${response.status}`);
      }

      // Read the SSE stream
      const reader = response.body?.getReader();
      if (!reader) {
        clearTimeout(timeoutId);
        throw new Error("No response body");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let receivedData = false;
      let streamedContent = "";
      let streamedSources: Source[] = [];
      const assistantId = generateId();
      let messageAdded = false;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          if (!receivedData) {
            receivedData = true;
            clearTimeout(timeoutId);
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const jsonStr = line.slice(6);
              if (!jsonStr.trim()) continue;
              
              try {
                const eventData = JSON.parse(jsonStr);
                
                if (eventData.type === "status") {
                  setLoadingStatus(eventData.message);

                } else if (eventData.type === "chunk") {
                  streamedContent += eventData.text || "";
                  if (!messageAdded) {
                    messageAdded = true;
                    setIsLoading(false);
                    setLoadingStatus("");
                    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: streamedContent }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) => m.id === assistantId ? { ...m, content: streamedContent } : m)
                    );
                  }

                } else if (eventData.type === "sources") {
                  if (eventData.sources?.length > 0) {
                    streamedSources = eventData.sources;
                    setMessages((prev) =>
                      prev.map((m) => m.id === assistantId ? { ...m, sources: streamedSources } : m)
                    );
                  }

                } else if (eventData.type === "done") {
                  const finalContent = eventData.answer || streamedContent || "No pude generar una respuesta.";
                  const finalSources = eventData.sources?.length > 0 ? eventData.sources : streamedSources;

                  if (!messageAdded) {
                    setMessages((prev) => [...prev, {
                      id: assistantId, role: "assistant",
                      content: finalContent,
                      sources: finalSources.length > 0 ? finalSources : undefined,
                    }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) => m.id === assistantId
                        ? { ...m, content: finalContent, sources: finalSources.length > 0 ? finalSources : m.sources }
                        : m)
                    );
                  }
                  setIsLoading(false);
                  setLoadingStatus("");
                  inputRef.current?.focus();
                  return;

                } else if (eventData.type === "error") {
                  throw new Error(eventData.message);
                }
              } catch (parseError) {
                if (parseError instanceof Error && (parseError.message.startsWith("GPU") || parseError.message.startsWith("Connection"))) {
                  throw parseError;
                }
              }
            }
          }
        }
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (error) {
      let errorText = "Error desconocido";
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorText = "Tiempo de espera agotado. Por favor intenta de nuevo.";
        } else {
          errorText = error.message;
        }
      }
      const errorMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: `Lo siento, ocurrió un error: ${errorText}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoadingStatus("");
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  // Handle edit input keydown
  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitEdit();
    } else if (e.key === "Escape") {
      cancelEditing();
    }
  };

  // Get the last user message ID (for showing edit button)
  const lastUserMessageId = [...messages].reverse().find(m => m.role === "user")?.id;

  const suggestedQuestions = [
    "¿Cuál es la diferencia entre diabetes tipo 1 y tipo 2?",
    "¿Cuáles son las principales causas de muerte en México?",
    "¿Qué fuentes de datos de salud hay en México?",
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
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        {/* Main Grid: Chat Left, Info Right */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Chat */}
          <div className="lg:col-span-7 order-1 lg:order-1 flex flex-col" style={{ height: "calc(100vh - 7rem)" }}>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden flex flex-col h-full">
              {/* Chat Header */}
              <div className="bg-white/5 border-b border-white/10 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
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
                
                {/* Privacy Badge */}
                <div className="flex items-center gap-2 bg-green-900/30 border border-green-500/30 rounded-full px-3 py-1">
                  <span className="text-green-400 text-xs">🇲🇽</span>
                  <span className="text-green-300 text-xs hidden sm:inline">ominis-2.0</span>
                </div>
              </div>

              {/* Messages Area */}
              <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((message) => {
                  // Compute effective sources: merge backend sources with any URLs found in content
                  const effectiveSources = message.role === "assistant"
                    ? getEffectiveSources(message.content, message.sources)
                    : message.sources;

                  return (
                  <div
                    key={message.id}
                    className={`flex ${message.role === "user" ? "justify-end" : "justify-start"} group`}
                  >
                    {/* Edit button for last user message */}
                    {message.role === "user" && message.id === lastUserMessageId && !isLoading && editingMessageId !== message.id && (
                      <button
                        onClick={() => startEditing(message.id, message.content)}
                        className="opacity-0 group-hover:opacity-100 mr-2 self-center text-gray-400 hover:text-white transition-all"
                        title="Editar mensaje"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                    )}
                    <div
                      className={`max-w-[85%] ${
                        message.role === "user"
                          ? "bg-blue-600 text-white rounded-2xl rounded-br-sm"
                          : "bg-white/10 text-gray-100 rounded-2xl rounded-bl-sm"
                      } p-3`}
                    >
                      {/* User message images */}
                      {message.images && message.images.length > 0 && (
                        <div className={`mb-2 ${message.images.length > 1 ? "grid grid-cols-2 gap-2" : ""}`}>
                          {message.images.map((img, idx) => (
                            <img 
                              key={idx}
                              src={img} 
                              alt={`Imagen adjunta ${idx + 1}`} 
                              className="max-w-full max-h-48 rounded-lg object-contain cursor-pointer hover:opacity-80 transition-opacity"
                              onClick={() => setModalImage(img)}
                            />
                          ))}
                        </div>
                      )}

                      {/* Editing mode - inline */}
                      {editingMessageId === message.id ? (
                        <div>
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            onKeyDown={handleEditKeyDown}
                            onBlur={() => {
                              // Small delay to allow click on other elements
                              setTimeout(() => {
                                if (editingMessageId === message.id) {
                                  submitEdit();
                                }
                              }, 150);
                            }}
                            className="w-full bg-transparent text-sm text-white focus:outline-none resize-none leading-relaxed"
                            style={{ minHeight: "1.5em" }}
                            rows={Math.max(1, editingText.split("\n").length)}
                            autoFocus
                          />
                          <p className="text-[10px] text-white/50 mt-1">Enter para enviar · Esc para cancelar</p>
                        </div>
                      ) : (
                        <>
                          <div className="text-sm leading-relaxed">
                            {message.role === "assistant" 
                              ? renderContentWithCitations(message.content, effectiveSources)
                              : <p className="whitespace-pre-wrap">{message.content}</p>
                            }
                          </div>

                          {/* Sources - show all sources with backend ref numbers */}
                          {effectiveSources && effectiveSources.length > 0 && (() => {
                            // Use ref_num from backend (Perplexity-style) or fallback to index
                            const displaySources = effectiveSources
                              .map((source: any, i: number) => ({
                                ...source,
                                displayNum: source.ref_num || (i + 1),
                              }))
                              .filter((s: any) => s.url && s.url.length > 0);
                            
                            if (displaySources.length === 0) return null;
                            
                            return (
                              <div className="mt-3 pt-3 border-t border-white/10">
                                <p className="text-xs text-gray-400 mb-1">📚 Fuentes consultadas:</p>
                                <ul className="space-y-1">
                                  {displaySources.map((source: any) => (
                                    <li key={source.displayNum} className="text-xs">
                                      <a
                                        href={source.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-400 hover:text-blue-300 transition-colors hover:underline"
                                      >
                                        [{source.displayNum}] {source.title}
                                        {source.type === "pubmed" && " 🔬"}
                                        {source.type === "web" && " 🌐"}
                                      </a>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            );
                          })()}
                        </>
                      )}
                    </div>
                  </div>
                  );
                })}

                {/* Loading indicator */}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 text-gray-100 rounded-2xl rounded-bl-sm p-3">
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
                        {loadingStatus && (
                          <span className="text-gray-300 text-sm animate-pulse">{loadingStatus}</span>
                        )}
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
                {/* Images Preview */}
                {uploadedImages.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {uploadedImages.map((img, index) => (
                      <div key={index} className="relative group">
                        <img 
                          src={img.data} 
                          alt={img.name} 
                          className="h-12 w-12 object-cover rounded"
                        />
                        <button
                          onClick={() => removeImage(index)}
                          className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Eliminar"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Active features indicator */}
                {(ragSearchEnabled || webSearchEnabled || pubmedSearchEnabled || uploadedImages.length > 0 || selectedModel !== "ominis-2.0") && (
                  <div className="flex items-center gap-1.5 mb-2 text-xs flex-wrap">
                    {/* Model badge (shown when non-default model selected) */}
                    {selectedModel !== "ominis-2.0" && (
                      <span className="flex items-center gap-1 text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        {availableModels.find(m => m.id === selectedModel)?.displayName || selectedModel}
                      </span>
                    )}
                    {ragSearchEnabled && (
                      <span className="flex items-center gap-1 text-cyan-400 bg-cyan-500/10 pl-2 pr-1 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                        </svg>
                        Ominis
                        <button onClick={() => setRagSearchEnabled(false)} className="ml-0.5 hover:text-cyan-200 transition-colors" title="Desactivar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </span>
                    )}
                    {webSearchEnabled && (
                      <span className="flex items-center gap-1 text-blue-400 bg-blue-500/10 pl-2 pr-1 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                        </svg>
                        Web
                        <button onClick={() => setWebSearchEnabled(false)} className="ml-0.5 hover:text-blue-200 transition-colors" title="Desactivar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </span>
                    )}
                    {pubmedSearchEnabled && (
                      <span className="flex items-center gap-1 text-purple-400 bg-purple-500/10 pl-2 pr-1 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                        </svg>
                        PubMed
                        <button onClick={() => setPubmedSearchEnabled(false)} className="ml-0.5 hover:text-purple-200 transition-colors" title="Desactivar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </span>
                    )}
                    {uploadedImages.length > 0 && (
                      <span className="flex items-center gap-1 text-green-400 bg-green-500/10 px-2 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        {uploadedImages.length} imagen{uploadedImages.length > 1 ? "es" : ""}
                      </span>
                    )}
                  </div>
                )}

                {/* Input Row */}
                <div className="flex items-center gap-2">
                  {/* Hidden file input */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    onChange={handleImageUpload}
                    className="hidden"
                  />

                  {/* Plus button with dropdown menu */}
                  <div className="relative" ref={plusMenuRef}>
                    <button
                      onClick={() => setShowPlusMenu(!showPlusMenu)}
                      className={`text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-full transition-colors ${showPlusMenu ? "bg-white/10 text-white" : ""}`}
                      title="Opciones"
                      disabled={isLoading}
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                      </svg>
                    </button>

                    {/* Dropdown Menu */}
                    {showPlusMenu && (
                      <div className="absolute bottom-full left-0 mb-2 bg-[#1a2744] border border-white/10 rounded-xl shadow-xl py-2 min-w-[200px] z-50">
                        {/* Add files option */}
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className="w-full flex items-center gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                          Agregar imágenes
                        </button>

                        <div className="border-t border-white/10 my-1"></div>

                        {/* Model selector section */}
                        <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Modelo</div>
                        {availableModels.map((m) => (
                          <button
                            key={m.id}
                            onClick={() => setSelectedModel(m.id)}
                            className={`w-full flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors ${
                              selectedModel === m.id
                                ? "text-white bg-white/10"
                                : "text-gray-300 hover:bg-white/10 hover:text-white"
                            }`}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                              </svg>
                              <span className="truncate">{m.displayName}</span>
                            </div>
                            {selectedModel === m.id && (
                              <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                          </button>
                        ))}

                        <div className="border-t border-white/10 my-1"></div>

                        {/* Section header */}
                        <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Buscar en fuentes</div>

                        {/* Ominis RAG toggle */}
                        <button
                          onClick={() => setRagSearchEnabled(!ragSearchEnabled)}
                          className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm"
                        >
                          <div className="flex items-center gap-3">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                            </svg>
                            Ominis
                          </div>
                          <div className={`w-8 h-5 rounded-full transition-colors ${ragSearchEnabled ? "bg-cyan-500" : "bg-gray-600"} relative`}>
                            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${ragSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`}></div>
                          </div>
                        </button>

                        {/* Web search toggle */}
                        <button
                          onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                          className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm"
                        >
                          <div className="flex items-center gap-3">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                            </svg>
                            Web
                          </div>
                          <div className={`w-8 h-5 rounded-full transition-colors ${webSearchEnabled ? "bg-blue-500" : "bg-gray-600"} relative`}>
                            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${webSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`}></div>
                          </div>
                        </button>

                        {/* PubMed search toggle */}
                        <button
                          onClick={() => setPubmedSearchEnabled(!pubmedSearchEnabled)}
                          className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm"
                        >
                          <div className="flex items-center gap-3">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                            </svg>
                            PubMed
                          </div>
                          <div className={`w-8 h-5 rounded-full transition-colors ${pubmedSearchEnabled ? "bg-purple-500" : "bg-gray-600"} relative`}>
                            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${pubmedSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`}></div>
                          </div>
                        </button>
                      </div>
                    )}
                  </div>

                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    placeholder="Escribe tu pregunta..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-full px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-all"
                    disabled={isLoading}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={isLoading || (!input.trim() && uploadedImages.length === 0)}
                    className="bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
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
          <div className="lg:col-span-5 order-2 lg:order-2 space-y-4 flex flex-col">
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
                curadas por un equipo humano.
              </p>
            </div>

            {/* Technology & Contact Card */}
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-4">
              <div className="flex items-start gap-2 mb-3">
                <span className="text-green-400 text-lg">🇲🇽</span>
                <div>
                  <h3 className="text-white font-semibold text-sm">
                    Potenciado por{" "}
                    <Link href="/modelo" className="text-blue-400 hover:underline">ominis-2.0</Link>
                  </h3>
                  <p className="text-gray-400 text-xs mt-1">
                    Modelo de IA mexicano especializado en salud. Entrenado con protocolos, datos y artículos hospedados exclusivamente en México (S3 mx-central-1).{" "}
                    <strong className="text-green-400">No usamos modelos de terceros (OpenAI, Google, Anthropic, Meta).</strong>{" "}
                    Tus consultas son completamente efímeras: no almacenamos tus interacciones ni usamos tus datos para entrenar el modelo.{" "}
                    Infraestructura 100% administrada por FUNSALUD.{" "}
                    <Link href="/modelo" className="text-blue-400 hover:underline">Ver más →</Link>
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
                  href="mailto:ominis@funsalud.org.mx"
                  className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                >
                  ominis@funsalud.org.mx
                </a>
              </div>
              <div className="border-t border-white/10 pt-3 mt-3">
                <h4 className="text-white font-medium text-xs mb-1">¿Quieres usar ominis-2.0?</h4>
                <p className="text-gray-400 text-xs mb-2">
                  Si deseas integrar el modelo ominis-2.0 en una aplicación de salud en México, 
                  contáctanos para solicitar acceso.
                </p>
                <a
                  href="mailto:ominis@funsalud.org.mx"
                  className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                >
                  ominis@funsalud.org.mx
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

      {/* Image Modal */}
      {modalImage && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          onClick={() => setModalImage(null)}
        >
          <div className="relative max-w-full max-h-full">
            <button
              onClick={() => setModalImage(null)}
              className="absolute -top-10 right-0 text-white hover:text-gray-300 transition-colors"
            >
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <img 
              src={modalImage} 
              alt="Imagen ampliada" 
              className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </section>
  );
}

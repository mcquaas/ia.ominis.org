"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import ChatSidebar from "@/components/ChatSidebar";
import Footer from "@/components/Footer";
import * as chatService from "@/services/chat";
import type { ConversationSummary } from "@/services/chat";
import * as feedbackService from "@/services/feedback";

interface Source {
  title: string;
  url: string;
  score?: number;
  type?: "rag" | "web" | "pubmed";
  authors?: string;
  year?: string;
  journal?: string;
  ref_num?: number;
}

interface ChartData {
  id: string;
  type: string;
  title: string;
  image: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  images?: string[];
  charts?: ChartData[];
  isReport?: boolean;
  model?: string;  // e.g. "openscholar" from done event (shown as Investigación)
  dbMessageId?: number;  // DB id when persisted (for feedback)
}

interface ModelOption {
  id: string;
  displayName: string;
  description: string;
  isDefault: boolean;
}

const HISTORY_ENABLED_KEY = "ominis_history_enabled";

// ominis-2.0 (Mexican LLM by FUNSALUD)
// Data is stored in Mexico (S3 mx-central-1), no 3rd party models
// Inference runs on GPU for speed via /api/query-stream

interface MainLayoutProps {
  initialUuid?: string;
}

export default function MainLayout({ initialUuid }: MainLayoutProps = {}) {
  const router = useRouter();
  const { isAuthenticated, user } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState("");
  const [ragSearchEnabled, setRagSearchEnabled] = useState(true);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [pubmedSearchEnabled, setPubmedSearchEnabled] = useState(true);
  const [researchModeEnabled, setResearchModeEnabled] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<Array<{ data: string; name: string }>>([]);
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; ext: string; text: string; extracting: boolean }>>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [researchSteps, setResearchSteps] = useState<Array<{ action: string; detail: string; url?: string; result?: string; elapsed?: number }>>([]);
  const [researchProgress, setResearchProgress] = useState<{ found: number; read: number; totalSteps: number; elapsedSeconds: number } | null>(null);
  const [showResearchPanel, setShowResearchPanel] = useState(false);
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([
    { id: "ominis-2.0", displayName: "Ominis 2.0", description: "Modelo de IA especializado en salud", isDefault: true },
  ]);
  const [selectedModel, setSelectedModel] = useState<string>("ominis-2.0");
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [feedbackByMessageId, setFeedbackByMessageId] = useState<Record<string, "positive" | "negative">>({});
  const [feedbackModalMessageId, setFeedbackModalMessageId] = useState<string | null>(null);
  const [feedbackReasonCategory, setFeedbackReasonCategory] = useState<string | null>(null);
  const [feedbackReasonText, setFeedbackReasonText] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);

  // Chat history state — closed by default on mobile so it doesn't take space
  const [sidebarOpen, setSidebarOpen] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches) {
      setSidebarOpen(true);
    }
  }, []);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [historyEnabled, setHistoryEnabled] = useState(true);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // ─── Chat history helpers ───────────────────────────────────────

  // Load history enabled preference from localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(HISTORY_ENABLED_KEY);
      if (stored !== null) setHistoryEnabled(stored === "true");
    }
  }, []);

  // Fetch conversations when user logs in
  useEffect(() => {
    if (isAuthenticated && user) {
      loadConversations();
    } else {
      setConversations([]);
      setActiveConversationId(null);
    }
  }, [isAuthenticated, user]);

  // Load conversation from URL uuid when navigating to /c/[uuid]
  useEffect(() => {
    if (!initialUuid || !isAuthenticated) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await chatService.getConversationByUuid(initialUuid);
        if (cancelled) return;
        setActiveConversationId(detail.id);
        activeConversationIdRef.current = detail.id;
        const loaded: Message[] = [];
        for (const m of detail.messages) {
          loaded.push({
            id: String(m.id),
            role: m.role as "user" | "assistant",
            content: m.content,
            sources: m.sources as Source[] | undefined,
            images: m.has_images ? [] : undefined,
            dbMessageId: m.role === "assistant" ? m.id : undefined,
          });
        }
        setMessages(loaded);
      } catch (err) {
        console.warn("[Ominis] Failed to load conversation from URL:", err);
      }
    })();
    return () => { cancelled = true; };
  }, [initialUuid, isAuthenticated]);

  const loadConversations = useCallback(async () => {
    try {
      const res = await chatService.listConversations();
      setConversations(res.data);
    } catch (err) {
      console.warn("[Ominis] Failed to load conversations:", err);
    }
  }, []);

  const handleNewChat = useCallback(async () => {
    if (!isAuthenticated || !historyEnabled) {
      setActiveConversationId(null);
      activeConversationIdRef.current = null;
      setMessages([]);
      router.push("/c");
      inputRef.current?.focus();
      return;
    }
    try {
      const conv = await chatService.createConversation();
      // Set state immediately so persistMessages uses this conv if user sends before useEffect loads
      setActiveConversationId(conv.id);
      activeConversationIdRef.current = conv.id;
      setMessages([]);
      router.push(`/c/${conv.uuid}`);
      setSidebarOpen(false);
      await loadConversations();
      setTimeout(() => inputRef.current?.focus(), 100);
    } catch (err) {
      console.warn("[Ominis] Failed to create conversation:", err);
      setActiveConversationId(null);
      activeConversationIdRef.current = null;
      setMessages([]);
      router.push("/c");
    }
  }, [router, isAuthenticated, historyEnabled, loadConversations]);

  // Redirect /c to /c/[uuid] when authenticated and history enabled (create new conversation)
  useEffect(() => {
    if (initialUuid !== undefined || !isAuthenticated || !historyEnabled) return;
    let cancelled = false;
    (async () => {
      try {
        const conv = await chatService.createConversation();
        if (cancelled) return;
        setActiveConversationId(conv.id);
        activeConversationIdRef.current = conv.id;
        setMessages([]);
        router.replace(`/c/${conv.uuid}`);
        loadConversations();
      } catch (err) {
        console.warn("[Ominis] Failed to create conversation on /c:", err);
      }
    })();
    return () => { cancelled = true; };
  }, [initialUuid, isAuthenticated, historyEnabled, router, loadConversations]);

  const handleSelectConversation = useCallback((uuid: string) => {
    router.push(`/c/${uuid}`);
    setSidebarOpen(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [router]);

  const handleDeleteConversation = useCallback(async (id: number) => {
    try {
      await chatService.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConversationId === id) {
        setActiveConversationId(null);
        setMessages([]);
        router.push("/c");
      }
    } catch (err) {
      console.warn("[Ominis] Failed to delete conversation:", err);
    }
  }, [activeConversationId, router]);

  const handleRenameConversation = useCallback(async (id: number, newTitle: string) => {
    try {
      const updated = await chatService.updateConversation(id, { title: newTitle });
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: updated.title } : c))
      );
    } catch (err) {
      console.warn("[Ominis] Failed to rename conversation:", err);
    }
  }, []);

  const handleRegenerateTitle = useCallback(async (id: number) => {
    try {
      const updated = await chatService.regenerateTitle(id);
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: updated.title } : c))
      );
    } catch (err) {
      console.warn("[Ominis] Failed to regenerate title:", err);
    }
  }, []);

  const handleToggleHistory = useCallback((enabled: boolean) => {
    setHistoryEnabled(enabled);
    localStorage.setItem(HISTORY_ENABLED_KEY, String(enabled));
  }, []);

  /**
   * Persist a pair of messages (user + assistant) to the backend.
   * Creates a new conversation if none is active.
   */
  // Use a ref to always have the latest activeConversationId inside async callbacks
  const activeConversationIdRef = useRef(activeConversationId);
  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const persistMessages = useCallback(
    async (
      userContent: string,
      assistantContent: string,
      sources?: Source[],
      hasImages: boolean = false,
      assistantMessageId?: string,
    ) => {
      if (!isAuthenticated || !historyEnabled) return;

      try {
        let convId = activeConversationIdRef.current;

        let newUuid: string | undefined;
        if (!convId) {
          const conv = await chatService.createConversation();
          convId = conv.id;
          newUuid = conv.uuid;
          setActiveConversationId(convId);
          activeConversationIdRef.current = convId;
        }

        // Add both messages
        const created = await chatService.addMessages(convId, [
          { role: "user", content: userContent, has_images: hasImages },
          {
            role: "assistant",
            content: assistantContent,
            sources: sources as Array<Record<string, unknown>> | undefined,
          },
        ]);

        // Update assistant message with dbMessageId for feedback
        const assistantDb = created.find((m) => m.role === "assistant");
        if (assistantDb && assistantMessageId) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId ? { ...m, dbMessageId: assistantDb.id } : m
            )
          );
        }

        // Redirect to UUID URL only after messages are saved (avoids showing empty window)
        if (newUuid) {
          router.replace(`/c/${newUuid}`);
        }

        // Refresh conversation list to show new/updated titles
        await loadConversations();
      } catch (err) {
        console.warn("[Ominis] Failed to persist chat:", err);
      }
    },
    [isAuthenticated, historyEnabled, loadConversations, router],
  );

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

  // Scroll-to-top button visibility (re-run when messages appear so ref is attached)
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const onScroll = () => setShowScrollTop(el.scrollTop > 200);
    el.addEventListener("scroll", onScroll);
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, [messages.length]);

  // Resize textarea when input changes (e.g. from suggestion click) so it expands with wrapped text
  const resizeInputTextarea = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "1px"; // force recalculation of scrollHeight (0 can cause flash)
    el.style.height = Math.min(Math.max(el.scrollHeight, 40), 300) + "px";
  }, []);
  useEffect(() => {
    resizeInputTextarea();
  }, [input, resizeInputTextarea]);

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
          if (!title || title.length < 3 || title.toLowerCase() === "url") {
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
          if (!title || title.length < 3 || title.toLowerCase() === "url") {
            try { title = new URL(url).hostname; } catch { title = url; }
          }
          sources.push({ title, url, type: "web" });
        }
      }
    }
    return sources;
  };

  // Merge existing sources with any URLs found in content that aren't already covered.
  // IMPORTANT: Only extract inline URLs when the backend already provided sources
  // (from RAG/web/PubMed). If no backend sources exist, the LLM answered from
  // general knowledge and any URLs in the text are likely hallucinated.
  const getEffectiveSources = (content: string, existingSources?: Source[]): Source[] | undefined => {
    // No backend sources → don't trust any URLs in the LLM text
    if (!existingSources || existingSources.length === 0) return undefined;

    const extracted = extractSourcesFromContent(content);
    if (extracted.length === 0) return existingSources;

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

  // Render a single line with full markdown: headers, bullets, numbered lists, inline formatting
  const renderLine = (line: string, sources: Source[], lIdx: number, pIdx: number, totalLines: number) => {
    const trimmedLine = line.trim();
    if (!trimmedLine) return null;

    // Check for markdown headers (### Header, ## Header, # Header)
    const headerMatch = trimmedLine.match(/^(#{1,3})\s+(.+)$/);
    if (headerMatch) {
      const level = headerMatch[1].length;
      const headerText = headerMatch[2];
      const cls = level === 1
        ? "text-base font-bold text-white mt-2"
        : level === 2
          ? "text-sm font-semibold text-white mt-1"
          : "text-sm font-medium text-gray-200 mt-1";
      return (
        <div key={lIdx} className={cls}>
          {renderInlineContent(headerText, sources, `p${pIdx}-l${lIdx}`)}
        </div>
      );
    }

    // Check for bullet points (- item or * item or • item)
    const bulletMatch = trimmedLine.match(/^[-*•]\s+(.+)$/);
    if (bulletMatch) {
      return (
        <span key={lIdx} className="block ml-3 relative">
          <span className="absolute -left-3 text-gray-500">•</span>
          {renderInlineContent(bulletMatch[1], sources, `p${pIdx}-l${lIdx}`)}
          {lIdx < totalLines - 1 && <br />}
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
          {lIdx < totalLines - 1 && <br />}
        </span>
      );
    }

    return (
      <span key={lIdx}>
        {renderInlineContent(trimmedLine, sources, `p${pIdx}-l${lIdx}`)}
        {lIdx < totalLines - 1 && <br />}
      </span>
    );
  };

  // ─── Table parsing & rendering ────────────────────────────────────

  /** Parse a markdown row like "| a | b | c |" into ["a","b","c"] */
  const parseTableRow = (line: string): string[] =>
    line.split("|").slice(1, -1).map((c) => c.trim());

  /** Check if a line is a table separator (|---|---|) */
  const isTableSeparator = (line: string): boolean =>
    /^\|[\s\-:| ]+\|$/.test(line.trim());

  /** Check if a line looks like a table row */
  const isTableRow = (line: string): boolean => {
    const t = line.trim();
    return t.startsWith("|") && t.endsWith("|") && t.split("|").length >= 3;
  };

  /** Segment content into text blocks and table blocks */
  const segmentContent = (text: string): Array<{ type: "text" | "table"; content: string }> => {
    const lines = text.split("\n");
    const segments: Array<{ type: "text" | "table"; content: string }> = [];
    let textBuf: string[] = [];
    let tableBuf: string[] = [];

    const flushText = () => {
      if (textBuf.length > 0) {
        segments.push({ type: "text", content: textBuf.join("\n") });
        textBuf = [];
      }
    };
    const flushTable = () => {
      if (tableBuf.length >= 2) {
        segments.push({ type: "table", content: tableBuf.join("\n") });
      } else if (tableBuf.length > 0) {
        // Not enough lines to be a table, treat as text
        textBuf.push(...tableBuf);
      }
      tableBuf = [];
    };

    for (const line of lines) {
      if (isTableRow(line) || isTableSeparator(line)) {
        flushText();
        tableBuf.push(line);
      } else {
        flushTable();
        textBuf.push(line);
      }
    }
    flushTable();
    flushText();
    return segments;
  };

  /** Parse table block into headers + rows */
  const parseTable = (tableContent: string): { headers: string[]; rows: string[][] } | null => {
    const lines = tableContent.trim().split("\n").filter((l) => l.trim());
    if (lines.length < 2) return null;

    const headers = parseTableRow(lines[0]);
    // Find separator index (usually line 1)
    const sepIdx = lines.findIndex((l) => isTableSeparator(l));
    const dataStart = sepIdx >= 0 ? sepIdx + 1 : 1;
    const rows = lines
      .slice(dataStart)
      .filter((l) => !isTableSeparator(l))
      .map(parseTableRow);

    if (headers.length === 0) return null;
    return { headers, rows };
  };

  /** Convert table to TSV for clipboard */
  const tableToTSV = (headers: string[], rows: string[][]): string => {
    const h = headers.join("\t");
    const r = rows.map((row) => row.join("\t")).join("\n");
    return `${h}\n${r}`;
  };

  /** Convert table to CSV for download */
  const tableToCSV = (headers: string[], rows: string[][]): string => {
    const escape = (v: string) => {
      if (v.includes(",") || v.includes('"') || v.includes("\n")) {
        return `"${v.replace(/"/g, '""')}"`;
      }
      return v;
    };
    const h = headers.map(escape).join(",");
    const r = rows.map((row) => row.map(escape).join(",")).join("\n");
    return `${h}\n${r}`;
  };

  /** Download a string as a file */
  const downloadFile = (content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /** Render a parsed table with copy/download actions */
  const renderTable = (
    headers: string[],
    rows: string[][],
    sources: Source[],
    key: string | number,
  ) => {
    const handleCopy = async () => {
      try {
        await navigator.clipboard.writeText(tableToTSV(headers, rows));
        // Brief visual feedback handled by button text swap in component
      } catch {
        // Fallback
        const ta = document.createElement("textarea");
        ta.value = tableToTSV(headers, rows);
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
    };

    const handleDownload = () => {
      downloadFile(tableToCSV(headers, rows), "ominis-tabla.csv", "text/csv;charset=utf-8;");
    };

    return (
      <div key={key} className="my-3 rounded-xl border border-white/10 overflow-hidden bg-white/5">
        {/* Action bar */}
        <div className="flex items-center justify-end gap-1 px-3 py-1.5 bg-white/5 border-b border-white/10">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors"
            title="Copiar tabla (para pegar en Excel)"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            Copiar
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors"
            title="Descargar como CSV"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
        </div>
        {/* Scrollable table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-white/5">
                {headers.map((h, hIdx) => (
                  <th
                    key={hIdx}
                    className="px-3 py-2 text-left text-gray-300 font-semibold border-b border-white/10"
                  >
                    {renderInlineContent(h, sources, `th-${key}-${hIdx}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rIdx) => (
                <tr
                  key={rIdx}
                  className={`${rIdx % 2 === 0 ? "" : "bg-white/[0.02]"} hover:bg-white/5 transition-colors`}
                >
                  {row.map((cell, cIdx) => (
                    <td
                      key={cIdx}
                      className="px-3 py-2 text-gray-300 border-b border-white/5"
                    >
                      {renderInlineContent(cell, sources, `td-${key}-${rIdx}-${cIdx}`)}
                    </td>
                  ))}
                  {/* Fill missing cells if row is shorter than headers */}
                  {row.length < headers.length &&
                    Array.from({ length: headers.length - row.length }).map((_, cIdx) => (
                      <td key={`empty-${cIdx}`} className="px-3 py-2 border-b border-white/5" />
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-3 py-1 text-[10px] text-gray-500 bg-white/[0.02]">
          {rows.length} fila{rows.length !== 1 ? "s" : ""} × {headers.length} columna{headers.length !== 1 ? "s" : ""}
        </div>
      </div>
    );
  };

  // ─── End table helpers ───────────────────────────────────────────

  // Render content with clickable citation links, preserving paragraphs and formatting
  // Always renders full markdown (bold, italic, headers, bullets) regardless of whether
  // sources are present, so formatting works during streaming too.
  /** Render a text block (non-table) with paragraphs and markdown */
  const renderTextBlock = (text: string, sources: Source[], keyOffset: string) => {
    const paragraphs = text.split(/\n{2,}/);

    if (paragraphs.length <= 1) {
      const lines = text.split("\n");
      if (lines.length <= 1) {
        return <span key={keyOffset}>{renderInlineContent(text, sources, `${keyOffset}-s`)}</span>;
      }
      return (
        <span key={keyOffset}>
          {lines.map((line, i) => renderLine(line, sources, i, 0, lines.length))}
        </span>
      );
    }

    return (
      <div key={keyOffset} className="space-y-3">
        {paragraphs.map((para, pIdx) => {
          const trimmed = para.trim();
          if (!trimmed) return null;

          if (!trimmed.includes("\n")) {
            const headerMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
            if (headerMatch) {
              return renderLine(trimmed, sources, 0, pIdx, 1);
            }
          }

          const lines = trimmed.split("\n");
          return (
            <p key={pIdx}>
              {lines.map((line, lIdx) => renderLine(line, sources, lIdx, pIdx, lines.length))}
            </p>
          );
        })}
      </div>
    );
  };

  // Strip LLM-generated "Referencias" / "Fuentes" block (redundant with inline citations + sources list)
  const stripReferenciasBlock = (text: string): string => {
    const lines = text.split("\n");
    const result: string[] = [];
    let stripMode = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      // Start of referencias block
      if (/^(Referencias?|Fuentes?|Bibliograf[ií]a|Sources?):\s*$/i.test(trimmed)) {
        stripMode = true;
        continue;
      }
      // Lines that look like "[N] Title" or "N. Title" when in strip mode
      if (stripMode) {
        if (/^\[\d+\]\s*.+/.test(trimmed) || /^\d+\.\s+.+/.test(trimmed)) continue;
        if (trimmed === "" || /^[-*]\s*/.test(trimmed)) continue;
        stripMode = false;
      }
      result.push(line);
    }
    return result.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  };

  // Replace "RAG" with "OMINIS" in LLM output so references always show OMINIS
  const normalizeRagToOminis = (text: string): string =>
    text.replace(/\bRAG\b/g, "OMINIS");

  const renderContentWithCitations = (content: string, sources?: Source[]) => {
    const effectiveSrc = sources || [];
    let contentWithoutReferencias = stripReferenciasBlock(content);
    contentWithoutReferencias = normalizeRagToOminis(contentWithoutReferencias);
    const formattedContent = formatContentWithCitations(contentWithoutReferencias, effectiveSrc.length > 0 ? effectiveSrc : undefined);

    // Segment into text and table blocks
    const segments = segmentContent(formattedContent);

    // No tables found - fast path
    if (segments.every((s) => s.type === "text")) {
      return renderTextBlock(formattedContent, effectiveSrc, "root");
    }

    // Mixed content with tables
    return (
      <div className="space-y-3">
        {segments.map((seg, idx) => {
          if (seg.type === "table") {
            const parsed = parseTable(seg.content);
            if (parsed) {
              return renderTable(parsed.headers, parsed.rows, effectiveSrc, `tbl-${idx}`);
            }
            // Failed to parse, render as text
            return renderTextBlock(seg.content, effectiveSrc, `seg-${idx}`);
          }
          return renderTextBlock(seg.content, effectiveSrc, `seg-${idx}`);
        })}
      </div>
    );
  };

  // Handle image upload (multiple files)
  const ALLOWED_DOC_EXTENSIONS = [".pdf", ".csv", ".xls", ".xlsx", ".doc", ".docx"];
  const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

  const processFile = (file: File) => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();

    if (ALLOWED_IMAGE_TYPES.includes(file.type) || file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (event) => {
        setUploadedImages((prev) => [
          ...prev,
          { data: event.target?.result as string, name: file.name },
        ]);
      };
      reader.readAsDataURL(file);
    } else if (ALLOWED_DOC_EXTENSIONS.includes(ext)) {
      // Add placeholder while extracting
      const idx = Date.now();
      setUploadedFiles((prev) => [...prev, { name: file.name, ext, text: "", extracting: true }]);

      // Send to backend for text extraction
      const formData = new FormData();
      formData.append("file", file);
      fetch("/api/extract-file", { method: "POST", body: formData })
        .then((res) => res.json())
        .then((data) => {
          setUploadedFiles((prev) =>
            prev.map((f) =>
              f.name === file.name && f.extracting
                ? { ...f, text: data.text || "", extracting: false }
                : f
            )
          );
        })
        .catch(() => {
          setUploadedFiles((prev) =>
            prev.map((f) =>
              f.name === file.name && f.extracting
                ? { ...f, text: "[Error al extraer contenido]", extracting: false }
                : f
            )
          );
        });
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach(processFile);
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
        const item = items[i];
        if (item.type.startsWith("image/")) {
          const file = item.getAsFile();
          if (file) processFile(file);
        }
      }
    }
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files) {
      Array.from(files).forEach(processFile);
    }
  };

  // Remove uploaded image by index
  const removeImage = (index: number) => {
    setUploadedImages((prev) => prev.filter((_, i) => i !== index));
  };

  // Remove uploaded file by index
  const removeFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Clear all attachments
  const clearAllImages = () => {
    setUploadedImages([]);
    setUploadedFiles([]);
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
    const hasAttachments = uploadedImages.length > 0 || uploadedFiles.length > 0;
    if ((!question && !hasAttachments) || isLoading) return;

    // Build user message content with attachment indicators
    const attachmentParts: string[] = [];
    if (uploadedImages.length > 0) {
      const imageNames = uploadedImages.map((img) => img.name).join(", ");
      attachmentParts.push(`${uploadedImages.length} imagen${uploadedImages.length > 1 ? "es" : ""}: ${imageNames}`);
    }
    if (uploadedFiles.length > 0) {
      const fileNames = uploadedFiles.map((f) => f.name).join(", ");
      attachmentParts.push(`${uploadedFiles.length} archivo${uploadedFiles.length > 1 ? "s" : ""}: ${fileNames}`);
    }
    const messageContent = attachmentParts.length > 0
      ? `${question}${question ? "\n" : ""}[${attachmentParts.join("; ")}]`
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
    const hadImages = uploadedImages.length > 0;
    const currentFileContext = uploadedFiles
      .filter((f) => f.text && !f.extracting)
      .map((f) => `--- ${f.name} ---\n${f.text}`)
      .join("\n\n");
    const currentRagSearch = ragSearchEnabled;
    const currentWebSearch = webSearchEnabled;
    const currentPubmedSearch = pubmedSearchEnabled;
    clearAllImages(); // Clear all attachments after capturing
    setIsLoading(true);
    setLoadingStatus("Analizando...");
    if (researchModeEnabled) {
      setResearchSteps([]);
      setResearchProgress(null);
      setShowResearchPanel(true);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, researchModeEnabled ? 300000 : 120000); // 5min for research, 2min for normal

      // Build chat history for context — include ALL previous messages
      // (messages is the state before setMessages runs, so it has the full prior history)
      const history = messages
        .slice(-20)
        .map(m => ({ role: m.role, content: m.content }));

      // Use streaming endpoint
      const endpoint = researchModeEnabled ? "/api/academic-query-stream" : "/api/query-stream";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: question || (currentFileContext ? "Analiza el archivo adjunto" : "Describe esta imagen"),
          history: history,
          images: currentImages.length > 0 ? currentImages : undefined,
          model: selectedModel,
          rag_search: currentRagSearch,
          web_search: currentWebSearch,
          pubmed_search: currentPubmedSearch,
          file_context: currentFileContext || undefined,
          iterations: researchModeEnabled ? 5 : undefined,
          max_total_sources: researchModeEnabled ? 25 : undefined,
          max_follow_links: researchModeEnabled ? 10 : undefined,
          max_trusted_sources: researchModeEnabled ? 10 : undefined,
          time_budget_seconds: researchModeEnabled ? 240 : undefined,
          excluded_sources: researchModeEnabled && excludedSources.size > 0 ? Array.from(excludedSources) : undefined,
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
                  const statusMsg = eventData.model === "openscholar"
                    ? `${eventData.message} (OpenScholar)`
                    : eventData.message;
                  setLoadingStatus(statusMsg);

                } else if (eventData.type === "research_step") {
                  if (eventData.step) {
                    setResearchSteps((prev) => {
                      if (prev.length === 0) setShowResearchPanel(true);
                      return [...prev, eventData.step];
                    });
                  }
                  if (eventData.progress) {
                    setResearchProgress(eventData.progress);
                  }

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
                      model: researchModeEnabled ? "openscholar" : undefined,
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

                } else if (eventData.type === "charts") {
                  // Chart images generated by backend
                  if (eventData.charts && eventData.charts.length > 0) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, charts: eventData.charts }
                          : m
                      )
                    );
                  }

                } else if (eventData.type === "done") {
                  const finalContent = eventData.answer || streamedContent || "No pude generar una respuesta.";
                  const finalSources = Array.isArray(eventData.sources) ? eventData.sources : [];
                  const finalCharts = eventData.charts || undefined;
                  const isReport = !!eventData.is_report;
                  const modelUsed = eventData.model || undefined;

                  if (!messageAdded) {
                    setMessages((prev) => [...prev, {
                      id: assistantId, role: "assistant", content: finalContent,
                      sources: finalSources.length > 0 ? finalSources : undefined,
                      charts: finalCharts, isReport, model: modelUsed,
                    }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, content: finalContent, sources: finalSources.length > 0 ? finalSources : undefined, charts: finalCharts || m.charts, isReport: isReport || m.isReport, model: modelUsed || m.model }
                          : m
                      )
                    );
                  }

                  persistMessages(messageContent, finalContent, finalSources.length > 0 ? finalSources : undefined, hadImages, assistantId);

                  setIsLoading(false);
                  setLoadingStatus("");
                  // Auto-disable research mode only after a report (flagged by backend)
                  if (researchModeEnabled && isReport) {
                    setResearchModeEnabled(false);
                  }
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

        // Persist even if no done event
        if (streamedContent) {
          persistMessages(
            messageContent,
            streamedContent,
            streamedSources.length > 0 ? streamedSources : undefined,
            hadImages,
            assistantId,
          );
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

  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopyContent = async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId((prev) => prev === id ? null : prev), 2000);
    } catch { /* ignore */ }
  };

  const getFeedbackExtras = (message: Message) => {
    const conv = activeConversationId ? conversations.find((c) => c.id === activeConversationId) : null;
    const queryTitle = conv?.title ?? messages.find((m) => m.role === "user")?.content.slice(0, 100) ?? "Nuevo trabajo";
    return {
      model_name: message.model ?? selectedModel,
      query_title: queryTitle,
    };
  };

  const handleThumbsUp = async (message: Message) => {
    try {
      const { model_name, query_title } = getFeedbackExtras(message);
      await feedbackService.submitFeedback({
        message_id: message.dbMessageId,
        conversation_id: activeConversationId ?? undefined,
        rating: "positive",
        content_preview: message.content.slice(0, 500),
        model_name,
        query_title,
        sources: message.sources,
      });
      setFeedbackByMessageId((prev) => ({ ...prev, [message.id]: "positive" }));
    } catch (err) {
      console.warn("[Ominis] Failed to submit feedback:", err);
    }
  };

  const handleThumbsDown = (message: Message) => {
    setFeedbackModalMessageId(message.id);
    setFeedbackReasonCategory(null);
    setFeedbackReasonText("");
  };

  const handleFeedbackModalSubmit = async () => {
    const msgId = feedbackModalMessageId;
    if (!msgId) return;
    const msg = messages.find((m) => m.id === msgId);
    if (!msg) return;

    setFeedbackSubmitting(true);
    try {
      const { model_name, query_title } = getFeedbackExtras(msg);
      await feedbackService.submitFeedback({
        message_id: msg.dbMessageId,
        conversation_id: activeConversationId ?? undefined,
        rating: "negative",
        reason_category: feedbackReasonCategory ?? undefined,
        reason_text: feedbackReasonText.trim() || undefined,
        content_preview: msg.content.slice(0, 500),
        model_name,
        query_title,
        sources: msg.sources,
      });
      setFeedbackByMessageId((prev) => ({ ...prev, [msgId]: "negative" }));
      setFeedbackModalMessageId(null);
    } catch (err) {
      console.warn("[Ominis] Failed to submit feedback:", err);
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleDownloadPdf = async (content: string, title: string) => {
    try {
      const res = await fetch("/api/generate-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, title: title || "OMINIS Report" }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error al generar PDF");
      }
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition");
      const filenameMatch = disposition?.match(/filename="([^"]+)"/);
      const filename = filenameMatch?.[1] || "ominis-report.pdf";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.warn("[PDF] Fallback to print:", err);
      // Fallback: open print dialog (same as before)
      const win = window.open("", "_blank");
      if (!win) return;
      let html = content
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^\- (.+)$/gm, "<li>$1</li>")
        .replace(/^\* (.+)$/gm, "<li>$1</li>")
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/\[(\d+)\]/g, '<sup class="ref">[$1]</sup>')
        .replace(/\n\n/g, "</p><p>")
        .replace(/\n/g, "<br>");
      html = "<p>" + html + "</p>";
      html = html.replace(/<p><h/g, "<h").replace(/<\/h(\d)><\/p>/g, "</h$1>");
      html = html.replace(/<p><li>/g, "<ul><li>").replace(/<\/li><\/p>/g, "</li></ul>");
      const logoUrl = window.location.origin + "/logo.png";
      win.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>
<style>body{font-family:Helvetica,Arial,sans-serif;max-width:720px;margin:0 auto;padding:20px;color:#1a1a1a;font-size:11pt;line-height:1.55}
h1{font-size:20pt;color:#111;border-bottom:2px solid #222;padding-bottom:6px;margin:0 0 12px 0}h2{font-size:14pt;color:#333;margin:16px 0 6px 0}
h3{font-size:12pt;color:#444;margin:12px 0 4px 0}p{margin:0 0 8px 0}ul{margin:4px 0 8px 20px;padding:0}li{margin:2px 0}
sup.ref{color:#1a5fb4;font-size:8pt;font-weight:600}.footer{font-size:8pt;color:#999;margin-top:24px;padding-top:8px;border-top:1px solid #eee}</style>
</head><body><div style="text-align:right;padding-bottom:12px;border-bottom:1px solid #ddd"><img src="${logoUrl}" alt="OMINIS" height="28" /></div>
${html}<div class="footer">con apoyo de ia.ominis.org</div></body></html>`);
      win.document.close();
      setTimeout(() => win.print(), 600);
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
    const hadImages = !!(originalMessage.images && originalMessage.images.length > 0);

    // Remove this message and all messages after it
    const newMessages = messages.slice(0, messageIndex);

    // Clear editing state
    setEditingMessageId(null);
    setEditingText("");

    // Create the new user message
    const userMessageContent = hadImages
      ? `${question}\n[${originalMessage.images!.length} imagen${originalMessage.images!.length > 1 ? "es" : ""} adjunta${originalMessage.images!.length > 1 ? "s" : ""}]`
      : question;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: userMessageContent,
      images: originalMessage.images,
    };

    setMessages([...newMessages, userMessage]);
    setIsLoading(true);
    setLoadingStatus("Analizando...");

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      const history = newMessages
        .slice(-20)
        .map(m => ({ role: m.role, content: m.content }));

      // Use streaming endpoint
      const endpoint = researchModeEnabled ? "/api/academic-query-stream" : "/api/query-stream";
      const response = await fetch(endpoint, {
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
          iterations: researchModeEnabled ? 5 : undefined,
          max_total_sources: researchModeEnabled ? 25 : undefined,
          max_follow_links: researchModeEnabled ? 10 : undefined,
          max_trusted_sources: researchModeEnabled ? 10 : undefined,
          time_budget_seconds: researchModeEnabled ? 240 : undefined,
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

                  // Persist to backend
                  persistMessages(
                    userMessageContent,
                    finalContent,
                    finalSources.length > 0 ? finalSources : undefined,
                    hadImages,
                  );

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

        // Persist even if no done event
        if (streamedContent) {
          persistMessages(
            userMessageContent,
            streamedContent,
            streamedSources.length > 0 ? streamedSources : undefined,
            hadImages,
          );
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
    "Principales causas de muerte en México",
    "Fuentes de datos de salud en México",
    "Diferencia entre diabetes tipo 1 y tipo 2",
    "Guías clínicas recientes para hipertensión",
  ];

  const hasMessages = messages.length > 0;
  const [footerExpanded, setFooterExpanded] = useState(false);

  const renderPlusMenu = () => (
    <div className="absolute bottom-full left-0 mb-2 bg-[#1a2744] border border-white/10 rounded-xl shadow-xl py-2 min-w-[200px] z-50">
      <button onClick={() => fileInputRef.current?.click()} className="w-full flex items-center gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
        Adjuntar archivos
      </button>
      <div className="border-t border-white/10 my-1" />
      <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Modelo</div>
      {availableModels.map((m) => (
        <button key={m.id} onClick={() => setSelectedModel(m.id)} className={`w-full flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors ${selectedModel === m.id ? "text-white bg-white/10" : "text-gray-300 hover:bg-white/10 hover:text-white"}`}>
          <div className="flex items-center gap-3 min-w-0">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
            <span className="truncate">{m.displayName}</span>
          </div>
          {selectedModel === m.id && <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>}
        </button>
      ))}
      <div className="border-t border-white/10 my-1" />
      <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Modo</div>
      <button onClick={() => setResearchModeEnabled(!researchModeEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
        <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /></svg>Investigación</div>
        <div className={`w-8 h-5 rounded-full transition-colors ${researchModeEnabled ? "bg-emerald-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${researchModeEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
      </button>
      <div className="border-t border-white/10 my-1" />
      <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Buscar en fuentes</div>
      <button onClick={() => setRagSearchEnabled(!ragSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
        <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>Ominis</div>
        <div className={`w-8 h-5 rounded-full transition-colors ${ragSearchEnabled ? "bg-cyan-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${ragSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
      </button>
      <button onClick={() => setWebSearchEnabled(!webSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
        <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>Web</div>
        <div className={`w-8 h-5 rounded-full transition-colors ${webSearchEnabled ? "bg-blue-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${webSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
      </button>
      <button onClick={() => setPubmedSearchEnabled(!pubmedSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
        <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>PubMed</div>
        <div className={`w-8 h-5 rounded-full transition-colors ${pubmedSearchEnabled ? "bg-purple-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${pubmedSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
      </button>
    </div>
  );

  return (
    <section className="h-screen pt-16 relative flex flex-col overflow-hidden overflow-x-hidden max-w-[100vw]">
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

      {/* Chat History Sidebar */}
      {/* Note: renderPlusMenu is defined below as a local function */}
      <ChatSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpen={() => setSidebarOpen(true)}
        isAuthenticated={isAuthenticated}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        onRenameConversation={handleRenameConversation}
        onRegenerateTitle={handleRegenerateTitle}
        historyEnabled={historyEnabled}
        onToggleHistory={handleToggleHistory}
      />

      {/* Content */}
      <div className={`relative z-10 flex-1 flex flex-col min-h-0 transition-all duration-300 overflow-x-hidden max-w-full ${sidebarOpen ? "lg:pl-72" : "lg:pl-10"}`}>
        <div className="flex-1 flex flex-col max-w-4xl w-full mx-auto px-4 sm:px-6 min-h-0 max-w-full">
              {/* Mobile toolbar - hamburger (history) and + (new job) at top left */}
              <div className="lg:hidden flex items-center gap-2 py-2 flex-shrink-0 -mx-4 sm:-mx-6 px-4 sm:px-6 border-b border-white/10 mb-1">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-lg transition-colors"
                  title="Historial de trabajos"
                  aria-label="Abrir historial"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                {isAuthenticated && (
                  <button
                    onClick={handleNewChat}
                    className="text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-lg transition-colors"
                    title="Nuevo trabajo"
                    aria-label="Nuevo trabajo"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                  </button>
                )}
              </div>
              {/* Minimal spacer when messages exist (sidebar handles its own toggle) */}
              {hasMessages && <div className="h-2 flex-shrink-0" />}

              {/* Empty State - centered prompt + input */}
              {!hasMessages && (
                <div className="flex-1 flex flex-col items-center justify-center px-4">
                  <h1 className="text-white text-2xl sm:text-3xl font-semibold mb-8 text-center">
                    ¿En qué puedo ayudarte?
                  </h1>

                  {/* Centered input for empty state */}
                  <div className="w-full max-w-2xl">
                    {/* Capsules (research, model, attachments — Ominis/Web/PubMed inside input) */}
                    {(researchModeEnabled || uploadedImages.length > 0 || uploadedFiles.length > 0 || selectedModel !== "ominis-2.0") && (
                      <div className="flex items-center justify-center gap-1.5 mb-3 text-xs flex-wrap">
                        {selectedModel !== "ominis-2.0" && (
                          <span className="flex items-center gap-1 text-amber-400 bg-amber-500/15 backdrop-blur-sm border border-amber-400/20 px-2 py-1 rounded-full">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                            {availableModels.find(m => m.id === selectedModel)?.displayName || selectedModel}
                          </span>
                        )}
                        {researchModeEnabled && (
                          <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/15 backdrop-blur-sm border border-emerald-400/20 pl-2 pr-1 py-1 rounded-full">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /></svg>
                            Investigación
                            <button onClick={() => setResearchModeEnabled(false)} className="ml-0.5 hover:text-emerald-200 transition-colors" title="Desactivar">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                            </button>
                          </span>
                        )}
                        {(uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                          <span className="flex items-center gap-1 text-orange-400 bg-orange-500/10 px-2 py-1 rounded-full">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                            {uploadedImages.length + uploadedFiles.length} adjunto{(uploadedImages.length + uploadedFiles.length) > 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Input row */}
                    <div
                      className={`relative ${isDragOver ? "ring-2 ring-cyan-400/50 bg-cyan-500/5 rounded-xl" : ""}`}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                    >
                      {isDragOver && (
                        <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#0a1628]/80 rounded-xl border-2 border-dashed border-cyan-400/50 pointer-events-none">
                          <p className="text-cyan-300 text-sm font-medium">Suelta archivos aquí</p>
                        </div>
                      )}

                      {/* Attachments Preview */}
                      {(uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                        <div className="mb-2 flex flex-wrap gap-2 justify-center">
                          {uploadedImages.map((img, index) => (
                            <div key={`img-${index}`} className="relative group">
                              <img src={img.data} alt={img.name} className="h-12 w-12 object-cover rounded" />
                              <button onClick={() => removeImage(index)} className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity" title="Eliminar">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                              </button>
                            </div>
                          ))}
                          {uploadedFiles.map((file, index) => (
                            <div key={`file-${index}`} className="relative group flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                              <svg className="w-5 h-5 text-orange-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                              <p className="text-white text-xs truncate max-w-[120px]">{file.name}</p>
                              <button onClick={() => removeFile(index)} className="text-gray-400 hover:text-red-400 transition-colors ml-1" title="Eliminar">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="flex flex-col gap-2 bg-white/[0.07] backdrop-blur-md border border-white/15 rounded-2xl px-3 py-2.5 shadow-lg shadow-black/10 focus-within:border-white/30 transition-all">
                        <input ref={fileInputRef} type="file" accept="image/*,.pdf,.csv,.xls,.xlsx,.doc,.docx" multiple onChange={handleFileUpload} className="hidden" />
                        <textarea
                          ref={inputRef}
                          value={input}
                          onChange={(e) => { setInput(e.target.value); e.target.style.height = "1px"; e.target.style.height = Math.min(Math.max(e.target.scrollHeight, 40), 300) + "px"; }}
                          onKeyDown={handleKeyDown} onPaste={handlePaste}
                          placeholder="Pregunta sobre salud en México..."
                          className="w-full min-h-[2.5rem] bg-transparent border-none px-0 py-0 text-sm text-white placeholder-gray-400 focus:outline-none resize-none overflow-y-auto"
                          style={{ maxHeight: "300px" }}
                          rows={1}
                          disabled={isLoading}
                        />
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <div className="relative" ref={plusMenuRef}>
                            <button
                              onClick={() => setShowPlusMenu(!showPlusMenu)}
                              className={`text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-full transition-colors ${showPlusMenu ? "bg-white/10 text-white" : ""}`}
                              title="Opciones" disabled={isLoading}
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                            </button>
                            {showPlusMenu && renderPlusMenu()}
                          </div>
                          <div className="flex-1 flex items-center gap-1 flex-wrap min-w-0">
                            {ragSearchEnabled && (
                              <span className="inline-flex items-center gap-0.5 text-cyan-400 bg-cyan-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                                Ominis
                                <button onClick={() => setRagSearchEnabled(false)} className="hover:text-cyan-200 transition-colors p-0.5" title="Desactivar">
                                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                              </span>
                            )}
                            {webSearchEnabled && (
                              <span className="inline-flex items-center gap-0.5 text-blue-400 bg-blue-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                                Web
                                <button onClick={() => setWebSearchEnabled(false)} className="hover:text-blue-200 transition-colors p-0.5" title="Desactivar">
                                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                              </span>
                            )}
                            {pubmedSearchEnabled && (
                              <span className="inline-flex items-center gap-0.5 text-purple-400 bg-purple-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                                PubMed
                                <button onClick={() => setPubmedSearchEnabled(false)} className="hover:text-purple-200 transition-colors p-0.5" title="Desactivar">
                                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                              </span>
                            )}
                          </div>
                          <button
                            onClick={sendMessage}
                            disabled={isLoading || (!input.trim() && uploadedImages.length === 0 && uploadedFiles.length === 0)}
                            className="bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Suggestions */}
                    <div className="flex flex-wrap justify-center gap-2 mt-4">
                      {suggestedQuestions.map((q, i) => (
                        <button key={i} onClick={() => { setInput(q); inputRef.current?.focus(); }}
                          className="text-xs text-gray-400 hover:text-gray-200 bg-white/[0.06] hover:bg-white/[0.12] backdrop-blur-sm border border-white/10 hover:border-white/25 rounded-full px-3 py-1.5 transition-all"
                        >{q}</button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Messages Area */}
              {hasMessages && (
              <div ref={messagesContainerRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
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
                          ? "bg-blue-500/30 backdrop-blur-md border border-blue-400/20 text-white rounded-2xl rounded-br-sm"
                          : "bg-white/10 backdrop-blur-md border border-white/10 text-gray-100 rounded-2xl rounded-bl-sm"
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

                          {/* Action buttons for assistant messages */}
                          {message.role === "assistant" && (
                            <div className="flex items-center gap-1.5 mt-2 pt-1">
                              {message.model === "openscholar" && (
                                <span className="text-[9px] text-amber-300 bg-amber-500/15 border border-amber-400/30 rounded px-1.5 py-0.5 mr-1" title="Generado con motor Investigación">Investigación</span>
                              )}
                              {message.isReport && (
                                <span className="text-[9px] text-emerald-500 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 mr-1">REPORTE</span>
                              )}
                              {message.content.length > 100 && (
                                <>
                                  <button
                                    onClick={() => handleCopyContent(message.id, message.content)}
                                    className="text-gray-500 hover:text-white p-1 hover:bg-white/10 rounded transition-colors"
                                    title="Copiar contenido"
                                  >
                                    {copiedId === message.id ? (
                                      <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                    ) : (
                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                    )}
                                  </button>
                                  <button
                                    onClick={() => handleDownloadPdf(message.content, message.content.split("\n")[0]?.replace(/^#+ /, "") || "Reporte")}
                                    className="text-gray-500 hover:text-white p-1 hover:bg-white/10 rounded transition-colors"
                                    title="Descargar PDF"
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                                  </button>
                                </>
                              )}
                              <button
                                onClick={() => handleThumbsUp(message)}
                                className={`p-1 rounded transition-colors flex-shrink-0 ${feedbackByMessageId[message.id] === "positive" ? "text-green-400" : "text-gray-400 hover:text-white hover:bg-white/10"}`}
                                title="Útil"
                                aria-label="Útil"
                              >
                                <svg className="w-4 h-4" fill={feedbackByMessageId[message.id] === "positive" ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                                  <path d="M15 5.88 14 10h5.83a2 2 0 011.92 2.56l-2.33 8A2 2 0 0117.5 22H4a2 2 0 01-2-2v-8a2 2 0 012-2h2.76a2 2 0 001.79-1.11L12 2a3.13 3.13 0 011 3.88Z" />
                                  <path d="M7 10v12" />
                                </svg>
                              </button>
                              <button
                                onClick={() => handleThumbsDown(message)}
                                className={`p-1 rounded transition-colors flex-shrink-0 ${feedbackByMessageId[message.id] === "negative" ? "text-red-400" : "text-gray-400 hover:text-white hover:bg-white/10"}`}
                                title="No útil"
                                aria-label="No útil"
                              >
                                <svg className="w-4 h-4" fill={feedbackByMessageId[message.id] === "negative" ? "currentColor" : "none"} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                                  <path d="M9 18.12 10 14H4.17a2 2 0 01-1.92-2.56l2.33-8A2 2 0 016.5 2H20a2 2 0 012 2v8a2 2 0 01-2 2h-2.76a2 2 0 00-1.79 1.11L12 22a3.13 3.13 0 01-3-3.88Z" />
                                  <path d="M17 14V2" />
                                </svg>
                              </button>
                            </div>
                          )}

                          {/* Charts */}
                          {message.charts && message.charts.length > 0 && (
                            <div className="mt-3 space-y-3">
                              {message.charts.map((chart) => (
                                <div key={chart.id} className="bg-white rounded-lg p-2 overflow-hidden">
                                  <img
                                    src={chart.image}
                                    alt={chart.title || "Gráfica"}
                                    className="w-full h-auto rounded cursor-pointer"
                                    onClick={() => setModalImage(chart.image)}
                                  />
                                  {chart.title && (
                                    <p className="text-gray-700 text-xs text-center mt-1 font-medium">{chart.title}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Sources list */}
                          {effectiveSources && effectiveSources.length > 0 && (() => {
                            const displaySources = effectiveSources
                              .map((source: any, i: number) => ({ ...source, displayNum: source.ref_num || (i + 1) }))
                              .filter((s: any) => s.url && s.url.length > 0);
                            if (displaySources.length === 0) return null;

                            // Show checkboxes if research mode is on and this is a plan message (has "?")
                            const showCheckboxes = researchModeEnabled && message.content.includes("?") && !isLoading;

                            return (
                              <div className="mt-3 pt-3 border-t border-white/10">
                                {showCheckboxes && (
                                  <p className="text-[10px] text-gray-500 mb-1.5">Desmarca las fuentes que no deseas incluir en la investigación:</p>
                                )}
                                <ul className="space-y-1.5">
                                  {displaySources.map((source: any) => {
                                    const isExcluded = excludedSources.has(source.url);
                                    const originLabel = source.type === "pubmed" ? "PubMed" : source.type === "rag" ? "Ominis" : "Web";
                                    const originIcon = source.type === "pubmed" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
                                    ) : source.type === "rag" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>
                                    ) : (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                    );
                                    const displayTitle = (source.title && source.title.toLowerCase() !== "url")
                                      ? source.title
                                      : (source.url ? (() => { try { return new URL(source.url).hostname; } catch { return source.url.slice(0, 50); } })() : "Sin título");
                                    return (
                                      <li key={source.displayNum} className={`text-xs ${isExcluded ? "opacity-40" : ""}`}>
                                        <div className="flex items-start gap-1.5">
                                          {showCheckboxes && (
                                            <input
                                              type="checkbox"
                                              checked={!isExcluded}
                                              onChange={() => {
                                                setExcludedSources(prev => {
                                                  const next = new Set(prev);
                                                  if (next.has(source.url)) next.delete(source.url);
                                                  else next.add(source.url);
                                                  return next;
                                                });
                                              }}
                                              className="mt-0.5 rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30 flex-shrink-0"
                                            />
                                          )}
                                          <div className="min-w-0">
                                            <a href={source.url} target="_blank" rel="noopener noreferrer"
                                              className="text-blue-400 hover:text-blue-300 transition-colors hover:underline">
                                              [{source.displayNum}] {displayTitle}
                                            </a>
                                            <div className="text-[10px] text-gray-500 mt-0.5 flex items-center gap-1">
                                              <span className="inline-flex items-center">{originIcon}{originLabel}</span>
                                              {source.authors && <span className="mr-2">· {source.authors.split(",").slice(0, 2).join(", ")}{source.authors.split(",").length > 2 ? " et al." : ""}</span>}
                                              {source.year && <span className="mr-2">· {source.year}</span>}
                                              {source.journal && <span>· {source.journal}</span>}
                                            </div>
                                          </div>
                                        </div>
                                      </li>
                                    );
                                  })}
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

                {/* Loading indicator / Research progress */}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 backdrop-blur-md border border-white/10 text-gray-100 rounded-2xl rounded-bl-sm p-3 max-w-[85%]">
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
                        <div className="flex items-center gap-2 min-w-0">
                          {loadingStatus && (
                            <span className="text-gray-300 text-sm animate-pulse">{loadingStatus}</span>
                          )}
                          {researchModeEnabled && (
                            <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 bg-amber-500/20 border border-amber-400/30 rounded" title="Motor académico exclusivo">
                              Investigación
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Research progress bar */}
                      {researchProgress && researchSteps.length > 0 && (
                        <div className="mt-3">
                          <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
                            <span>{researchProgress.found} fuentes · {researchProgress.read} leídas</span>
                            <span className="flex items-center gap-1.5">
                              <span className="text-amber-300/90 font-medium">OpenScholar</span>
                              <span>{researchProgress.elapsedSeconds}s</span>
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-500" style={{ width: `${Math.min(100, researchProgress.elapsedSeconds / 2.4)}%` }} />
                          </div>
                          <button
                            onClick={() => setShowResearchPanel(!showResearchPanel)}
                            className="mt-2 text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
                          >
                            {showResearchPanel ? "Ocultar actividad" : `Ver actividad (${researchSteps.length} pasos)`}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
              )}

              {/* Scroll-to-top — transparent over content */}
              {hasMessages && showScrollTop && (
                <div className="flex-shrink-0 flex justify-end items-center px-4 py-1">
                  <button
                    onClick={() => messagesContainerRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
                    className="p-1.5 text-white/70 hover:text-white transition-colors"
                    title="Volver arriba"
                    aria-label="Volver arriba"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    </svg>
                  </button>
                </div>
              )}

              {/* Input Area (bottom — only when chat has messages) */}
              {hasMessages && <div
                className={`p-3 flex-shrink-0 border-t border-white/10 relative ${isDragOver ? "ring-2 ring-cyan-400/50 bg-cyan-500/5 rounded-xl" : ""}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {/* Drag overlay */}
                {isDragOver && (
                  <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#0a1628]/80 rounded-xl border-2 border-dashed border-cyan-400/50 pointer-events-none">
                    <div className="text-center">
                      <svg className="w-8 h-8 text-cyan-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      <p className="text-cyan-300 text-sm font-medium">Suelta archivos aquí</p>
                      <p className="text-gray-400 text-xs mt-1">Imágenes, PDF, CSV, XLS, DOC</p>
                    </div>
                  </div>
                )}

                {/* Attachments Preview */}
                {(uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {uploadedImages.map((img, index) => (
                      <div key={`img-${index}`} className="relative group">
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
                    {uploadedFiles.map((file, index) => (
                      <div key={`file-${index}`} className="relative group flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                        <svg className="w-5 h-5 text-orange-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <div className="min-w-0">
                          <p className="text-white text-xs truncate max-w-[120px]">{file.name}</p>
                          {file.extracting ? (
                            <p className="text-cyan-400 text-[10px] animate-pulse">Extrayendo...</p>
                          ) : (
                            <p className="text-gray-500 text-[10px]">{file.text ? `${file.text.length.toLocaleString()} chars` : "Listo"}</p>
                          )}
                        </div>
                        <button
                          onClick={() => removeFile(index)}
                          className="text-gray-400 hover:text-red-400 transition-colors ml-1"
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

                {/* Active features indicator (research, model, attachments — Ominis/Web/PubMed inside input) */}
                {(researchModeEnabled || uploadedImages.length > 0 || uploadedFiles.length > 0 || selectedModel !== "ominis-2.0") && (
                  <div className="flex items-center gap-1.5 mb-2 text-xs flex-wrap">
                    {selectedModel !== "ominis-2.0" && (
                      <span className="flex items-center gap-1 text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        {availableModels.find(m => m.id === selectedModel)?.displayName || selectedModel}
                      </span>
                    )}
                    {researchModeEnabled && (
                      <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 pl-2 pr-1 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" />
                        </svg>
                        Investigación
                        <button onClick={() => setResearchModeEnabled(false)} className="ml-0.5 hover:text-emerald-200 transition-colors" title="Desactivar">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </span>
                    )}
                    {(uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                      <span className="flex items-center gap-1 text-orange-400 bg-orange-500/10 px-2 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                        </svg>
                        {uploadedImages.length + uploadedFiles.length} adjunto{(uploadedImages.length + uploadedFiles.length) > 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                )}

                {/* Input Row — textarea on top, buttons below */}
                <div className="flex flex-col gap-2 bg-white/5 border border-white/10 rounded-2xl px-3 py-2.5 focus-within:border-white/30 transition-all">
                  <input ref={fileInputRef} type="file" accept="image/*,.pdf,.csv,.xls,.xlsx,.doc,.docx" multiple onChange={handleFileUpload} className="hidden" />
                  {/* Row 1: full-width textarea (grows, expands frame upward) */}
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => { setInput(e.target.value); e.target.style.height = "1px"; e.target.style.height = Math.min(Math.max(e.target.scrollHeight, 40), 300) + "px"; }}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    placeholder="Pregunta sobre salud en México..."
                    className="w-full min-h-[2.5rem] bg-transparent border-none text-sm text-white placeholder-gray-500 focus:outline-none resize-none overflow-y-auto py-0"
                    style={{ maxHeight: "300px" }}
                    rows={1}
                    disabled={isLoading}
                  />
                  {/* Row 2: + | tags | send */}
                  <div className="flex items-center gap-2 flex-shrink-0">
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
                      {showPlusMenu && renderPlusMenu()}
                    </div>
                    <div className="flex-1 flex items-center gap-1 flex-wrap min-w-0">
                      {ragSearchEnabled && (
                        <span className="inline-flex items-center gap-0.5 text-cyan-400 bg-cyan-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                          Ominis
                          <button onClick={() => setRagSearchEnabled(false)} className="hover:text-cyan-200 transition-colors p-0.5" title="Desactivar">
                            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </span>
                      )}
                      {webSearchEnabled && (
                        <span className="inline-flex items-center gap-0.5 text-blue-400 bg-blue-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                          Web
                          <button onClick={() => setWebSearchEnabled(false)} className="hover:text-blue-200 transition-colors p-0.5" title="Desactivar">
                            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </span>
                      )}
                      {pubmedSearchEnabled && (
                        <span className="inline-flex items-center gap-0.5 text-purple-400 bg-purple-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                          PubMed
                          <button onClick={() => setPubmedSearchEnabled(false)} className="hover:text-purple-200 transition-colors p-0.5" title="Desactivar">
                            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </span>
                      )}
                    </div>
                    <button
                      onClick={sendMessage}
                      disabled={isLoading || (!input.trim() && uploadedImages.length === 0 && uploadedFiles.length === 0)}
                      className="bg-blue-600 hover:bg-blue-700 text-white p-2.5 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>}

            {/* Bottom info line */}
            <div className="flex-shrink-0 text-center py-1.5">
              <span className="text-gray-500 text-[11px]">
                ⚠️ Siempre verifica con las fuentes originales · Una iniciativa de{" "}
                <a href="https://www.funsalud.org.mx" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white transition-colors">FUNSALUD</a>
                {" · IA hecha en México · modelo LLM: "}
                <a href="/modelo" className="text-gray-400 hover:text-white transition-colors">ominis-2.0</a>
                {" · "}
                <button
                  onClick={() => setFooterExpanded(true)}
                  className="text-gray-400 hover:text-white transition-colors underline underline-offset-2 decoration-gray-600 hover:decoration-white"
                >
                  Más información
                </button>
              </span>
            </div>
        </div>
      </div>

      {/* Expandable footer overlay */}
      {footerExpanded && (
        <div className={`fixed inset-x-0 bottom-0 z-40 max-h-[70vh] overflow-y-auto transition-all duration-300 ${sidebarOpen ? "lg:pl-72" : "lg:pl-10"}`}>
          <div className="bg-[#060e1a]/95 backdrop-blur-md border-t border-white/10">
            <button
              type="button"
              onClick={() => setFooterExpanded(false)}
              className="w-full text-center py-3 cursor-pointer hover:bg-white/5 transition-colors border-b border-white/10"
            >
              <span className="text-gray-500 hover:text-gray-300 text-[11px] transition-colors">
                Ocultar ▼
              </span>
            </button>
            <Footer />
          </div>
        </div>
      )}

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

      {/* Feedback Modal (thumbs down) */}
      {feedbackModalMessageId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => setFeedbackModalMessageId(null)}
        >
          <div
            className="bg-[#1a2744] border border-white/15 rounded-xl shadow-xl max-w-md w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold">Gracias por ayudarnos</h3>
              <button
                onClick={() => setFeedbackModalMessageId(null)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <p className="text-gray-400 text-sm mb-3">¿Por qué no te resultó útil esta respuesta?</p>
            <div className="flex flex-wrap gap-2 mb-4">
              {feedbackService.REASON_CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  onClick={() => setFeedbackReasonCategory(feedbackReasonCategory === cat.value ? null : cat.value)}
                  className={`px-3 py-2 rounded-lg text-sm transition-colors ${
                    feedbackReasonCategory === cat.value
                      ? "bg-cyan-500/30 text-cyan-200 border border-cyan-400/50"
                      : "bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
            <textarea
              placeholder="Compartir detalles (opcional)"
              value={feedbackReasonText}
              onChange={(e) => setFeedbackReasonText(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 resize-none"
              rows={3}
            />
            <div className="flex justify-end mt-4">
              <button
                onClick={handleFeedbackModalSubmit}
                disabled={feedbackSubmitting}
                className="bg-gray-600 hover:bg-gray-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                {feedbackSubmitting ? "Enviando…" : "Enviar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Research panel reopen button (floating, shown when panel is closed but has data) */}
      {!showResearchPanel && researchSteps.length > 0 && (
        <button
          onClick={() => setShowResearchPanel(true)}
          className="fixed top-20 right-4 z-30 bg-[#1a2744]/90 backdrop-blur-sm border border-white/10 rounded-full p-2.5 text-gray-400 hover:text-white hover:bg-white/10 transition-colors shadow-lg"
          title="Ver actividad de investigación"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </button>
      )}

      {/* Research Activity Panel (right sidebar) */}
      {showResearchPanel && researchSteps.length > 0 && (
        <aside className="fixed top-16 right-0 bottom-0 z-40 w-80 bg-[#0b1426]/95 backdrop-blur-md border-l border-white/10 flex flex-col transition-transform duration-300">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="text-sm font-semibold text-white">Actividad de investigación</h3>
              <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 bg-amber-500/20 border border-amber-400/30 rounded" title="Motor académico exclusivo">
                Investigación
              </span>
            </div>
            <button onClick={() => setShowResearchPanel(false)} className="text-gray-400 hover:text-white p-1 transition-colors">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          {researchProgress && (
            <div className="px-4 py-2 border-b border-white/10 bg-white/5">
              <div className="flex justify-between text-[10px] text-gray-400">
                <span>{researchProgress.found} encontradas</span>
                <span>{researchProgress.read} leídas</span>
                <span>{researchProgress.elapsedSeconds}s</span>
              </div>
              <div className="w-full h-1 bg-white/10 rounded-full mt-1 overflow-hidden">
                <div className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all" style={{ width: `${Math.min(100, researchProgress.elapsedSeconds / 2.4)}%` }} />
              </div>
            </div>
          )}
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
            {researchSteps.map((step, i) => {
              const iconMap: Record<string, string> = { plan: "📋", search: "🔍", search_result: "📄", refine: "🎯", filter: "⚙️", read: "📖", read_done: "✅", read_fail: "❌", follow: "🔗", complete: "🏁", sources: "📊" };
              const icon = iconMap[step.action] || "•";
              return (
                <div key={i} className="text-[11px] leading-relaxed">
                  <div className="flex items-start gap-1.5">
                    <span className="flex-shrink-0 mt-0.5">{icon}</span>
                    <div className="min-w-0">
                      <p className="text-gray-300">{step.detail}</p>
                      {step.result && <p className="text-gray-500">{step.result}</p>}
                      {step.url && (
                        <a href={step.url} target="_blank" rel="noopener noreferrer" className="text-cyan-500 hover:text-cyan-400 truncate block">{step.url.replace(/^https?:\/\//, '').substring(0, 50)}</a>
                      )}
                    </div>
                    <span className="text-gray-600 flex-shrink-0 ml-auto">{step.elapsed}s</span>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>
      )}
    </section>
  );
}

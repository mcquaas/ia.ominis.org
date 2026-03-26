"use client";

import { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import ChatSidebar from "@/components/ChatSidebar";
import Footer from "@/components/Footer";
import * as chatService from "@/services/chat";
import type { ConversationSummary } from "@/services/chat";
import * as feedbackService from "@/services/feedback";
import { getChatDefaults, getToken } from "@/services/auth";

interface Source {
  title: string;
  url: string;
  score?: number;
  sourceType?: "rag" | "web" | "pubmed" | "openscholar" | "clinicaltrials" | "directorio_mx" | "allcan" | "pdf" | "csv" | "xlsx" | "xls" | "sav";
  authors?: string;
  year?: string;
  journal?: string;
  doi?: string;
  ref_num?: number;
  nctId?: string;
  ctStartDate?: string;
  ctLocationsSummary?: string;
  ctFallbackSearchUrl?: string;
  ctClassicShowUrl?: string;
  meta?: {
    page_number?: number;
    file_name?: string;
    chunk_id?: string;
    text_excerpt?: string;
  };
  snippet?: string;
}

interface SourceWithDisplayNum extends Source {
  displayNum: number;
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
  /** Retrieved but not cited in the answer (SSE `sources_not_used`). */
  sourcesNotUsed?: Source[];
  images?: string[];
  charts?: ChartData[];
  isReport?: boolean;
  degradation?: string;
  model?: string;  // e.g. "ominis-2.0" from done event (shown as Investigación)
  dbMessageId?: number;  // DB id when persisted (for feedback)
  reportTitle?: string;   // from backend for PDF filename (e.g. "Salud Digital y Reforma LGS")
  /** English keywords sent to ClinicalTrials.gov API (SSE clinical_trials_keywords). */
  clinicalTrialsKeywords?: string;
  /** Backend hints: add missing tools or «profundizar» second pass (SSE suggested_add_tools). */
  suggestedAddTools?: { id: string; label: string; extend?: boolean }[];
}

interface ModelOption {
  id: string;
  displayName: string;
  description: string;
  isDefault: boolean;
  allowed?: boolean;
  reason?: string; // "login_required" | "request_superadmin" | "admin_only"
}

const HISTORY_ENABLED_KEY = "ominis_history_enabled";

/** Max wait for `/api/query-stream` (SSE). Must cover Vast Serverless cold start; align with backend `vast_serverless_client_timeout` (default 900s). */
const QUERY_STREAM_CLIENT_TIMEOUT_MS = 900_000;

function clinicalTrialCardTitle(source: Source): string {
  const raw = (source.title || "").trim();
  const short = raw.replace(/\s*\(NCT\d+\)\s*$/i, "").trim();
  if (short.length > 140) return `${short.slice(0, 137)}…`;
  return short || raw || "Ensayo clínico";
}

/** Decode HTML entities so they display correctly (e.g. &oacute; → ó). Preserves markdown. */
function decodeHtmlEntities(text: string): string {
  if (!text || typeof text !== "string") return text;
  const entities: Record<string, string> = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'",
    "&nbsp;": "\u00A0", "&aacute;": "á", "&eacute;": "é", "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú",
    "&Aacute;": "Á", "&Eacute;": "É", "&Iacute;": "Í", "&Oacute;": "Ó", "&Uacute;": "Ú",
    "&ntilde;": "ñ", "&Ntilde;": "Ñ", "&uuml;": "ü", "&Uuml;": "Ü",
    "&copy;": "©", "&reg;": "®", "&trade;": "™",
  };
  return text.replace(/&(?:#(\d+)|#x([0-9a-fA-F]+)|([a-zA-Z]+));/g, (_, dec, hex, name) => {
    if (dec != null) return String.fromCharCode(parseInt(dec, 10));
    if (hex != null) return String.fromCharCode(parseInt(hex, 16));
    return entities[`&${name};`] ?? `&${name};`;
  });
}

function buildContextSearchText(source: Source): string {
  const fromMeta = source.meta?.text_excerpt?.trim();
  if (fromMeta) {
    const cleaned = decodeHtmlEntities(fromMeta)
      .replace(/\s+/g, " ")
      .replace(/[\[\]{}<>]/g, " ")
      .trim();
    return cleaned.slice(0, 120);
  }
  const raw = decodeHtmlEntities(source.snippet || source.title || "");
  const cleaned = raw
    .replace(/\s+/g, " ")
    .replace(/[\[\]{}<>]/g, " ")
    .trim();
  return cleaned.slice(0, 120);
}

function isCsvLikeUrl(url: string): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    return /\.csv(\?[^\s]*)?$/i.test(u.pathname) || u.pathname.toLowerCase().endsWith(".csv");
  } catch {
    return false;
  }
}

/** PDF file URLs — must not use HTML text fragments (#:~:text=), which break Chrome's PDF viewer. */
function isPdfUrl(url: string): boolean {
  if (!url) return false;
  try {
    const u = new URL(url.split("#")[0]);
    return /\.pdf(\?[^\s#]*)?$/i.test(u.pathname) || u.pathname.toLowerCase().endsWith(".pdf");
  } catch {
    return false;
  }
}

/** Server-side preview via `/api/csv-preview` (avoids browser CORS). */
function isCsvPreviewAllowedHost(url: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    const h = u.hostname.toLowerCase();
    if (h === "localhost" || h === "127.0.0.1") return true;
    if (h.endsWith("ominis.org")) return true;
    if (h.endsWith(".gob.mx")) return true;
    return false;
  } catch {
    return false;
  }
}

function buildSourceDeepLink(source: Source): string {
  const url = (source.url || "").trim();
  if (!url) return "";
  const base = url.split("#")[0];
  const searchText = buildContextSearchText(source);
  const pdf = isPdfUrl(url) || source.sourceType === "pdf";

  // PDF: use page + search in the hash (Chrome/Adobe-style). Never #:~:text= on PDFs — it can crash the viewer.
  if (pdf) {
    const page = source.meta?.page_number;
    if (page != null && page > 0) {
      const parts = [`page=${page}`];
      if (searchText) parts.push(`search=${encodeURIComponent(searchText)}`);
      return `${base}#${parts.join("&")}`;
    }
    return base;
  }

  // HTML/text deep link using text fragments (Chrome/Edge): #:~:text=...
  if (!url.includes("#") && /^https?:\/\//i.test(url) && searchText) {
    return `${base}#:~:text=${encodeURIComponent(searchText)}`;
  }

  return url;
}

/** Extract numbered questions (lines ending with ?) from plan message content for "Alcance de la investigación". */
function parsePlanQuestions(content: string): string[] {
  if (!content || typeof content !== "string") return [];
  const questions: string[] = [];
  const lines = content.split(/\r?\n/);
  for (const line of lines) {
    if (questions.length >= 4) break;
    const trimmed = line.trim();
    const match = trimmed.match(/^\s*(?:\d+[.)]|[-*])\s*(.+?\?)\s*$/);
    if (match) questions.push(match[1].trim());
  }
  return questions;
}

// ominis-2.0 (Mexican LLM by FUNSALUD)
// Data is stored in Mexico (S3 mx-central-1), no 3rd party models
// Inference runs on GPU for speed via /api/query-stream

interface MainLayoutProps {
  initialUuid?: string;
}

export default function MainLayout({ initialUuid }: MainLayoutProps = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, user, loading: authLoading } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState("");
  const [loadingModel, setLoadingModel] = useState<string | null>(null);
  /** GPU cold start: backend sends phase gpu_warmup + waitSeconds while waiting for first token */
  const [gpuWarmupHint, setGpuWarmupHint] = useState(false);
  const [gpuWaitSeconds, setGpuWaitSeconds] = useState<number | null>(null);
  const [ragSearchEnabled, setRagSearchEnabled] = useState(true);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [pubmedSearchEnabled, setPubmedSearchEnabled] = useState(true);
  const [openscholarSearchEnabled, setOpenscholarSearchEnabled] = useState(false);
  /** ClinicalTrials.gov (México); solo usuarios autenticados (el backend ignora si no hay JWT). */
  const [clinicalTrialsSearchEnabled, setClinicalTrialsSearchEnabled] = useState(false);
  const [doctorDirectorySearchEnabled, setDoctorDirectorySearchEnabled] = useState(false);
  const [allcanSearchEnabled, setAllcanSearchEnabled] = useState(false);
  const [researchModeEnabled, setResearchModeEnabled] = useState(false);
  const [research21Enabled, setResearch21Enabled] = useState(false); // Research 2.1 (deep multi-round + section-by-section) from Dashboard > Opciones
  const [publicAccessEnabled, setPublicAccessEnabled] = useState(true);
  const [chatDefaultsLoading, setChatDefaultsLoading] = useState(true);
  const [uploadedImages, setUploadedImages] = useState<Array<{ data: string; name: string }>>([]);
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; ext: string; text: string; extracting: boolean }>>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [showModelMenu, setShowModelMenu] = useState(false);
  const [plusMenuOpenDownward, setPlusMenuOpenDownward] = useState(false);
  const [plusMenuPosition, setPlusMenuPosition] = useState<{ left: number; top: number; openUpward?: boolean } | null>(null);
  const menuPortalRef = useRef<HTMLDivElement | null>(null);
  const [researchSteps, setResearchSteps] = useState<Array<{ action: string; detail: string; url?: string; result?: string; reasoning?: string; elapsed?: number }>>([]);
  const [researchProgress, setResearchProgress] = useState<{ found: number; read: number; totalSteps: number; elapsedSeconds: number } | null>(null);
  const [showResearchPanel, setShowResearchPanel] = useState(false);
  const [expandedResearchStepIndex, setExpandedResearchStepIndex] = useState<number | null>(null);
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [scopeAnswers, setScopeAnswers] = useState<Record<string, string[]>>({}); // messageId -> answers for plan scope questions
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([
    { id: "ominis-2.0", displayName: "Ominis 2.0", description: "Uso general (Qwen)", isDefault: true },
  ]);
  const [selectedModel, setSelectedModel] = useState<string>("ominis-2.0");
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [feedbackByMessageId, setFeedbackByMessageId] = useState<Record<string, "positive" | "negative">>({});
  const [feedbackModalMessageId, setFeedbackModalMessageId] = useState<string | null>(null);
  const [feedbackReasonCategory, setFeedbackReasonCategory] = useState<string | null>(null);
  const [feedbackReasonText, setFeedbackReasonText] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [modelAccessMessage, setModelAccessMessage] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);
  const modelMenuRef = useRef<HTMLDivElement>(null);

  // When + menu opens, choose placement and position for portal (so it's not clipped by overflow-hidden)
  useLayoutEffect(() => {
    if (!showPlusMenu || !plusMenuRef.current) {
      setPlusMenuPosition(null);
      return;
    }
    const rect = plusMenuRef.current.getBoundingClientRect();
    const spaceAbove = rect.top;
    const spaceBelow = typeof window !== "undefined" ? window.innerHeight - rect.bottom : 0;
    setPlusMenuOpenDownward(spaceBelow >= spaceAbove);
    const openUpward = spaceBelow < 220;
    const top = openUpward ? rect.top : rect.top + rect.height / 2;
    setPlusMenuPosition({ left: rect.right + 8, top, openUpward });
  }, [showPlusMenu]);
  const runStreamRef = useRef<(q: string, history: Message[], userMsg: Message, opts: { messageContent: string; hadImages: boolean; currentImages: string[]; currentFileContext: string }) => Promise<void>>(null);

  // Chat history state — closed by default on mobile so it doesn't take space
  const [sidebarOpen, setSidebarOpen] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches) {
      setSidebarOpen(true);
    }
  }, []);

  // Apply server-configured chat defaults on mount (Investigación, Ominis, PubMed, Web)
  useEffect(() => {
    setChatDefaultsLoading(true);
    getChatDefaults()
      .then((d) => {
        setResearchModeEnabled(d.research_mode ?? false);
        setRagSearchEnabled(d.rag_search);
        setWebSearchEnabled(d.web_search);
        setPubmedSearchEnabled(d.pubmed_search);
        setOpenscholarSearchEnabled(d.openscholar_search ?? false);
        setResearch21Enabled(d.research_2_1 ?? false);
        setPublicAccessEnabled(d.public_access_enabled ?? true);
      })
      .catch(() => {
        // Keep current defaults on error.
        setPublicAccessEnabled(true);
      })
      .finally(() => setChatDefaultsLoading(false));
  }, []);

  // When chat requires login, send anonymous users straight to login (preserve return URL).
  useEffect(() => {
    if (authLoading || chatDefaultsLoading) return;
    if (publicAccessEnabled || isAuthenticated) return;
    if (typeof window === "undefined") return;
    const q = window.location.search.replace(/^\?/, "");
    const base = pathname || "/c";
    const returnTo = q ? `${base}?${q}` : base;
    router.replace(`/login?next=${encodeURIComponent(returnTo)}`);
  }, [
    authLoading,
    chatDefaultsLoading,
    publicAccessEnabled,
    isAuthenticated,
    pathname,
    router,
  ]);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [historyEnabled, setHistoryEnabled] = useState(true);

  const loadConversations = useCallback(async () => {
    try {
      const res = await chatService.listConversations();
      setConversations(res.data);
    } catch (err) {
      console.warn("[Ominis] Failed to load conversations:", err);
    }
  }, []);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [activeStreamAssistantId, setActiveStreamAssistantId] = useState<string | null>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  /** When true, user left the bottom; don't auto-scroll until they scroll back to the bottom */
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false);
  /** Same as userHasScrolledUp, updated synchronously in scroll — avoids auto-scroll winning a frame before React re-renders */
  const userHasScrolledUpRef = useRef(false);
  const [sourcePreviewSource, setSourcePreviewSource] = useState<Source | null>(null);
  const [csvPreview, setCsvPreview] = useState<{
    url: string;
    title?: string;
    rows: string[][];
    truncated: boolean;
    rawText: string;
  } | null>(null);
  const [csvPreviewLoading, setCsvPreviewLoading] = useState(false);
  const [csvPreviewError, setCsvPreviewError] = useState<string | null>(null);
  const [expandedClinicalTrialByUrl, setExpandedClinicalTrialByUrl] = useState<Record<string, boolean>>({});

  const openCsvPreview = useCallback(async (url: string, title?: string) => {
    setCsvPreviewError(null);
    setCsvPreviewLoading(true);
    setCsvPreview(null);
    try {
      const res = await fetch(`/api/csv-preview?url=${encodeURIComponent(url)}`);
      const data = (await res.json().catch(() => ({}))) as {
        error?: string;
        rows?: string[][];
        truncated?: boolean;
        rawText?: string;
      };
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setCsvPreview({
        url,
        title,
        rows: data.rows || [],
        truncated: !!data.truncated,
        rawText: data.rawText || "",
      });
    } catch (e) {
      setCsvPreviewError(e instanceof Error ? e.message : "Error al cargar CSV");
    } finally {
      setCsvPreviewLoading(false);
    }
  }, []);

  function SourceAnchor(props: { source: Source; className?: string; children: React.ReactNode }) {
    const { source, className, children } = props;
    const href = buildSourceDeepLink(source);
    const csvOk = isCsvLikeUrl(source.url) && isCsvPreviewAllowedHost(source.url);
    if (csvOk) {
      return (
        <button
          type="button"
          onClick={() => void openCsvPreview(source.url, source.title)}
          className={className}
        >
          {children}
        </button>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
        {children}
      </a>
    );
  }

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
  }, [isAuthenticated, user, loadConversations]);

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
          const row = m as {
            sources?: unknown;
            sources_not_used?: Source[];
          };
          let sources: Source[] | undefined;
          let sourcesNotUsed: Source[] | undefined = row.sources_not_used;
          const raw = row.sources;
          if (Array.isArray(raw)) {
            sources = raw as Source[];
          } else if (raw && typeof raw === "object" && raw !== null && "used" in raw) {
            const o = raw as { used?: Source[]; not_used?: Source[] };
            sources = o.used;
            if (!sourcesNotUsed?.length && o.not_used?.length) sourcesNotUsed = o.not_used;
          } else {
            sources = raw as Source[] | undefined;
          }
          loaded.push({
            id: String(m.id),
            role: m.role as "user" | "assistant",
            content: m.content,
            sources,
            sourcesNotUsed,
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
  }, [initialUuid, isAuthenticated, loadConversations]);

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
      sourcesNotUsed?: Source[],
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
            sources: sources as unknown as Array<Record<string, unknown>> | undefined,
            sources_not_used:
              sourcesNotUsed && sourcesNotUsed.length > 0
                ? (sourcesNotUsed as unknown as Array<Record<string, unknown>>)
                : undefined,
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

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    const el = messagesContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  };

  const SCROLL_AT_BOTTOM_THRESHOLD = 100;

  useEffect(() => {
    if (activeStreamAssistantId) return;
    if (!userHasScrolledUp) scrollToBottom();
    inputRef.current?.focus();
  }, [messages, userHasScrolledUp, activeStreamAssistantId]);

  // When loading (streaming), only auto-scroll if user hasn't scrolled up — unless we follow the answer anchor
  useEffect(() => {
    if (activeStreamAssistantId) return;
    if (isLoading && !userHasScrolledUp) scrollToBottom();
  }, [isLoading, loadingStatus, userHasScrolledUp, activeStreamAssistantId]);

  // While streaming, follow new content by pinning the thread to the bottom — never scrollIntoView on the
  // answer top (that yanks the user away from sources below). userHasScrolledUpRef is sync-updated on scroll.
  useLayoutEffect(() => {
    if (!activeStreamAssistantId || userHasScrolledUpRef.current) return;
    const el = messagesContainerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
  }, [messages, activeStreamAssistantId]);

  // Scroll-to-top visibility + pin state (ref updated in the same tick as scroll for reliable stream follow)
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const onScroll = () => {
      setShowScrollTop(el.scrollTop > 200);
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_AT_BOTTOM_THRESHOLD;
      const pinned = !atBottom;
      userHasScrolledUpRef.current = pinned;
      setUserHasScrolledUp(pinned);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
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
          sources.push({ title, url, sourceType: "web" });
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
          sources.push({ title, url, sourceType: "web" });
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
    // When backend already provides stable reference numbers, preserve them exactly.
    // Merging extracted URL sources here can shift indices and break [N] mapping.
    if (existingSources.some((s) => typeof s.ref_num === "number")) return existingSources;

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
    // Keep backend citation numbers stable when ref_num is present.
    // Avoid client-side URL/author remapping that can desync source cards.
    if (sources.some((s) => typeof s.ref_num === "number")) {
      return content.trim();
    }

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
    let source = sources.find((s: Source) => s.ref_num === num);
    // Fallback to array index
    if (!source) {
      source = sources[num - 1];
    }
    if (source && source.url) {
      const citationHref = buildSourceDeepLink(source);
      let citationTitle = decodeHtmlEntities(source.title || "");

      if (source.sourceType === "pdf" && source.meta?.page_number) {
        citationTitle = source.title
          ? `${citationTitle} (página ${source.meta.page_number})`
          : `Página ${source.meta.page_number}`;
      }

      const csvOk = isCsvLikeUrl(source.url) && isCsvPreviewAllowedHost(source.url);
      const citeCls =
        "inline-flex items-center justify-center w-3.5 h-3.5 text-[9px] font-medium bg-blue-500 hover:bg-blue-400 text-white rounded-full align-super mx-0.5 transition-colors" +
        (csvOk ? " cursor-pointer" : "");

      if (csvOk) {
        return (
          <button
            key={key}
            type="button"
            onClick={() => void openCsvPreview(source.url, source.title)}
            className={citeCls}
            title={citationTitle}
          >
            {sourceNum}
          </button>
        );
      }

      return (
        <a
          key={key}
          href={citationHref}
          target="_blank"
          rel="noopener noreferrer"
          className={citeCls}
          title={citationTitle}
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
        <span key={lIdx} className="flex gap-2 mb-2 first:mt-0">
          <span className="flex-shrink-0 text-gray-500">•</span>
          <span className="flex-1 min-w-0">
            {renderInlineContent(bulletMatch[1], sources, `p${pIdx}-l${lIdx}`)}
          </span>
        </span>
      );
    }

    // Check for numbered list (1. item, 2. item)
    const numberedMatch = trimmedLine.match(/^(\d+)\.\s+(.+)$/);
    if (numberedMatch) {
      return (
        <span key={lIdx} className="flex gap-2 mb-2 first:mt-0">
          <span className="flex-shrink-0 text-gray-400 text-xs tabular-nums">{numberedMatch[1]}.</span>
          <span className="flex-1 min-w-0">
            {renderInlineContent(numberedMatch[2], sources, `p${pIdx}-l${lIdx}`)}
          </span>
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
      <div key={keyOffset} className="space-y-4">
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

  // Strip LLM-generated "Referencias" / "Fuentes" block (we show compact refs + lupa from sources list)
  const stripReferenciasBlock = (text: string): string => {
    const lines = text.split("\n");
    const result: string[] = [];
    let stripMode = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();
      // Start of referencias block (plain or markdown ##)
      if (/^(##\s*)?(Referencias?|Fuentes?|Bibliograf[ií]a|Sources?):\s*$/i.test(trimmed)) {
        stripMode = true;
        continue;
      }
      if (/^##\s+(Referencias?|Fuentes?|Bibliograf[ií]a|Sources?)\s*$/i.test(trimmed)) {
        stripMode = true;
        continue;
      }
      // Lines that look like "[N] Title" or "N. Title" when in strip mode
      if (stripMode) {
        if (/^\[\d+\]\s*.+/.test(trimmed) || /^\d+\.\s+.+/.test(trimmed)) continue;
        if (trimmed === "" || /^[-*]\s*/.test(trimmed)) continue;
        if (/^URL:\s*/i.test(trimmed) || /^Content:\s*/i.test(trimmed) || trimmed === "---") continue;
        // Exit strip mode when we hit a new section (## or code block) so we don't strip the rest of the report
        if (/^##\s+/.test(trimmed) || /^```/.test(trimmed)) stripMode = false;
        else continue; // skip any other line that is part of the reference block (e.g. content body)
      }
      result.push(line);
    }
    return result.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  };

  // Replace "RAG" with "OMINIS" in LLM output so references always show OMINIS
  const normalizeRagToOminis = (text: string): string =>
    text.replace(/\bRAG\b/g, "OMINIS");

  // Remove "OPENSCHOLAR — " or "OPENSCHOLAR - " from titles in content (report references)
  const stripOpenscholarPrefix = (text: string): string =>
    text.replace(/\bOPENSCHOLAR\s*[—\-]\s*/gi, "").replace(/\bOPENSCHOLAR\s+/gi, "");

  const renderContentWithCitations = (content: string, sources?: Source[]) => {
    const effectiveSrc = sources || [];
    const decodedContent = decodeHtmlEntities(content);
    let contentWithoutReferencias = stripReferenciasBlock(decodedContent);
    contentWithoutReferencias = normalizeRagToOminis(contentWithoutReferencias);
    contentWithoutReferencias = stripOpenscholarPrefix(contentWithoutReferencias);
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

  // Fetch available models from backend (with optional auth for allowed/reason per model)
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const token = getToken();
        const headers: HeadersInit = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;
        const modelsRes = await fetch("/api/models", { headers }).catch(() => null);
        if (modelsRes && modelsRes.ok) {
          const data = await modelsRes.json();
          if (data.models?.length > 0) {
            setAvailableModels(data.models);
            const defaultId = data.default || "ominis-2.0";
            const defaultAllowed = data.models.find((m: ModelOption) => m.id === defaultId)?.allowed !== false;
            setSelectedModel(defaultAllowed ? defaultId : "ominis-2.0");
          }
        }
      } catch {
        // Silently keep defaults if backend is unreachable
      }
    };
    fetchModels();
  }, [isAuthenticated]);

  // When Modo Investigación is turned on, auto-enable all four search sources so the report has enough sources.
  useEffect(() => {
    if (researchModeEnabled) {
      setRagSearchEnabled(true);
      setWebSearchEnabled(true);
      setPubmedSearchEnabled(true);
      setOpenscholarSearchEnabled(true);
    }
  }, [researchModeEnabled]);

  // When Modo Investigación is on, backend uses 128K if available (else 8K). Use Ominis branding only (dashboard can override displayName).
  const research128KModel = availableModels.find((m) => m.id === "ominis-2.0-research-128k");
  const research128KAvailable = Boolean(research128KModel && research128KModel.allowed !== false);
  // Prefer stream model id when available; always show Ominis-based names, never the underlying implementation name.
  const effectiveResearchModelLabel =
    researchModeEnabled && loadingModel === "ominis-2.0-research-128k"
      ? (research128KModel?.displayName || "Ominis 2.0 Research 128K")
      : researchModeEnabled && loadingModel === "ominis-2.0-research"
        ? (availableModels.find((m) => m.id === "ominis-2.0-research")?.displayName || "Ominis 2.0 Research 8K")
        : research128KAvailable
          ? (research128KModel?.displayName || "Ominis 2.0 Research 128K")
          : (availableModels.find((m) => m.id === "ominis-2.0-research")?.displayName || "Ominis 2.0 Research 8K");

  // Close menus when clicking outside (consider both trigger and portaled + menu)
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (plusMenuRef.current?.contains(target)) return;
      if (menuPortalRef.current?.contains(target)) return;
      if (modelMenuRef.current?.contains(target)) return;
      setShowPlusMenu(false);
      setShowModelMenu(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  type RunStreamOpts = {
    messageContent: string;
    hadImages: boolean;
    currentImages: string[];
    currentFileContext: string;
    /** When false, request uses manual toggles (e.g. after «Agregar»). Default: automated orchestration. */
    tool_automation?: boolean;
    /** Bump retrieval breadth (e.g. «profundizar» follow-up). */
    num_sources?: number;
  };

  const runStream = async (
    question: string,
    historyForRequest: Message[],
    userMessage: Message,
    opts: RunStreamOpts,
  ) => {
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    userHasScrolledUpRef.current = false;
    setUserHasScrolledUp(false);
    setLoadingStatus("Analizando...");
    setLoadingModel(selectedModel);
    setGpuWarmupHint(false);
    setGpuWaitSeconds(null);
    if (researchModeEnabled) {
      setResearchSteps([]);
      setResearchProgress(null);
      setExpandedResearchStepIndex(null);
      setShowResearchPanel(true);
    }
    try {
      const controller = new AbortController();
      const timeoutMs = QUERY_STREAM_CLIENT_TIMEOUT_MS;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      const history = historyForRequest.slice(-20).map((m) => ({ role: m.role, content: m.content }));
      const headers: HeadersInit = { "Content-Type": "application/json" };
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const body: Record<string, unknown> = {
        question: question || (opts.currentFileContext ? "Analiza el archivo adjunto" : "Describe esta imagen"),
        history,
        images: opts.currentImages.length > 0 ? opts.currentImages : undefined,
        model: selectedModel,
        research_mode: researchModeEnabled,
        // En modo investigación siempre activar las cuatro búsquedas (orden de importancia: Ominis, Academic, PubMed, Web)
        rag_search: researchModeEnabled ? true : ragSearchEnabled,
        web_search: researchModeEnabled ? true : webSearchEnabled,
        pubmed_search: researchModeEnabled ? true : pubmedSearchEnabled,
        openscholar_search: researchModeEnabled ? true : openscholarSearchEnabled,
        clinical_trials_search: isAuthenticated && clinicalTrialsSearchEnabled,
        doctor_directory_search: isAuthenticated && doctorDirectorySearchEnabled,
        allcan_search: isAuthenticated && allcanSearchEnabled,
        /** Haystack orchestrator selects sources from question + intent (LLM + heuristics). Set false for manual toggles only. */
        tool_automation: opts.tool_automation !== false,
        file_context: opts.currentFileContext || undefined,
        excluded_sources: researchModeEnabled ? Array.from(excludedSources) : undefined,
        research_2_1: researchModeEnabled ? research21Enabled : undefined,
      };
      if (typeof opts.num_sources === "number" && opts.num_sources > 0) {
        body.num_sources = Math.min(48, Math.floor(opts.num_sources));
      }
      const response = await fetch("/api/query-stream", { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
      if (!response.ok) {
        clearTimeout(timeoutId);
        throw new Error(`HTTP ${response.status}`);
      }
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
      let streamedCtKw = "";
      const assistantId = generateId();
      setActiveStreamAssistantId(assistantId);
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
            if (!line.startsWith("data: ")) continue;
            const jsonStr = line.slice(6);
            if (!jsonStr.trim()) continue;
            try {
              const eventData = JSON.parse(jsonStr);
              if (eventData.type === "status") {
                setLoadingStatus(eventData.message);
                setLoadingModel(eventData.model ?? null);
                if (eventData.phase === "gpu_warmup") setGpuWarmupHint(true);
                if (typeof eventData.waitSeconds === "number") setGpuWaitSeconds(eventData.waitSeconds);
              } else if (eventData.type === "research_step") {
                if (eventData.step) {
                  setResearchSteps((prev) => {
                    if (prev.length === 0) setShowResearchPanel(true);
                    return [...prev, eventData.step];
                  });
                }
                if (eventData.progress) setResearchProgress(eventData.progress);
              } else if (eventData.type === "chunk") {
                streamedContent += eventData.text || "";
                if (!messageAdded) {
                  messageAdded = true;
                  setIsLoading(false);
                  setLoadingStatus("");
                  setLoadingModel(null);
                  setGpuWarmupHint(false);
                  setGpuWaitSeconds(null);
                  setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: streamedContent, model: undefined, clinicalTrialsKeywords: streamedCtKw || undefined }]);
                } else {
                  setIsLoading(false);
                  setLoadingStatus("");
                  setLoadingModel(null);
                  setGpuWarmupHint(false);
                  setGpuWaitSeconds(null);
                  setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content: streamedContent } : m)));
                }
              } else if (eventData.type === "sources") {
                if (eventData.sources?.length > 0) {
                  streamedSources = eventData.sources;
                  const kw =
                    typeof eventData.clinical_trials_keywords === "string"
                      ? eventData.clinical_trials_keywords.trim()
                      : "";
                  if (kw) streamedCtKw = kw;
                  if (!messageAdded) {
                    messageAdded = true;
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: assistantId,
                        role: "assistant",
                        content: "",
                        sources: streamedSources,
                        clinicalTrialsKeywords: kw || undefined,
                      },
                    ]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, sources: streamedSources, clinicalTrialsKeywords: kw || m.clinicalTrialsKeywords }
                          : m,
                      ),
                    );
                  }
                }
              } else if (eventData.type === "charts") {
                if (eventData.charts?.length > 0) {
                  setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, charts: eventData.charts } : m)));
                }
              } else if (eventData.type === "done") {
                const finalContent = eventData.answer || streamedContent || "No pude generar una respuesta.";
                const finalSources: Source[] = Array.isArray(eventData.sources) ? eventData.sources : streamedSources;
                const notUsedRaw = eventData.sources_not_used;
                const sourcesNotUsed: Source[] | undefined =
                  Array.isArray(notUsedRaw) && notUsedRaw.length > 0 ? (notUsedRaw as Source[]) : undefined;
                const finalCharts = eventData.charts || undefined;
                const isReport = !!eventData.is_report;
                const modelUsed = eventData.model || undefined;
                const degradation = eventData.degradation || undefined;
                const reportTitle = eventData.report_title || undefined;
                const doneKw =
                  typeof eventData.clinical_trials_keywords === "string"
                    ? eventData.clinical_trials_keywords.trim()
                    : "";
                const ctKwFinal = doneKw || streamedCtKw || undefined;
                const suggestedRaw = eventData.suggested_add_tools;
                const suggestedAddTools =
                  Array.isArray(suggestedRaw) && suggestedRaw.length > 0
                    ? (suggestedRaw as { id: string; label: string; extend?: boolean }[])
                        .filter((x) => x && typeof x.id === "string" && typeof x.label === "string")
                        .map((x) => ({
                          id: x.id,
                          label: x.label,
                          ...(x.extend === true ? { extend: true as const } : {}),
                        }))
                    : undefined;
                if (!messageAdded) {
                  setMessages((prev) => [...prev, {
                    id: assistantId, role: "assistant", content: finalContent,
                    sources: finalSources.length > 0 ? finalSources : undefined,
                    sourcesNotUsed,
                    charts: finalCharts, isReport, model: modelUsed, degradation, reportTitle,
                    clinicalTrialsKeywords: ctKwFinal,
                    suggestedAddTools,
                  }]);
                } else {
                  setMessages((prev) => prev.map((m) =>
                    m.id === assistantId ? { ...m, content: finalContent, sources: finalSources.length > 0 ? finalSources : undefined, sourcesNotUsed: sourcesNotUsed ?? m.sourcesNotUsed, charts: finalCharts || m.charts, isReport: isReport || m.isReport, model: modelUsed || m.model, degradation, reportTitle: reportTitle ?? m.reportTitle, clinicalTrialsKeywords: ctKwFinal || m.clinicalTrialsKeywords, suggestedAddTools } : m
                  ));
                }
                setResearchSteps([]);
                setResearchProgress(null);
                setExpandedResearchStepIndex(null);
                persistMessages(
                  opts.messageContent,
                  finalContent,
                  finalSources.length > 0 ? finalSources : undefined,
                  opts.hadImages,
                  assistantId,
                  sourcesNotUsed,
                );
                setIsLoading(false);
                setLoadingStatus("");
                setLoadingModel(null);
                setGpuWarmupHint(false);
                setGpuWaitSeconds(null);
                if (researchModeEnabled && isReport) setResearchModeEnabled(false);
                inputRef.current?.focus();
                clearTimeout(timeoutId);
                return;
              } else if (eventData.type === "error") {
                throw new Error(eventData.message);
              }
            } catch (parseError) {
              if (parseError instanceof Error && parseError.message === (JSON.parse(jsonStr) as { message?: string })?.message) throw parseError;
            }
          }
        }
        if (streamedContent && !messageAdded) {
          setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: streamedContent, sources: streamedSources.length > 0 ? streamedSources : undefined, clinicalTrialsKeywords: streamedCtKw || undefined }]);
        }
        if (streamedContent) {
          persistMessages(opts.messageContent, streamedContent, streamedSources.length > 0 ? streamedSources : undefined, opts.hadImages, assistantId);
        }
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (error) {
      const errorText = error instanceof Error && error.name === "AbortError"
        ? "Tiempo de espera agotado. Por favor intenta de nuevo."
        : error instanceof Error ? error.message : "Error desconocido";
      setMessages((prev) => [...prev, { id: generateId(), role: "assistant", content: `Lo siento, hubo un error: ${errorText}. Por favor intenta de nuevo.` }]);
    } finally {
      setActiveStreamAssistantId(null);
      setLoadingStatus("");
      setLoadingModel(null);
      setGpuWarmupHint(false);
      setGpuWaitSeconds(null);
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };
  runStreamRef.current = runStream;

  const activateSuggestedToolId = (toolId: string) => {
    switch (toolId) {
      case "ominis_rag":
        setRagSearchEnabled(true);
        break;
      case "web":
        setWebSearchEnabled(true);
        break;
      case "pubmed":
        setPubmedSearchEnabled(true);
        break;
      case "openscholar":
        setOpenscholarSearchEnabled(true);
        break;
      case "clinical_trials":
        setClinicalTrialsSearchEnabled(true);
        break;
      case "doctor_directory_mx":
        setDoctorDirectorySearchEnabled(true);
        break;
      case "allcan_mexico":
        setAllcanSearchEnabled(true);
        break;
      default:
        break;
    }
  };

  const handleSuggestedAddTool = (toolId: string, toolLabel: string, extend?: boolean) => {
    if (isLoading) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser?.content?.trim()) return;
    activateSuggestedToolId(toolId);
    const shortName = toolLabel.replace(/\s*·\s*profundizar\s*$/i, "").trim();
    const followUpContent =
      extend === true
        ? `[Segunda búsqueda más profunda (${shortName}). Prioriza cifras, presupuestos, tablas, informes oficiales, CIEP, transparencia y PDFs institucionales. Cita cada dato con [N].]\n\n${lastUser.content}`
        : `[Ampliar fuentes: ${toolLabel}]\n\n${lastUser.content}`;
    const userMsg: Message = {
      id: generateId(),
      role: "user",
      content: followUpContent,
      images: lastUser.images,
    };
    const opts: RunStreamOpts = {
      messageContent: userMsg.content,
      hadImages: !!lastUser.images?.length,
      currentImages: lastUser.images ?? [],
      currentFileContext: uploadedFiles.filter((f) => f.text && !f.extracting).map((f) => `--- ${f.name} ---\n${f.text}`).join("\n\n"),
      tool_automation: false,
      num_sources: extend === true ? 14 : undefined,
    };
    void runStream(userMsg.content, messages, userMsg, opts);
  };

  const sendMessage = async () => {
    const question = input.trim();
    const hasAttachments = uploadedImages.length > 0 || uploadedFiles.length > 0;
    if ((!question && !hasAttachments) || isLoading) return;

    const attachmentParts: string[] = [];
    if (uploadedImages.length > 0) {
      attachmentParts.push(`${uploadedImages.length} imagen${uploadedImages.length > 1 ? "es" : ""}: ${uploadedImages.map((img) => img.name).join(", ")}`);
    }
    if (uploadedFiles.length > 0) {
      attachmentParts.push(`${uploadedFiles.length} archivo${uploadedFiles.length > 1 ? "s" : ""}: ${uploadedFiles.map((f) => f.name).join(", ")}`);
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

    setInput("");
    clearAllImages();
    if (researchModeEnabled && messages.length === 0) setExcludedSources(new Set());
    const opts: RunStreamOpts = {
      messageContent,
      hadImages: uploadedImages.length > 0,
      currentImages: uploadedImages.map((img) => img.data),
      currentFileContext: uploadedFiles.filter((f) => f.text && !f.extracting).map((f) => `--- ${f.name} ---\n${f.text}`).join("\n\n"),
    };
    await runStream(question, messages, userMessage, opts);
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
    const queryTitle = conv?.title ?? messages.find((m) => m.role === "user")?.content.slice(0, 100) ?? "(Título pendiente)";
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
    userHasScrolledUpRef.current = false;
    setUserHasScrolledUp(false);
    setLoadingStatus("Analizando...");
    setLoadingModel(selectedModel);
    setGpuWarmupHint(false);
    setGpuWaitSeconds(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), QUERY_STREAM_CLIENT_TIMEOUT_MS);

      const history = newMessages
        .slice(-20)
        .map(m => ({ role: m.role, content: m.content }));

      // Use streaming endpoint (send auth for model access)
      const endpoint = "/api/query-stream";
      const headers: HeadersInit = { "Content-Type": "application/json" };
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify({
          question: question,
          history: history,
          images: originalMessage.images || undefined,
          model: selectedModel,
          // En modo investigación siempre activar las cuatro búsquedas
          rag_search: researchModeEnabled ? true : ragSearchEnabled,
          web_search: researchModeEnabled ? true : webSearchEnabled,
          pubmed_search: researchModeEnabled ? true : pubmedSearchEnabled,
          openscholar_search: researchModeEnabled ? true : openscholarSearchEnabled,
          clinical_trials_search: isAuthenticated && clinicalTrialsSearchEnabled,
          doctor_directory_search: isAuthenticated && doctorDirectorySearchEnabled,
          allcan_search: isAuthenticated && allcanSearchEnabled,
          tool_automation: true,
          iterations: undefined,
          max_total_sources: undefined,
          max_follow_links: undefined,
          max_trusted_sources: undefined,
          time_budget_seconds: undefined,
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
      let streamedCtKw = "";
      const assistantId = generateId();
      setActiveStreamAssistantId(assistantId);
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
                  setLoadingModel(eventData.model ?? null);
                  if (eventData.phase === "gpu_warmup") setGpuWarmupHint(true);
                  if (typeof eventData.waitSeconds === "number") setGpuWaitSeconds(eventData.waitSeconds);

                } else if (eventData.type === "chunk") {
                  streamedContent += eventData.text || "";
                  if (!messageAdded) {
                    messageAdded = true;
                    setIsLoading(false);
                    setLoadingStatus("");
                    setLoadingModel(null);
                    setGpuWarmupHint(false);
                    setGpuWaitSeconds(null);
                    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: streamedContent, clinicalTrialsKeywords: streamedCtKw || undefined }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) => m.id === assistantId ? { ...m, content: streamedContent } : m)
                    );
                  }

                } else if (eventData.type === "sources") {
                  if (eventData.sources?.length > 0) {
                    streamedSources = eventData.sources;
                    const kw =
                      typeof eventData.clinical_trials_keywords === "string"
                        ? eventData.clinical_trials_keywords.trim()
                        : "";
                    if (kw) streamedCtKw = kw;
                    setMessages((prev) => {
                      const exists = prev.some((m) => m.id === assistantId);
                      if (!exists) {
                        return [
                          ...prev,
                          {
                            id: assistantId,
                            role: "assistant",
                            content: "",
                            sources: streamedSources,
                            clinicalTrialsKeywords: kw || undefined,
                          },
                        ];
                      }
                      return prev.map((m) =>
                        m.id === assistantId
                          ? { ...m, sources: streamedSources, clinicalTrialsKeywords: kw || m.clinicalTrialsKeywords }
                          : m,
                      );
                    });
                    messageAdded = true;
                  }

                } else if (eventData.type === "done") {
                  const finalContent = eventData.answer || streamedContent || "No pude generar una respuesta.";
                  const finalSources: Source[] = Array.isArray(eventData.sources) ? eventData.sources : streamedSources;
                  const notUsedRaw = eventData.sources_not_used;
                  const sourcesNotUsed: Source[] | undefined =
                    Array.isArray(notUsedRaw) && notUsedRaw.length > 0 ? (notUsedRaw as Source[]) : undefined;
                  const degradation = eventData.degradation || undefined;
                  const isReport = !!eventData.is_report;
                  const doneKw =
                    typeof eventData.clinical_trials_keywords === "string"
                      ? eventData.clinical_trials_keywords.trim()
                      : "";
                  const ctKwFinal = doneKw || streamedCtKw || undefined;
                  const suggestedRaw2 = eventData.suggested_add_tools;
                  const suggestedAddTools2 =
                    Array.isArray(suggestedRaw2) && suggestedRaw2.length > 0
                      ? (suggestedRaw2 as { id: string; label: string; extend?: boolean }[])
                          .filter((x) => x && typeof x.id === "string" && typeof x.label === "string")
                          .map((x) => ({
                            id: x.id,
                            label: x.label,
                            ...(x.extend === true ? { extend: true as const } : {}),
                          }))
                      : undefined;

                  if (!messageAdded) {
                    setMessages((prev) => [...prev, {
                      id: assistantId, role: "assistant",
                      content: finalContent,
                      sources: finalSources.length > 0 ? finalSources : undefined,
                      sourcesNotUsed,
                      degradation,
                      isReport,
                      clinicalTrialsKeywords: ctKwFinal,
                      suggestedAddTools: suggestedAddTools2,
                    }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) => m.id === assistantId
                        ? { ...m, content: finalContent, sources: finalSources.length > 0 ? finalSources : m.sources, sourcesNotUsed: sourcesNotUsed ?? m.sourcesNotUsed, degradation, isReport, clinicalTrialsKeywords: ctKwFinal || m.clinicalTrialsKeywords, suggestedAddTools: suggestedAddTools2 ?? m.suggestedAddTools }
                        : m)
                    );
                  }

                  // Persist to backend
                  persistMessages(
                    userMessageContent,
                    finalContent,
                    finalSources.length > 0 ? finalSources : undefined,
                    hadImages,
                    undefined,
                    sourcesNotUsed,
                  );

                  setIsLoading(false);
                  setLoadingStatus("");
                  setLoadingModel(null);
                  setGpuWarmupHint(false);
                  setGpuWaitSeconds(null);
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
      setActiveStreamAssistantId(null);
      setLoadingStatus("");
      setLoadingModel(null);
      setGpuWarmupHint(false);
      setGpuWaitSeconds(null);
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
    "¿Cuáles son las principales causas de muerte en México?",
    "¿Qué fuentes de información sobre Cáncer existen?",
    "¿Cuáles son los diferentes sistemas de salud y a quiénes atienden?",
    "¿Qué guías clínicas recientes existen para hipertensión?",
  ];

  const hasMessages = messages.length > 0;
  const [footerExpanded, setFooterExpanded] = useState(false);

  // Guard against showing the chat UI to anonymous users when public access is disabled.
  if (authLoading || chatDefaultsLoading) {
    return (
      <section className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
      </section>
    );
  }

  if (!publicAccessEnabled && !isAuthenticated) {
    return (
      <section className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
      </section>
    );
  }

  const renderModelPicker = () => {
    const current = availableModels.find((m) => m.id === selectedModel);
    const currentLabel = current?.displayName ?? selectedModel;
    return (
      <div className="relative min-w-0 flex-1 lg:flex-initial lg:max-w-[min(100%,20rem)]" ref={modelMenuRef}>
        <button
          type="button"
          onClick={() => {
            setShowModelMenu((v) => !v);
            setShowPlusMenu(false);
          }}
          className={`flex items-center gap-1.5 w-full lg:w-auto max-w-full rounded-lg px-2 py-1.5 text-left text-sm font-medium transition-colors ${showModelMenu ? "bg-white/10 text-white" : "text-white/90 hover:bg-white/10 hover:text-white"}`}
          aria-expanded={showModelMenu}
          aria-haspopup="listbox"
          title="Modelo"
        >
          <span className="truncate min-w-0">{currentLabel}</span>
          <svg className={`w-4 h-4 flex-shrink-0 text-gray-400 transition-transform ${showModelMenu ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {showModelMenu && (
          <div
            className="absolute left-0 top-full z-[210] mt-1 w-[min(calc(100vw-2rem),20rem)] max-h-[min(60vh,420px)] overflow-y-auto rounded-xl border border-white/10 bg-[#1a2744] py-1 shadow-xl"
            role="listbox"
            aria-label="Elegir modelo"
          >
            {availableModels.map((m) => {
              const locked = m.allowed === false;
              const title = locked
                ? (m.reason === "login_required"
                  ? "Inicia sesión para usar este modelo"
                  : m.reason === "admin_only"
                    ? "Solo administradores pueden usar este modelo (GPT / gpt-oss)"
                    : "Solicita acceso al SuperAdmin para usar este modelo")
                : undefined;
              const lockMessage = locked
                ? (m.reason === "login_required"
                  ? "Inicia sesión para usar este modelo."
                  : m.reason === "admin_only"
                    ? "Solo administradores pueden usar GPT (gpt-oss)."
                    : "Solicita acceso al SuperAdmin para usar este modelo.")
                : "";
              return (
                <button
                  key={m.id}
                  type="button"
                  role="option"
                  aria-selected={selectedModel === m.id}
                  title={title}
                  onClick={() => {
                    if (locked) {
                      setModelAccessMessage(lockMessage);
                      setTimeout(() => setModelAccessMessage(null), 4000);
                      return;
                    }
                    setSelectedModel(m.id);
                    setShowModelMenu(false);
                  }}
                  className={`flex w-full items-start justify-between gap-3 px-3 py-2.5 text-left text-sm transition-colors ${selectedModel === m.id ? "bg-white/10 text-white" : "text-gray-200 hover:bg-white/10 hover:text-white"} ${locked ? "opacity-80" : ""}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{m.displayName}</span>
                      {locked && (
                        <svg className="w-3.5 h-3.5 flex-shrink-0 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                      )}
                    </div>
                    {m.description ? (
                      <p className="mt-0.5 text-xs leading-snug text-gray-500 line-clamp-2">{m.description}</p>
                    ) : null}
                  </div>
                  {selectedModel === m.id && !locked ? (
                    <svg className="w-4 h-4 flex-shrink-0 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : null}
                </button>
              );
            })}
            {modelAccessMessage ? (
              <p className="mx-2 mt-1 rounded-lg bg-amber-900/30 px-3 py-2 text-xs text-amber-300">{modelAccessMessage}</p>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  const renderPlusMenu = () => {
    if (!showPlusMenu) return null;
    const menuContent = (
      <>
        <button onClick={() => fileInputRef.current?.click()} className="w-full flex items-center gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
          Adjuntar archivos
        </button>
        <div className="border-t border-white/10 my-1" />
        <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Buscar en fuentes</div>
        <button onClick={() => setRagSearchEnabled(!ragSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Búsqueda en fuentes curadas por Ominis (bases de salud)">
          <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>Ominis</div>
          <div className={`w-8 h-5 rounded-full transition-colors ${ragSearchEnabled ? "bg-cyan-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${ragSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
        </button>
        <button onClick={() => setPubmedSearchEnabled(!pubmedSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Búsqueda en PubMed (literatura científica)">
          <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>PubMed</div>
          <div className={`w-8 h-5 rounded-full transition-colors ${pubmedSearchEnabled ? "bg-purple-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${pubmedSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
        </button>
        <button onClick={() => setWebSearchEnabled(!webSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Búsqueda en la web">
          <div className="flex items-center gap-3"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>Web</div>
          <div className={`w-8 h-5 rounded-full transition-colors ${webSearchEnabled ? "bg-blue-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${webSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
        </button>
        <button onClick={() => setOpenscholarSearchEnabled(!openscholarSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Búsqueda en Semantic Scholar (artículos académicos)">
          <div className="flex items-center gap-3"><svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg><span className="min-w-0 truncate">OpenScholar</span></div>
          <div className={`w-8 h-5 flex-shrink-0 rounded-full transition-colors ${openscholarSearchEnabled ? "bg-amber-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${openscholarSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
        </button>
        {isAuthenticated && (
          <button onClick={() => setClinicalTrialsSearchEnabled(!clinicalTrialsSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Ensayos clínicos en México (ClinicalTrials.gov)">
            <div className="flex items-center gap-3 min-w-0">
              <svg className="w-4 h-4 flex-shrink-0 text-teal-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>
              <span className="min-w-0 truncate">Ensayos (México)</span>
            </div>
            <div className={`w-8 h-5 flex-shrink-0 rounded-full transition-colors ${clinicalTrialsSearchEnabled ? "bg-teal-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${clinicalTrialsSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
          </button>
        )}
        {isAuthenticated && (
          <button onClick={() => setDoctorDirectorySearchEnabled(!doctorDirectorySearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Directorio de médicos (México)">
            <div className="flex items-center gap-3 min-w-0">
              <svg className="w-4 h-4 flex-shrink-0 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
              <span className="min-w-0 truncate">Directorio MX</span>
            </div>
            <div className={`w-8 h-5 flex-shrink-0 rounded-full transition-colors ${doctorDirectorySearchEnabled ? "bg-emerald-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${doctorDirectorySearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
          </button>
        )}
        {isAuthenticated && (
          <button onClick={() => setAllcanSearchEnabled(!allcanSearchEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm" title="Organizaciones All.Can México">
            <div className="flex items-center gap-3 min-w-0">
              <svg className="w-4 h-4 flex-shrink-0 text-sky-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
              <span className="min-w-0 truncate">All.Can México</span>
            </div>
            <div className={`w-8 h-5 flex-shrink-0 rounded-full transition-colors ${allcanSearchEnabled ? "bg-sky-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${allcanSearchEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
          </button>
        )}
        <div className="border-t border-white/10 my-1" />
        <div className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">Modo</div>
        <button onClick={() => setResearchModeEnabled(!researchModeEnabled)} className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-gray-300 hover:bg-white/10 hover:text-white transition-colors text-sm">
          <div className="flex flex-col items-start gap-0.5">
            <div className="flex items-center gap-3">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /></svg>
              <span>Investigación</span>
            </div>
            {researchModeEnabled && (
              <span className="text-[10px] text-gray-400 pl-7">
                Ominis-2.0-Research
              </span>
            )}
            {!researchModeEnabled && research128KAvailable && (
              <span className="text-[10px] text-gray-500 pl-7">Al activar: Ominis-2.0-Research</span>
            )}
          </div>
          <div className={`w-8 h-5 rounded-full flex-shrink-0 transition-colors ${researchModeEnabled ? "bg-emerald-500" : "bg-gray-600"} relative`}><div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${researchModeEnabled ? "translate-x-3.5" : "translate-x-0.5"}`} /></div>
        </button>
      </>
    );
    const wrapperClass = "min-w-[200px] max-h-[min(60vh,420px)] overflow-y-auto rounded-xl border border-white/10 bg-[#1a2744] py-2 shadow-xl z-[200]";
    if (plusMenuPosition && typeof document !== "undefined") {
      const isAbove = plusMenuPosition.openUpward === true;
      return createPortal(
        <div
          ref={(el) => { menuPortalRef.current = el; }}
          className={wrapperClass}
          style={{
            position: "fixed",
            left: plusMenuPosition.left,
            top: plusMenuPosition.top,
            transform: isAbove ? "translateY(-100%)" : "translateY(-50%)",
            zIndex: 200,
          }}
        >
          {menuContent}
        </div>,
        document.body
      );
    }
    return (
      <div
        className={`absolute left-0 ${wrapperClass} ${
          plusMenuOpenDownward ? "top-full mt-2" : "bottom-full mb-2"
        }`}
      >
        {menuContent}
      </div>
    );
  };

  return (
    <section className="h-screen pt-[calc(4rem+var(--banner-height,0px)+env(safe-area-inset-top))] relative flex flex-col overflow-hidden overflow-x-hidden w-full max-w-[100vw] min-w-0">
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
      <div className={`relative z-10 flex-1 flex flex-col min-h-0 min-w-0 transition-all duration-300 overflow-x-hidden w-full max-w-full ${sidebarOpen ? "lg:pl-72" : "lg:pl-10"}`}>
        <div className="flex-1 flex flex-col w-full min-w-0 mx-auto px-4 sm:px-6 min-h-0 max-w-full lg:max-w-3xl">
              {/* Mobile toolbar - hamburger (history) and + (new job) at top left */}
              <div className="relative z-30 flex items-center gap-2 py-2 flex-shrink-0 -mx-4 sm:-mx-6 px-4 sm:px-6 border-b border-white/10 mb-1">
                <button
                  type="button"
                  onClick={() => setSidebarOpen(true)}
                  className="lg:hidden flex-shrink-0 text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-lg transition-colors"
                  title="Historial de trabajos"
                  aria-label="Abrir historial"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                {renderModelPicker()}
                {isAuthenticated && (
                  <button
                    type="button"
                    onClick={handleNewChat}
                    className="lg:hidden flex-shrink-0 ml-auto text-gray-400 hover:text-white p-2 hover:bg-white/10 rounded-lg transition-colors"
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
                  <div className="w-full max-w-full lg:max-w-2xl">
                    {/* Capsules (research, model, attachments — Ominis/Web/PubMed inside input) */}
                    {(researchModeEnabled || uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                      <div className="flex items-center justify-center gap-1.5 mb-3 text-xs flex-wrap">
                        {researchModeEnabled && (
                          <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/15 backdrop-blur-sm border border-emerald-400/20 pl-2 pr-1 py-1 rounded-full">
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" /></svg>
                            Modo investigación
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
                              onClick={() => {
                                setShowPlusMenu(!showPlusMenu);
                                setShowModelMenu(false);
                              }}
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
                            {openscholarSearchEnabled && (
                              <span className="inline-flex items-center gap-0.5 text-amber-400 bg-amber-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                                OpenScholar
                                <button onClick={() => setOpenscholarSearchEnabled(false)} className="hover:text-amber-200 transition-colors p-0.5" title="Desactivar">
                                  <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                                </button>
                              </span>
                            )}
                            {isAuthenticated && clinicalTrialsSearchEnabled && (
                              <span className="inline-flex items-center gap-0.5 text-teal-300 bg-teal-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                                CT.gov
                                <button onClick={() => setClinicalTrialsSearchEnabled(false)} className="hover:text-teal-100 transition-colors p-0.5" title="Desactivar">
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
                          {message.role === "assistant" ? (
                            <div className="text-sm leading-relaxed scroll-mt-28 min-h-[1.5rem]">
                              {message.content?.trim()
                                ? renderContentWithCitations(message.content, effectiveSources)
                                : isLoading && activeStreamAssistantId === message.id && (effectiveSources?.length ?? 0) > 0 ? (
                                    <p className="text-gray-400 italic text-sm">Generando respuesta…</p>
                                  ) : null}
                            </div>
                          ) : (
                            <div className="text-sm leading-relaxed">
                              <p className="whitespace-pre-wrap">{decodeHtmlEntities(message.content)}</p>
                            </div>
                          )}

                          {/* Action buttons for assistant messages */}
                          {message.role === "assistant" && (
                            <div className="flex items-center gap-1.5 mt-2 pt-1">
                              {(message.model === "ominis-2.0-research" || message.model === "ominis-2.0-research-128k") && (
                                <span className="text-[9px] text-amber-300 bg-amber-500/15 border border-amber-400/30 rounded px-1.5 py-0.5 mr-1" title="Generado con motor Investigación">Investigación</span>
                              )}
                              {message.degradation && (
                                <span className="inline-flex items-center gap-1 text-amber-400 bg-amber-500/15 text-[10px] px-2 py-0.5 rounded-full" title={message.degradation}>
                                  <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                                  {message.degradation}
                                </span>
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
                                    onClick={() => handleDownloadPdf(message.content, message.reportTitle || message.content.split("\n")[0]?.replace(/^#+ /, "") || "Reporte")}
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

                          {message.role === "assistant" &&
                            message.suggestedAddTools &&
                            message.suggestedAddTools.length > 0 &&
                            !message.isReport && (
                            <div className="mt-2 pt-2 border-t border-white/5">
                              <p className="text-[10px] text-gray-500 mb-1.5 leading-snug">
                                {message.suggestedAddTools.some((t) => t.extend)
                                  ? "Amplía la respuesta (nueva pasada de búsqueda o más fuentes):"
                                  : "Agregar:"}
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {message.suggestedAddTools.map((t) => (
                                  <button
                                    key={`${t.id}-${t.extend ? "ex" : "add"}`}
                                    type="button"
                                    onClick={() => handleSuggestedAddTool(t.id, t.label, t.extend === true)}
                                    disabled={isLoading}
                                    className="text-[10px] px-2 py-1 rounded-md bg-white/5 border border-white/15 text-gray-200 hover:bg-cyan-500/15 hover:border-cyan-400/30 hover:text-white transition-colors disabled:opacity-40"
                                  >
                                    {t.label}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Alcance de la investigación (plan message) + Proceder */}
                          {researchModeEnabled && message.role === "assistant" && message.content.includes("?") && !message.content.includes("## Referencias") && !isLoading && (() => {
                            const questions = parsePlanQuestions(message.content);
                            if (questions.length === 0) return null;
                            const answersForInput = scopeAnswers[message.id] ?? questions.map(() => "");
                            return (
                              <div className="mt-4 pt-3 border-t border-white/10">
                                <h4 className="text-sm font-semibold text-white mb-0.5">Alcance de la investigación</h4>
                                <p className="text-[11px] text-gray-400 mb-3">Para acotar mejor el alcance de mi investigación, por favor comenta mis planteamientos (opcional).</p>
                                <div className="space-y-3 mb-4">
                                  {questions.map((q, i) => (
                                    <div key={i}>
                                      <p className="text-xs text-gray-300 mb-1">{q}</p>
                                      <input
                                        type="text"
                                        value={answersForInput[i] ?? ""}
                                        onChange={(e) => {
                                          const val = e.target.value;
                                          setScopeAnswers(prev => {
                                            const arr = prev[message.id] ?? questions.map(() => "");
                                            const next = [...arr];
                                            while (next.length <= i) next.push("");
                                            next[i] = val;
                                            return { ...prev, [message.id]: next };
                                          });
                                        }}
                                        placeholder="Tu comentario (opcional)"
                                        className="w-full px-2.5 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
                                      />
                                    </div>
                                  ))}
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const answers = scopeAnswers[message.id] ?? questions.map(() => "");
                                    const parts = answers.map((a, i) => (a.trim() ? `${i + 1}. ${a.trim()}` : "")).filter(Boolean);
                                    const proceedMessage = parts.length > 0 ? "Proceder\n\n" + parts.join("\n") : "Proceder";
                                    const userMsg: Message = { id: generateId(), role: "user", content: proceedMessage };
                                    const opts: RunStreamOpts = {
                                      messageContent: proceedMessage,
                                      hadImages: false,
                                      currentImages: [],
                                      currentFileContext: uploadedFiles.filter((f) => f.text && !f.extracting).map((f) => `--- ${f.name} ---\n${f.text}`).join("\n\n"),
                                    };
                                    runStreamRef.current?.(proceedMessage, messages, userMsg, opts);
                                  }}
                                  disabled={isLoading}
                                  className="w-full sm:w-auto mt-2 px-4 py-2.5 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-400/30 hover:bg-cyan-500/30 hover:text-white transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  Iniciar investigación
                                </button>
                              </div>
                            );
                          })()}

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

                          {/* Sources list: en modo investigación solo después del reporte final (solo fuentes citadas) */}
                          {(!researchModeEnabled || message.isReport === true) &&
                            ((effectiveSources?.length ?? 0) > 0) &&
                            (() => {
                            const withNum = (effectiveSources ?? [])
                              .filter((s: Source) => s.url && s.url.length > 0)
                              .map((source: Source, i: number) => ({ ...source, displayNum: source.ref_num ?? (i + 1) }));
                            const allDisplaySources = [...withNum].sort((a, b) => (a.displayNum as number) - (b.displayNum as number));
                            const citedRefNums = new Set<number>();
                            for (const m of (message.content || "").matchAll(/\[(\d+)\]/g)) {
                              const n = parseInt(m[1], 10);
                              if (Number.isFinite(n) && n > 0) citedRefNums.add(n);
                            }
                            const answerLower = (message.content || "").toLowerCase();
                            const isMentionedInAnswer = (source: SourceWithDisplayNum): boolean => {
                              if (!source.url) return false;
                              const title = (source.title || "").trim().toLowerCase();
                              if (title && title.length >= 16 && answerLower.includes(title.slice(0, 40))) {
                                return true;
                              }
                              try {
                                const host = new URL(buildSourceDeepLink(source)).hostname.replace(/^www\./, "").toLowerCase();
                                return host.length > 0 && answerLower.includes(host);
                              } catch {
                                return false;
                              }
                            };
                            const hasExplicitCitations = citedRefNums.size > 0;
                            const displaySources = allDisplaySources.filter((s) =>
                              hasExplicitCitations ? citedRefNums.has(Number(s.displayNum)) : isMentionedInAnswer(s)
                            );

                            // Show checkboxes for plan-phase sources: research mode, no References section, not loading, and plan-like content
                            const isPlanMessage = message.content.includes("?") || /plan|fuentes|proceder/i.test(message.content || "");
                            const showCheckboxes = researchModeEnabled && isPlanMessage && !message.content.includes("## Referencias") && !isLoading;

                            const splitSources = false;
                            const displayUnused: SourceWithDisplayNum[] = [];

                            if (displaySources.length === 0 && displayUnused.length === 0) return null;

                            const showClinicalTrialsResultsHeader =
                              Boolean(message.clinicalTrialsKeywords?.trim()) ||
                              displaySources.some((s) => s.sourceType === "clinicaltrials") ||
                              displayUnused.some((s) => s.sourceType === "clinicaltrials");
                            const ctKwLabel = message.clinicalTrialsKeywords?.trim() || "—";

                            const renderSourceItem = (source: SourceWithDisplayNum, idx: number) => {
                                    const isExcluded = excludedSources.has(source.url);
                                    if (source.sourceType === "clinicaltrials") {
                                      const expanded = expandedClinicalTrialByUrl[source.url] === true;
                                      const cardTitle = clinicalTrialCardTitle(source);
                                      const nct =
                                        source.nctId ||
                                        (source.url.match(/study\/(NCT\d+)/i)?.[1] ?? source.url.match(/NCT\d+/i)?.[0]) ||
                                        "";
                                      return (
                                        <li key={source.url || `src-${idx}`} className={`text-xs ${isExcluded ? "opacity-40" : ""}`}>
                                          <div className="flex items-start gap-1.5">
                                            {showCheckboxes && (
                                              <input
                                                type="checkbox"
                                                checked={!isExcluded}
                                                onChange={() => {
                                                  setExcludedSources((prev) => {
                                                    const next = new Set(prev);
                                                    if (next.has(source.url)) next.delete(source.url);
                                                    else next.add(source.url);
                                                    return next;
                                                  });
                                                }}
                                                className="mt-2 rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30 flex-shrink-0"
                                              />
                                            )}
                                            <div className="min-w-0 flex-1 rounded-lg border border-teal-500/25 bg-teal-500/5 overflow-hidden">
                                              <button
                                                type="button"
                                                className="w-full text-left px-2.5 py-2 hover:bg-white/5 transition-colors"
                                                onClick={() =>
                                                  setExpandedClinicalTrialByUrl((p) => ({
                                                    ...p,
                                                    [source.url]: !p[source.url],
                                                  }))
                                                }
                                              >
                                                <div className="flex items-start justify-between gap-2">
                                                  <div className="min-w-0">
                                                    <span className="text-teal-300 font-medium text-[11px]">[{source.displayNum}]</span>{" "}
                                                    <span className="text-white text-[12px] font-medium leading-snug">{cardTitle}</span>
                                                    {nct && (
                                                      <span className="block text-[10px] text-gray-500 font-mono mt-0.5">{nct}</span>
                                                    )}
                                                    <div className="text-[10px] text-gray-400 mt-1 space-x-1">
                                                      <span>
                                                        Inicio: {source.ctStartDate?.trim() ? source.ctStartDate : "—"}
                                                      </span>
                                                      <span>·</span>
                                                      <span className="line-clamp-2">
                                                        {source.ctLocationsSummary?.trim()
                                                          ? source.ctLocationsSummary
                                                          : "Ubicación: ver registro"}
                                                      </span>
                                                    </div>
                                                  </div>
                                                  <span className="text-gray-500 text-lg leading-none flex-shrink-0" aria-hidden>
                                                    {expanded ? "▾" : "▸"}
                                                  </span>
                                                </div>
                                              </button>
                                              {expanded && (
                                                <div className="px-2.5 pb-2.5 pt-0 border-t border-white/10 space-y-2">
                                                  {source.snippet ? (
                                                    <p className="text-[11px] text-gray-400 whitespace-pre-wrap leading-relaxed">
                                                      {decodeHtmlEntities(source.snippet)}
                                                    </p>
                                                  ) : null}
                                                  <div className="flex flex-col gap-1.5">
                                                    <a
                                                      href={buildSourceDeepLink(source)}
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                      className="inline-flex items-center gap-1 text-[11px] text-teal-300 hover:text-teal-200 font-medium"
                                                    >
                                                      Ficha del estudio (clinicaltrials.gov)
                                                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                      </svg>
                                                    </a>
                                                    {source.ctClassicShowUrl ? (
                                                      <a
                                                        href={source.ctClassicShowUrl}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="inline-flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-300"
                                                      >
                                                        Vista clásica (ct2/show) — si la ficha principal falla
                                                      </a>
                                                    ) : null}
                                                    {source.ctFallbackSearchUrl ? (
                                                      <a
                                                        href={source.ctFallbackSearchUrl}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="inline-flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-300"
                                                      >
                                                        Búsqueda por NCT en ClinicalTrials.gov
                                                      </a>
                                                    ) : null}
                                                  </div>
                                                </div>
                                              )}
                                            </div>
                                            <button
                                              type="button"
                                              onClick={() => setSourcePreviewSource(source)}
                                              className="flex-shrink-0 p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded transition-colors mt-0.5"
                                              title="Vista previa"
                                              aria-label="Vista previa de la fuente"
                                            >
                                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                              </svg>
                                            </button>
                                          </div>
                                        </li>
                                      );
                                    }
                                    const originLabel =
                                      source.sourceType === "pubmed"
                                        ? "PubMed"
                                        : source.sourceType === "rag"
                                          ? "Ominis"
                                          : source.sourceType === "openscholar"
                                            ? "OpenScholar"
                                            : source.sourceType === "directorio_mx"
                                              ? "Directorio MX"
                                              : source.sourceType === "allcan"
                                                ? "All.Can"
                                                : "Web";
                                    const originIcon = source.sourceType === "pubmed" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
                                    ) : source.sourceType === "rag" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>
                                    ) : source.sourceType === "openscholar" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
                                    ) : source.sourceType === "directorio_mx" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                                    ) : source.sourceType === "allcan" ? (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5 text-sky-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
                                    ) : (
                                      <svg className="w-3.5 h-3.5 inline-block align-text-bottom mr-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                                    );
                                    const displayTitle = (source.title && source.title.toLowerCase() !== "url")
                                      ? stripOpenscholarPrefix(decodeHtmlEntities(source.title))
                                      : (source.url ? (() => { try { return new URL(source.url).hostname; } catch { return source.url.slice(0, 50); } })() : "Sin título");
                                    const hasMeta = source.authors || source.year || source.doi || source.journal;
                                    return (
                                      <li key={source.url || `src-${idx}`} className={`text-xs ${isExcluded ? "opacity-40" : ""}`}>
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
                                          <div className="min-w-0 flex-1">
                                            <div className="font-medium text-white">
                                              [{source.displayNum}]{" "}
                                              <SourceAnchor
                                                source={source}
                                                className="text-blue-400 hover:text-blue-300 transition-colors hover:underline text-left"
                                              >
                                                {displayTitle}
                                              </SourceAnchor>
                                            </div>
                                            {hasMeta ? (
                                              <div className="text-[10px] text-gray-400 mt-0.5">
                                                <span className="inline-flex items-center mr-1.5">{originIcon}{originLabel}</span>
                                                {source.authors && <span>{source.authors.split(",").slice(0, 3).join(", ")}{source.authors.split(",").length > 3 ? " et al." : ""}</span>}
                                                {source.year && <span>{source.authors ? " · " : ""}{source.year}</span>}
                                                {source.journal && <span>{source.authors || source.year ? " · " : ""}{source.journal}</span>}
                                                {source.doi && <span>{source.authors || source.year || source.journal ? " · " : ""}{source.doi}</span>}
                                              </div>
                                            ) : (
                                              <div className="text-[10px] text-gray-500 mt-0.5 inline-flex items-center">{originIcon}{originLabel}</div>
                                            )}
                                            <SourceAnchor
                                              source={source}
                                              className="text-[9px] text-gray-500 hover:text-gray-400 truncate block mt-0.5 break-all text-left w-full"
                                            >
                                              {buildSourceDeepLink(source)}
                                            </SourceAnchor>
                                          </div>
                                          <button
                                            type="button"
                                            onClick={() => setSourcePreviewSource(source)}
                                            className="flex-shrink-0 p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded transition-colors"
                                            title="Vista previa"
                                            aria-label="Vista previa de la fuente"
                                          >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                                          </button>
                                        </div>
                                      </li>
                                    );
                            };

                            return (
                              <div className="mt-3 pt-3 border-t border-white/10">
                                {showClinicalTrialsResultsHeader && (
                                  <p className="text-[11px] text-teal-200/95 mb-2 leading-snug">
                                    Resultados de clinicaltrials.gov con palabras clave:{" "}
                                    <span className="font-medium text-white">&ldquo;{ctKwLabel}&rdquo;</span>
                                  </p>
                                )}
                                {showCheckboxes && (
                                  <p className="text-[10px] text-gray-500 mb-1.5">Por favor desmarca fuentes que no te parezcan relevantes.</p>
                                )}
                                {displaySources.length > 0 && (
                                  <>
                                    {splitSources && (
                                      <p className="text-[11px] text-cyan-200/90 font-medium mb-1.5">Fuentes citadas en la respuesta</p>
                                    )}
                                    <ul
                                      className={`space-y-1.5 ${
                                        splitSources
                                          ? "rounded-lg border border-cyan-500/25 bg-cyan-950/25 p-2"
                                          : ""
                                      }`}
                                    >
                                      {displaySources.map((s, i) => renderSourceItem(s, i))}
                                    </ul>
                                  </>
                                )}
                                {splitSources && displayUnused.length > 0 && (
                                  <>
                                    <p className="text-[11px] text-gray-400 mt-3 mb-1.5 leading-snug">
                                      También se consideraron estas fuentes (menos relevantes):
                                    </p>
                                    <ul className="space-y-1.5 rounded-lg border border-white/10 bg-white/[0.04] p-2">
                                      {displayUnused.map((s, i) => renderSourceItem(s, i))}
                                    </ul>
                                  </>
                                )}
                                {showCheckboxes && (() => {
                                  const questions = parsePlanQuestions(message.content);
                                  const ensureAnswers = (): string[] => {
                                    const cur = scopeAnswers[message.id];
                                    if (cur && cur.length >= questions.length) return cur;
                                    return questions.map((_, i) => (scopeAnswers[message.id]?.[i] ?? "") || "");
                                  };
                                  return (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        const answers = ensureAnswers();
                                        const parts = answers.map((a, i) => (a.trim() ? `${i + 1}. ${a.trim()}` : "")).filter(Boolean);
                                        const proceedMessage = parts.length > 0 ? "Proceder\n\n" + parts.join("\n") : "Proceder";
                                        const userMsg: Message = { id: generateId(), role: "user", content: proceedMessage };
                                        const opts: RunStreamOpts = {
                                          messageContent: proceedMessage,
                                          hadImages: false,
                                          currentImages: [],
                                          currentFileContext: uploadedFiles.filter((f) => f.text && !f.extracting).map((f) => `--- ${f.name} ---\n${f.text}`).join("\n\n"),
                                        };
                                        runStreamRef.current?.(proceedMessage, messages, userMsg, opts);
                                      }}
                                      disabled={isLoading}
                                      className="mt-4 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-400/30 hover:bg-cyan-500/30 hover:text-white transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      Iniciar investigación
                                    </button>
                                  );
                                })()}
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
                        <div className="flex items-center gap-2 min-w-0 flex-wrap">
                          {loadingStatus && (
                            <span className="text-gray-300 text-sm animate-pulse">{loadingStatus}</span>
                          )}
                          {loadingStatus && loadingModel && <span className="text-gray-500 mx-1">·</span>}
                          {loadingModel && (
                            <span className="text-[10px] text-cyan-300/90 font-medium whitespace-nowrap" title="LLM en uso">
                              {availableModels.find(m => m.id === loadingModel)?.displayName ?? (loadingModel === "ominis-2.0-research" ? "Ominis 2.0 Research 8K" : loadingModel === "ominis-2.0-research-128k" ? "Ominis 2.0 Research 128K" : loadingModel)}
                            </span>
                          )}
                          {researchModeEnabled && (
                            <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 bg-amber-500/20 border border-amber-400/30 rounded" title="Motor académico exclusivo">
                              Investigación
                            </span>
                          )}
                        </div>
                      </div>
                      {(gpuWarmupHint || gpuWaitSeconds !== null) && !(researchProgress && researchSteps.length > 0) && (
                        <div className="mt-3 space-y-1.5">
                          <div className="flex justify-between text-[10px] text-gray-400">
                            <span>Esperando respuesta del modelo</span>
                            <span>{gpuWaitSeconds != null ? `${gpuWaitSeconds}s` : "…"}</span>
                          </div>
                          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-cyan-600/30 via-cyan-400/80 to-cyan-600/30 animate-pulse"
                              style={{ width: gpuWaitSeconds != null ? `${Math.min(92, 8 + gpuWaitSeconds * 0.35)}%` : "35%" }}
                            />
                          </div>
                          {gpuWarmupHint ? (
                            <p className="text-[10px] text-gray-500 leading-snug">
                              Si la GPU está en la nube y fría, la primera respuesta puede tardar varios minutos; las siguientes suelen ser más rápidas.{" "}
                              <span className="text-gray-400">
                                Tu mensaje ya está en proceso en cuanto ves este panel; sabrás que el modelo escribe cuando aparezcan las primeras palabras abajo.
                              </span>
                            </p>
                          ) : (
                            gpuWaitSeconds !== null && (
                              <p className="text-[10px] text-gray-500">
                                El temporizador indica que seguimos a la espera del modelo. Verás la respuesta en cuanto empiece el texto debajo.
                              </p>
                            )
                          )}
                        </div>
                      )}
                      {/* Research progress bar */}
                      {researchProgress && researchSteps.length > 0 && (
                        <div className="mt-3">
                          <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
                            <span>{researchProgress.found} fuentes · {researchProgress.read} leídas</span>
                            <span className="flex items-center gap-1.5">
                              <span className="text-amber-300/90 font-medium">{effectiveResearchModelLabel}</span>
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

                {/* Research progress bar while document is streaming (after first chunk, until done) */}
                {!isLoading && researchSteps.length > 0 && (researchProgress != null) && (
                  <div className="flex justify-start">
                    <div className="bg-white/10 backdrop-blur-md border border-white/10 text-gray-100 rounded-2xl rounded-bl-sm p-3 max-w-[85%]">
                      <div className="flex items-center gap-3">
                        <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
                        <span className="text-gray-300 text-sm">Generando documento…</span>
                        {researchModeEnabled && (
                          <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 bg-amber-500/20 border border-amber-400/30 rounded">Investigación</span>
                        )}
                      </div>
                      <div className="mt-3">
                        <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
                          <span>{researchProgress.found} fuentes · {researchProgress.read} leídas</span>
                          <span className="flex items-center gap-1.5">
                            <span className="text-amber-300/90 font-medium">{effectiveResearchModelLabel}</span>
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

              {/* Source preview modal (lupa) */}
              {sourcePreviewSource && (
                <div
                  className="fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
                  onClick={() => setSourcePreviewSource(null)}
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="source-preview-title"
                >
                  <div
                    className="bg-[#0f1d32] border border-white/20 rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                      <h3 id="source-preview-title" className="text-sm font-semibold text-white">Vista previa de la fuente</h3>
                      <button
                        type="button"
                        onClick={() => setSourcePreviewSource(null)}
                        className="p-1.5 text-gray-400 hover:text-white transition-colors rounded"
                        aria-label="Cerrar"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
                      <div>
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Título</p>
                        <p className="text-white font-medium">{stripOpenscholarPrefix(decodeHtmlEntities(sourcePreviewSource.title)) || "Sin título"}</p>
                      </div>
                      {sourcePreviewSource.authors && (
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Autor</p>
                          <p className="text-gray-300">{sourcePreviewSource.authors}</p>
                        </div>
                      )}
                      {(sourcePreviewSource.year || sourcePreviewSource.journal || sourcePreviewSource.doi) && (
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          {sourcePreviewSource.year && <div><span className="text-[10px] text-gray-500 uppercase">Fecha</span> <span className="text-gray-300">{sourcePreviewSource.year}</span></div>}
                          {sourcePreviewSource.journal && <div><span className="text-[10px] text-gray-500 uppercase">Publicación</span> <span className="text-gray-300">{sourcePreviewSource.journal}</span></div>}
                          {sourcePreviewSource.doi && <div><span className="text-[10px] text-gray-500 uppercase">DOI</span> <span className="text-gray-300">{sourcePreviewSource.doi}</span></div>}
                        </div>
                      )}
                      <div>
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">URL</p>
                        {isCsvLikeUrl(sourcePreviewSource.url) && isCsvPreviewAllowedHost(sourcePreviewSource.url) ? (
                          <div className="space-y-2">
                            <button
                              type="button"
                              onClick={() => void openCsvPreview(sourcePreviewSource.url, sourcePreviewSource.title)}
                              className="text-xs font-medium text-teal-400 hover:text-teal-300 underline"
                            >
                              Ver muestra del CSV (tabla)
                            </button>
                            <a
                              href={buildSourceDeepLink(sourcePreviewSource)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-400 hover:text-blue-300 break-all text-xs block"
                            >
                              {buildSourceDeepLink(sourcePreviewSource)}
                            </a>
                          </div>
                        ) : (
                          <a href={buildSourceDeepLink(sourcePreviewSource)} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 break-all text-xs">
                            {buildSourceDeepLink(sourcePreviewSource)}
                          </a>
                        )}
                      </div>
                      {sourcePreviewSource.sourceType === "clinicaltrials" && (
                        <div className="space-y-1 text-xs">
                          {sourcePreviewSource.ctClassicShowUrl && (
                            <div>
                              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Si ves error 502</p>
                              <a
                                href={sourcePreviewSource.ctClassicShowUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-teal-400 hover:text-teal-300 break-all"
                              >
                                Abrir vista clásica (ct2/show)
                              </a>
                            </div>
                          )}
                          {sourcePreviewSource.ctFallbackSearchUrl && (
                            <div>
                              <a
                                href={sourcePreviewSource.ctFallbackSearchUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-gray-400 hover:text-gray-300 break-all"
                              >
                                Búsqueda por NCT en el sitio NLM
                              </a>
                            </div>
                          )}
                        </div>
                      )}
                      {sourcePreviewSource.snippet && (
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Fragmento</p>
                          <p className="text-gray-400 text-xs leading-relaxed whitespace-pre-wrap">{sourcePreviewSource.snippet}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* CSV preview modal (allowed hosts only; fetches via /api/csv-preview) */}
              {(csvPreview || csvPreviewLoading || csvPreviewError) && (
                <div
                  className="fixed inset-0 z-[10001] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
                  onClick={() => {
                    if (!csvPreviewLoading) {
                      setCsvPreview(null);
                      setCsvPreviewError(null);
                    }
                  }}
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="csv-preview-title"
                >
                  <div
                    className="bg-[#0f1d32] border border-white/20 rounded-xl shadow-2xl max-w-4xl w-full max-h-[85vh] overflow-hidden flex flex-col"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
                      <h3 id="csv-preview-title" className="text-sm font-semibold text-white truncate pr-2">
                        {csvPreview?.title || "Vista previa CSV"}
                      </h3>
                      <button
                        type="button"
                        onClick={() => {
                          setCsvPreview(null);
                          setCsvPreviewError(null);
                        }}
                        className="p-1.5 text-gray-400 hover:text-white transition-colors rounded flex-shrink-0"
                        aria-label="Cerrar"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
                      {csvPreviewLoading && (
                        <p className="text-gray-400 text-sm">Cargando…</p>
                      )}
                      {csvPreviewError && (
                        <p className="text-red-400 text-sm">{csvPreviewError}</p>
                      )}
                      {csvPreview && !csvPreviewLoading && (
                        <>
                          <p className="text-[10px] text-gray-500 break-all">{csvPreview.url}</p>
                          {csvPreview.truncated && (
                            <p className="text-[11px] text-amber-200/90">
                              Muestra truncada (archivo grande). Copiar y descargar usan el fragmento cargado en el servidor.
                            </p>
                          )}
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium"
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(csvPreview.rawText);
                                } catch {
                                  /* ignore */
                                }
                              }}
                              disabled={!csvPreview.rawText}
                            >
                              Copiar texto
                            </button>
                            <a
                              href={`/api/csv-preview?url=${encodeURIComponent(csvPreview.url)}&download=1`}
                              className="inline-flex items-center px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-white text-xs font-medium"
                            >
                              Descargar
                            </a>
                          </div>
                          <div className="overflow-x-auto rounded-lg border border-white/10">
                            <table className="min-w-full text-left text-[11px] text-gray-200 border-collapse">
                              <tbody>
                                {csvPreview.rows.map((row, ri) => (
                                  <tr key={ri} className="border-b border-white/5">
                                    {row.map((cell, ci) => (
                                      <td key={ci} className="px-2 py-1 align-top whitespace-nowrap max-w-[14rem] truncate" title={cell}>
                                        {cell}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Input Area (bottom — only when chat has messages) */}
              {hasMessages && <div
                className={`p-3 flex-shrink-0 border-t border-white/10 relative w-full max-w-full lg:max-w-2xl lg:mx-auto ${isDragOver ? "ring-2 ring-cyan-400/50 bg-cyan-500/5 rounded-xl" : ""}`}
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
                {(researchModeEnabled || uploadedImages.length > 0 || uploadedFiles.length > 0) && (
                  <div className="flex items-center gap-1.5 mb-2 text-xs flex-wrap">
                    {researchModeEnabled && (
                      <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 pl-2 pr-1 py-1 rounded-full">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 7h.01M5 11h.01M5 15h.01M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" />
                        </svg>
                        Modo investigación
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
                        onClick={() => {
                          setShowPlusMenu(!showPlusMenu);
                          setShowModelMenu(false);
                        }}
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
                      {openscholarSearchEnabled && (
                        <span className="inline-flex items-center gap-0.5 text-amber-400 bg-amber-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                          OpenScholar
                          <button onClick={() => setOpenscholarSearchEnabled(false)} className="hover:text-amber-200 transition-colors p-0.5" title="Desactivar">
                            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </span>
                      )}
                      {isAuthenticated && clinicalTrialsSearchEnabled && (
                        <span className="inline-flex items-center gap-0.5 text-teal-300 bg-teal-500/20 text-[10px] pl-1.5 pr-1 py-0.5 rounded-full">
                          CT.gov
                          <button onClick={() => setClinicalTrialsSearchEnabled(false)} className="hover:text-teal-100 transition-colors p-0.5" title="Desactivar">
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
                <a href="/modelo" className="text-gray-400 hover:text-white transition-colors">
                  {researchModeEnabled ? `${effectiveResearchModelLabel} (investigación)` : "ominis-2.0"}
                </a>
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
        <aside className="fixed top-[calc(4rem+var(--banner-height,0px)+env(safe-area-inset-top))] right-0 bottom-0 z-40 w-80 bg-[#0b1426]/95 backdrop-blur-md border-l border-white/10 flex flex-col transition-transform duration-300">
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
              const iconMap: Record<string, string> = { plan: "📋", search: "🔍", search_result: "📄", refine: "🎯", filter: "⚙️", read: "📖", read_done: "✅", read_fail: "❌", read_start: "📚", read_skip: "⏸️", follow: "🔗", complete: "🏁", sources: "📊", relevance: "🎯", relevance_done: "✓", structure: "📑", round2: "🔄", round3: "🧠", gaps: "🕳️", outline: "📝", outline_done: "✅", writing: "✍️" };
              const icon = iconMap[step.action] || "•";
              const reasoningPreviewLen = 90;
              const showReasoningPreview = step.reasoning && step.reasoning.length > reasoningPreviewLen;
              const isExpanded = expandedResearchStepIndex === i;
              const reasoningDisplay = step.reasoning
                ? (isExpanded ? step.reasoning : (showReasoningPreview ? step.reasoning.slice(0, reasoningPreviewLen) + "…" : step.reasoning))
                : null;
              return (
                <div key={i} className="text-[11px] leading-relaxed">
                  <div className="flex items-start gap-1.5">
                    <span className="flex-shrink-0 mt-0.5">{icon}</span>
                    <div className="min-w-0 flex-1 break-words">
                      <p className="text-gray-300 break-words">{step.detail}</p>
                      {reasoningDisplay && (
                        <p
                          role="button"
                          tabIndex={0}
                          onClick={() => setExpandedResearchStepIndex(isExpanded ? null : i)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setExpandedResearchStepIndex(isExpanded ? null : i); } }}
                          className="text-amber-200/80 italic mt-0.5 cursor-pointer hover:bg-white/5 rounded px-1 -mx-1 py-0.5 transition-colors"
                          title={showReasoningPreview && !isExpanded ? "Clic para ver descripción completa" : undefined}
                        >
                          {reasoningDisplay}
                          {showReasoningPreview && !isExpanded && <span className="text-amber-400/90 ml-0.5"> (clic para ver más)</span>}
                          {showReasoningPreview && isExpanded && <span className="text-amber-400/90 ml-0.5"> (clic para cerrar)</span>}
                        </p>
                      )}
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

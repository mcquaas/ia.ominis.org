(function () {
  var suggestedQuestions = [
    "¿Cuáles son las principales causas de muerte en México?",
    "¿Qué fuentes de información sobre Cáncer existen?",
    "¿Cuáles son los diferentes sistemas de salud y a quiénes atienden?",
    "¿Qué guías clínicas recientes existen para hipertensión?",
  ];

  function injectInitialPage() {
    if (document.getElementById("ominis-initial-wrap")) return;
    var textarea = document.querySelector("#root textarea, main textarea, form textarea");
    if (!textarea) return;
    var form = textarea.closest("form") || textarea.closest("[class*='form']") || textarea.closest("div");
    var container = form && form.parentElement ? form.parentElement : textarea.parentElement;
    if (!container) return;

    var wrap = document.createElement("div");
    wrap.id = "ominis-initial-wrap";
    wrap.className = "ominis-initial-wrap";
    var title = document.createElement("h1");
    title.className = "ominis-initial-title";
    title.textContent = "¿En qué puedo ayudarte?";
    wrap.appendChild(title);

    var suggestionsDiv = document.createElement("div");
    suggestionsDiv.className = "ominis-suggestions";
    suggestedQuestions.forEach(function (q) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ominis-suggestion-btn";
      btn.textContent = q;
      btn.addEventListener("click", function () {
        textarea.value = q;
        textarea.focus();
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      });
      suggestionsDiv.appendChild(btn);
    });
    wrap.appendChild(suggestionsDiv);

    container.insertBefore(wrap, form || textarea);

    function updateVisibility() {
      var bubbles = document.querySelectorAll("#root [class*='message-content'], #root [data-sender], #root [class*='group'] [class*='message']");
      var hasMessages = bubbles && bubbles.length > 0;
      wrap.classList.toggle("ominis-initial-hidden", !!hasMessages);
    }
    var obs = new MutationObserver(updateVisibility);
    obs.observe(document.getElementById("root") || document.body, { childList: true, subtree: true });
    updateVisibility();
  }

  /* Single definition: health/research categories for Comunidad filters and agent form dropdown */
  var COMMUNITY_CATEGORIES = [
    "Investigación en salud",
    "Atención clínica",
    "Política en salud",
    "Epidemiología",
    "Salud pública",
    "Guías y evidencia",
    "Educación médica"
  ];
  /* Map LibreChat built-in category labels → same labels used in Comunidad filters */
  var categoryMap = [
    { from: "Genera", to: "Investigación en salud" },
    { from: "General", to: "Investigación en salud" },
    { from: "Recursos Humanos", to: "Atención clínica" },
    { from: "Human Resources", to: "Atención clínica" },
    { from: "Investigación y desarrollo", to: "Política en salud" },
    { from: "Research and development", to: "Política en salud" },
    { from: "Finanzas", to: "Epidemiología" },
    { from: "Finance", to: "Epidemiología" },
    { from: "TI", to: "Salud pública" },
    { from: "IT", to: "Salud pública" },
    { from: "Ventas", to: "Guías y evidencia" },
    { from: "Sales", to: "Guías y evidencia" },
    { from: "Posventa", to: "Educación médica" },
    { from: "After-sales", to: "Educación médica" }
  ];
  var textReplacements = [
    { from: "Agent Marketplace", to: "Comunidad" },
    { from: "Marketplace", to: "Comunidad" },
    { from: "| LibreChat", to: " | Ominis" },
    { from: "Descubre y usa el poder de los agentes de inteligencia artificial para mejorar tu productividad y tus flujos de trabajo.", to: "Descubre y usa agentes de IA desarrollados por la comunidad para la investigación en salud, la práctica clínica y la política pública." },
    { from: "Discover and use the power of AI agents to improve your productivity and workflows.", to: "Descubre y usa agentes de IA desarrollados por la comunidad para la investigación en salud, la práctica clínica y la política pública." },
    { from: "Todos los Agentes", to: "Agentes de la comunidad" },
    { from: "All Agents", to: "Agentes de la comunidad" },
    { from: "Explora todos los agentes compartidos en todas las categorías", to: "Explora agentes compartidos por la comunidad de investigadores y profesionales de la salud." },
    { from: "Explore all agents shared across all categories", to: "Explora agentes compartidos por la comunidad de investigadores y profesionales de la salud." },
    { from: "No se encontró ningún agente", to: "No hay agentes en esta categoría aún." },
    { from: "No agents found", to: "No hay agentes en esta categoría aún." },
    { from: "Search agents...", to: "Buscar agentes..." },
    { from: "Web Search", to: "Búsqueda web" },
    { from: "File Context", to: "Contexto de archivo" },
    { from: "Upload File Context", to: "Subir contexto de archivo" },
    { from: "Support Contact", to: "Contacto de soporte" },
    { from: "Support contact name", to: "Nombre del contacto de soporte" },
    { from: "Email", to: "Correo electrónico" },
    { from: "support@example.com", to: "correo@ejemplo.com" },
    { from: "Rol: USER", to: "Rol: USUARIO" },
    { from: "Max Agent Steps", to: "Pasos máximos del agente" },
    { from: "Agent Handoffs", to: "Reenvíos del agente" },
    { from: "Add handoff agent", to: "Agregar agente de reenvío" },
    { from: "Agent Chain (Mixture-of-Agents)", to: "Cadena de agentes (Mixture-of-Agents)" },
    { from: "No prompts yet", to: "Aún no hay prompts" },
    { from: "Create your first prompt to get started", to: "Crea tu primer prompt para comenzar" },
    { from: "Memories", to: "Memorias" },
    { from: "Filter memories...", to: "Filtrar memorias..." },
    { from: "Use memory", to: "Usar memoria" },
    { from: "No memories yet", to: "Aún no hay memorias" },
    { from: "No memories. Create them manually or prompt the AI to remember something", to: "Sin memorias. Créalas manualmente o pide al asistente que recuerde algo." },
    { from: "Admin Settings - Memories", to: "Ajustes de administrador - Memorias" },
    { from: "Allow using Memories", to: "Permitir usar Memorias" },
    { from: "Allow creating Memories", to: "Permitir crear Memorias" },
    { from: "Allow updating Memories", to: "Permitir actualizar Memorias" },
    { from: "Allow reading Memories", to: "Permitir leer Memorias" },
    { from: "Allow users to opt out of Memories", to: "Permitir que los usuarios rechacen Memorias" },
    { from: "MCP Settings", to: "Configuración MCP" },
    { from: "Filter MCP servers by name", to: "Filtrar servidores MCP por nombre" },
    { from: "No MCP servers yet", to: "Aún no hay servidores MCP" },
    { from: "Create your first MCP server to get started", to: "Crea tu primer servidor MCP para comenzar" },
    { from: "New Chat", to: "Nuevo chat" },
    { from: "Copy link", to: "Copiar enlace" },
    { from: "Rename", to: "Renombrar" },
    { from: "Regenerate title", to: "Regenerar título" },
    { from: "Delete", to: "Eliminar" },
    { from: "My Agents", to: "Mis agentes" },
    { from: "Search Ominis models...", to: "Buscar modelos Ominis..." },
    { from: "Buscar modelos...", to: "Buscar modelos Ominis..." },
    { from: "Create New Agent", to: "Crear nuevo agente" },
    { from: "Create new agent", to: "Crear nuevo agente" },
    { from: "Create Agent", to: "Crear agente" },
    { from: "Create agent", to: "Crear agente" },
    { from: "Category", to: "Categoría" },
    { from: "Category *", to: "Categoría *" },
    { from: "Tools and Actions", to: "Herramientas y acciones" },
    { from: "File context", to: "Contexto de archivo" },
    { from: "Search categories...", to: "Buscar categorías..." },
    { from: "Edit Agent", to: "Editar agente" },
    { from: "Delete Agent", to: "Eliminar agente" },
    { from: "Agent name", to: "Nombre del agente" },
    { from: "Agent description", to: "Descripción del agente" },
    { from: "Optional: The agent's name", to: "Opcional: El nombre del agente" },
    { from: "Optional: Describe your Agent here", to: "Opcional: Describa su agente aquí" },
    { from: "System instructions that the agent uses", to: "Las instrucciones del sistema que utiliza el agente" },
    { from: "Instructions", to: "Instrucciones" },
    { from: "Indicaciones", to: "Prompts" },
    { from: "Variables", to: "Variables" },
    { from: "Save", to: "Guardar" },
    { from: "Cancel", to: "Cancelar" },
    { from: "Create", to: "Crear" },
    { from: "Update", to: "Actualizar" },
    { from: "Delete", to: "Eliminar" },
    { from: "Submit", to: "Enviar" },
    { from: "Back", to: "Volver" },
    { from: "Close", to: "Cerrar" },
    { from: "Loading...", to: "Cargando..." },
    { from: "Save and Submit", to: "Guardar y enviar" },
    { from: "Reasoning Summary", to: "Resumen de razonamiento" },
    { from: "Use Responses API", to: "Usar API de respuestas" },
    { from: "Verbosity", to: "Verbosidad" },
    { from: "Disable Streaming", to: "Desactivar streaming" },
    { from: "File Token Limit", to: "Límite de tokens de archivo" },
    { from: "Unset", to: "Sin definir" },
    { from: "Admin Settings", to: "Ajustes de administrador" },
    { from: "Admin Settings - Indicaciones", to: "Ajustes de administrador - Prompts" },
    { from: "Admin Settings - Prompts", to: "Ajustes de administrador - Prompts" },
    { from: "Allow sharing Prompts", to: "Permitir compartir Prompts" },
    { from: "Allow sharing Prompts publicly", to: "Permitir compartir Prompts públicamente" },
    { from: "Allow use of Prompts", to: "Permitir uso de Prompts" },
    { from: "Allow creating Prompts", to: "Permitir crear Prompts" },
    { from: "Reset Model Parameters", to: "Restablecer parámetros del modelo" },
    { from: "You've reached the end of the results", to: "Has llegado al final de los resultados" },
    { from: "You have reached the end of the results", to: "Has llegado al final de los resultados" },
    { from: "You've reached the end of the list", to: "Has llegado al final de la lista" },
    { from: "Enable web search functionality using OpenAI's built-in search capabilities. This allows the model to search the web for up-to-date information and provide more accurate, current responses.", to: "Activa la búsqueda web con las capacidades de búsqueda de OpenAI. Permite al modelo buscar información actualizada y dar respuestas más precisas y recientes." },
    { from: "Enable web search functionality", to: "Activar búsqueda web" },
    { from: "Disable streaming for this request", to: "Desactivar streaming para esta solicitud" },
    { from: "Use the Responses API for structured output", to: "Usar la API de respuestas para salida estructurada" },
    { from: "Maximum number of tokens to use for file content", to: "Número máximo de tokens para el contenido de archivos" }
  ];

  var placeholderReplacements = [
    { from: "Search agents...", to: "Buscar agentes..." },
    { from: "Search Ominis models...", to: "Buscar modelos Ominis..." },
    { from: "Support contact name", to: "Nombre del contacto de soporte" },
    { from: "support@example.com", to: "correo@ejemplo.com" },
    { from: "Filter memories...", to: "Filtrar memorias..." },
    { from: "Filter MCP servers by name", to: "Filtrar servidores MCP por nombre" },
    { from: "Optional: The agent's name", to: "Opcional: El nombre del agente" },
    { from: "Optional: Describe your Agent here", to: "Opcional: Describa su agente aquí" },
    { from: "System instructions that the agent uses", to: "Las instrucciones del sistema que utiliza el agente" },
    { from: "Search categories...", to: "Buscar categorías..." }
  ];

  function replaceTextInNode(node) {
    if (node.nodeType !== Node.TEXT_NODE || !node.textContent) return;
    var text = node.textContent;
    var changed = false;
    textReplacements.forEach(function (r) {
      if (text.indexOf(r.from) !== -1) {
        text = text.replace(new RegExp(r.from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), r.to);
        changed = true;
      }
    });
    if (changed) node.textContent = text;
  }

  function replaceCategoryLabels() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    var node;
    while ((node = walker.nextNode())) {
      var text = node.textContent.trim();
      if (!text) continue;
      categoryMap.forEach(function (m) {
        if (text === m.from) {
          node.textContent = node.textContent.replace(m.from, m.to);
        }
      });
    }
  }

  function replacePlaceholders() {
    var inputs = document.querySelectorAll("#root input[placeholder], #root textarea[placeholder], main input[placeholder], main textarea[placeholder]");
    inputs.forEach(function (el) {
      var ph = el.getAttribute("placeholder");
      if (!ph) return;
      placeholderReplacements.forEach(function (r) {
        if (ph.indexOf(r.from) !== -1) {
          el.setAttribute("placeholder", ph.replace(r.from, r.to));
        }
      });
    });
  }

  function replaceTitles() {
    var elms = document.querySelectorAll("#root [title], main [title]");
    elms.forEach(function (el) {
      var t = el.getAttribute("title");
      if (!t) return;
      var changed = false;
      textReplacements.forEach(function (r) {
        if (t.indexOf(r.from) !== -1) {
          t = t.replace(new RegExp(r.from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), r.to);
          changed = true;
        }
      });
      if (changed) el.setAttribute("title", t);
    });
  }

  function replaceSidebarUntitledChats() {
    var aside = document.querySelector("#root aside, #root [data-testid='sidebar'], #root [class*='sidebar']");
    if (!aside) return;
    var links = aside.querySelectorAll("a[href*='/c/'], a[href*='/chat/']");
    links.forEach(function (a) {
      var text = (a.textContent || "").trim();
      if (text === "Nuevo chat") {
        a.textContent = "(Título pendiente)";
      }
    });
  }

  function applyMarketplaceToComunidad() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      replaceTextInNode(node);
    }
    replaceCategoryLabels();
    replacePlaceholders();
    replaceTitles();
    replaceSidebarUntitledChats();
  }

  function hideLibreChatFooter() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      if (node.textContent && node.textContent.indexOf("LibreChat") !== -1) {
        var el = node.parentElement;
        while (el && el !== document.body) {
          if (el.id && el.id.indexOf("ominis") === 0) break;
          el.style.display = "none";
          el = el.parentElement;
        }
        break;
      }
    }
  }

  function injectOminisFooter() {
    var bar = document.createElement("div");
    bar.id = "ominis-footer-bar";
    bar.className = "ominis-footer-bar";
    bar.innerHTML =
      '<span class="ominis-footer-text">Siempre verifica con las fuentes originales · Una iniciativa de <a href="https://www.funsalud.org.mx" target="_blank" rel="noopener noreferrer">FUNSALUD</a> · IA hecha en México · modelo LLM: <a href="https://ia.ominis.org/modelo" target="_blank" rel="noopener noreferrer">ominis-2.0</a> · <button type="button" id="ominis-footer-mas-info">Más información</button></span>';

    var overlay = document.createElement("div");
    overlay.id = "ominis-footer-overlay";
    overlay.className = "ominis-footer-overlay";
    overlay.innerHTML =
      '<div class="ominis-footer-overlay-inner">' +
      '<button type="button" id="ominis-footer-close">Ocultar &darr;</button>' +
      '<footer class="ominis-footer-content">' +
      '<div class="ominis-footer-grid">' +
      '<div><h3>FUNSALUD</h3><p>OMINIS es una iniciativa sin fines de lucro de la <a href="https://funsalud.org.mx" target="_blank" rel="noopener">Fundación Mexicana para la Salud A.C.</a> para facilitar la investigación en salud apoyada por IA.</p><span class="ominis-badge">100% Datos en México</span></div>' +
      '<div><h3>Tecnología</h3><p>Potenciado por <a href="https://ia.ominis.org/modelo" target="_blank" rel="noopener">ominis-2.0</a>, modelo de IA mexicano especializado en salud. Datos en México (S3 mx-central-1).</p></div>' +
      '<div><h3>Recursos</h3><ul><li><a href="https://ominis.org" target="_blank" rel="noopener">Observatorio OMINIS</a></li><li><a href="https://roclab.ominis.org" target="_blank" rel="noopener">ROCLab</a></li><li><a href="https://ia.ominis.org/modelo" target="_blank" rel="noopener">Modelo ominis-2.0</a></li></ul></div>' +
      '<div><h3>Contacto</h3><p><a href="mailto:ominis@funsalud.org.mx">ominis@funsalud.org.mx</a></p></div>' +
      "</div>" +
      '<div class="ominis-footer-bottom">&copy; ' + new Date().getFullYear() + " Fundación Mexicana para la Salud A.C.</div>" +
      "</footer></div>";

    document.body.appendChild(bar);
    document.body.appendChild(overlay);

    document.getElementById("ominis-footer-mas-info").onclick = function () {
      overlay.classList.add("ominis-footer-overlay-visible");
    };
    document.getElementById("ominis-footer-close").onclick = function () {
      overlay.classList.remove("ominis-footer-overlay-visible");
    };
    overlay.onclick = function (e) {
      if (e.target === overlay) overlay.classList.remove("ominis-footer-overlay-visible");
    };
  }

  function fixRightPanelToggle() {
    var root = document.getElementById("root");
    if (!root) return;
    var candidates = root.querySelectorAll(
      "button[class*='collapse'], button[class*='expand'], a[class*='collapse'], a[class*='expand'], " +
      "[class*='panel-toggle'], [class*='right-panel'] button, [class*='slide'] button, " +
      "[data-testid*='slide'] button, [data-testid*='panel'] button"
    );
    var viewportRight = window.innerWidth;
    candidates.forEach(function (el) {
      var rect = el.getBoundingClientRect();
      if (rect.right >= viewportRight - 80 && rect.width <= 60 && rect.height >= 20) {
        el.classList.add("ominis-right-toggle");
        el.style.zIndex = "50";
        el.style.pointerEvents = "auto";
        el.style.position = "relative";
      }
    });
    var byClass = root.querySelectorAll(".ominis-right-toggle");
    byClass.forEach(function (el) {
      el.style.zIndex = "50";
      el.style.pointerEvents = "auto";
    });
  }

  function injectHeaderLogo() {
    if (document.getElementById("ominis-header-logo")) return;
    var headerRightSection = document.querySelector(
      '#root [data-testid="chat-header-right"], ' + /* Specific for main chat header right section */
      '#root main [class*="header"] > div:last-child, ' + /* Generic for any header last child div */
      '#root [class*="conversation"][class*="header"] > div:last-child, ' + /* For conversation header */
      '#root [class*="main-chat-layout"] [class*="header-actions"]'
    );

    if (!headerRightSection) return;

    var shareBtn = headerRightSection.querySelector(
      'button[aria-label*="hare"], button[aria-label*="Share"], button[aria-label*="ompartir"], ' +
      'a[aria-label*="hare"], a[aria-label*="Share"], [data-testid*="share"]'
    );
    
    if (!shareBtn) return;

    var link = document.createElement("a");
    link.id = "ominis-header-logo";
    link.className = "ominis-header-logo";
    link.href = "https://ia.ominis.org";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", "OMINIS - Ir a ia.ominis.org");
    var img = document.createElement("img");
    img.src = "https://ia.ominis.org/logo.png";
    img.alt = "OMINIS";
    img.setAttribute("height", "28");
    link.appendChild(img);
    
    shareBtn.parentElement.insertBefore(link, shareBtn);
  }

  function setupMessageInput() {
    var textarea = document.querySelector("#root textarea, main form textarea");
    if (!textarea || textarea.dataset.ominisPlaceholder === "1") return;
    textarea.placeholder = "Pídele a Ominis...";
    textarea.dataset.ominisPlaceholder = "1";
    textarea.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        var form = textarea.closest("form");
        if (form) {
          var submit = form.querySelector('button[type="submit"]');
          if (submit) submit.click();
          else form.requestSubmit();
        }
      }
    });
  }

  /** Try to get display name from LibreChat greeting (e.g. "Buenas noches, Gustavo") */
  function getDisplayNameFromPage() {
    var root = document.getElementById("root") || document.body;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var node;
    var re = /(?:Buenas?\s+noches|Buenos?\s+d[ií]as|Good\s+(?:morning|evening|afternoon)),\s*([^\s].+?)(?:\s*$|\s*[\u201C\u201D"]|\.)/i;
    while ((node = walker.nextNode())) {
      var text = (node.textContent || "").trim();
      var m = text.match(re);
      if (m && m[1]) return m[1].trim();
    }
    return null;
  }

  function injectOminisTopBar() {
    if (document.getElementById("ominis-top-bar")) return;
    var bar = document.createElement("div");
    bar.id = "ominis-top-bar";
    bar.className = "ominis-top-bar";
    bar.innerHTML =
      '<a href="https://ia.ominis.org" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-brand">' +
      '<img src="https://ia.ominis.org/logo.png" alt="OMINIS" class="ominis-top-bar-logo"/>' +
      '</a>' +
      '<span class="ominis-top-bar-subtitle">Observatorio Mexicano para la Investigación y la Inteligencia en Salud</span>' +
      '<div class="ominis-top-bar-nav">' +
      '<a href="https://ia.ominis.org/live" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-link">Live Avatar</a>' +
      '<a href="https://chat.ominis.org" class="ominis-top-bar-link">Agentes (Pro)</a>' +
      '<a href="https://ia.ominis.org/sinba" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-link">Cubos SINBA</a>' +
      '</div>' +
      '<div class="ominis-top-bar-right">' +
      '<button type="button" id="ominis-top-bar-profile-btn" class="ominis-top-bar-profile-btn" aria-haspopup="true" aria-expanded="false">' +
      '<span class="ominis-top-bar-avatar" id="ominis-top-bar-avatar">?</span>' +
      '<span class="ominis-top-bar-name" id="ominis-top-bar-name">Perfil</span>' +
      '<svg class="ominis-top-bar-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>' +
      '</button>' +
      '<div id="ominis-top-bar-dropdown" class="ominis-top-bar-dropdown" role="menu" hidden>' +
      '<div class="ominis-top-bar-dropdown-header">' +
      '<span class="ominis-top-bar-dropdown-name" id="ominis-top-bar-dropdown-name">Usuario</span>' +
      '</div>' +
      '<a href="https://ia.ominis.org/profile" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-dropdown-item" role="menuitem">Mi Perfil</a>' +
      '<a href="https://ia.ominis.org/api-keys" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-dropdown-item" role="menuitem">API Keys</a>' +
      '<a href="https://ia.ominis.org/profile/api-docs" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-dropdown-item" role="menuitem">Documentación API</a>' +
      '<a href="https://ia.ominis.org/c" target="_blank" rel="noopener noreferrer" class="ominis-top-bar-dropdown-item" role="menuitem">Ir al Chat</a>' +
      '<button type="button" class="ominis-top-bar-dropdown-item ominis-top-bar-logout" role="menuitem">Cerrar sesión</button>' +
      '</div>' +
      '</div>';
    document.body.insertBefore(bar, document.body.firstChild);

    var profileBtn = document.getElementById("ominis-top-bar-profile-btn");
    var dropdown = document.getElementById("ominis-top-bar-dropdown");
    var nameEl = document.getElementById("ominis-top-bar-name");
    var dropdownNameEl = document.getElementById("ominis-top-bar-dropdown-name");
    var avatarEl = document.getElementById("ominis-top-bar-avatar");

    function updateDisplayName() {
      var name = getDisplayNameFromPage();
      if (name) {
        nameEl.textContent = name;
        dropdownNameEl.textContent = name;
        avatarEl.textContent = name.charAt(0).toUpperCase();
      }
    }
    updateDisplayName();
    setTimeout(updateDisplayName, 800);
    setTimeout(updateDisplayName, 2000);

    function closeDropdown() {
      dropdown.setAttribute("hidden", "");
      profileBtn.setAttribute("aria-expanded", "false");
    }
    function openDropdown() {
      dropdown.removeAttribute("hidden");
      profileBtn.setAttribute("aria-expanded", "true");
    }
    function toggleDropdown() {
      if (dropdown.hasAttribute("hidden")) openDropdown(); else closeDropdown();
    }

    profileBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleDropdown();
    });
    document.getElementById("ominis-top-bar-dropdown").querySelector(".ominis-top-bar-logout").addEventListener("click", function () {
      closeDropdown();
      window.location.href = "/api/auth/logout";
    });
    document.addEventListener("click", function (e) {
      if (dropdown && !dropdown.hasAttribute("hidden") && !bar.contains(e.target)) closeDropdown();
    });
  }

  function run() {
    injectOminisTopBar();
    hideLibreChatFooter();
    injectOminisFooter();
    injectHeaderLogo();
    injectInitialPage();
    applyMarketplaceToComunidad();
    setupMessageInput();
    fixRightPanelToggle();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
  var tries = 0;
  var t = setInterval(function () {
    injectOminisTopBar();
    injectHeaderLogo();
    injectInitialPage();
    applyMarketplaceToComunidad();
    replaceSidebarUntitledChats();
    setupMessageInput();
    fixRightPanelToggle();
    if (++tries >= 20) clearInterval(t);
  }, 500);
  /* Re-apply Comunidad labels when SPA navigates to /agents */
  var lastPath = location.pathname;
  setInterval(function () {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      setTimeout(applyMarketplaceToComunidad, 300);
    }
  }, 500);
})();

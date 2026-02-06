# Agent Prompt & Tools Evaluation

## Current State Analysis

### 1. Prompt Issues Identified

#### 1.1 Basic System Prompt (Current)
**Location**: `lambda/query/handler.py`, `scripts/rag/query_engine.py`, `infrastructure/09-deploy-ollama-ec2.sh`

**Current Prompt**:
```
Eres un asistente médico especializado de Ominis Health, respaldado por FUNSALUD. 
Tu objetivo es proporcionar información de salud precisa y útil basada en las fuentes proporcionadas.

INSTRUCCIONES:
1. Responde SOLO basándote en la información proporcionada en las fuentes.
2. Si las fuentes no contienen información suficiente, indícalo claramente.
3. Siempre cita las fuentes que uses (por número).
4. Usa un lenguaje claro y accesible.
5. No proporciones diagnósticos médicos. Recomienda consultar a un profesional cuando sea apropiado.
6. Responde en español.
```

**Problems**:
- ❌ No mentions available tools (PubMed, Web search)
- ❌ No instructions on when/how to use tools
- ❌ Too restrictive ("SOLO basándote en las fuentes") - prevents tool usage
- ❌ No guidance on proactive tool suggestions
- ❌ Missing persona reinforcement (OMINIS research assistant)
- ❌ No instructions for multi-part responses or follow-ups

#### 1.2 Prompt Duplication
- Same prompt exists in 3+ locations
- Inconsistent updates across files
- Model-level system prompt in Ollama Modelfile differs from runtime prompts

### 2. Tool Implementation Issues

#### 2.1 Frontend vs Backend Mismatch
**Frontend** (`MainLayout.tsx`):
- ✅ Has UI toggles for Web and PubMed search
- ✅ Sends `web_search` parameter to API
- ❌ No `pubmed_search` parameter sent (only UI toggle exists)
- ❌ No actual tool invocation mechanism

**Backend** (`query-stream/route.ts`, `query-gpu/route.ts`):
- ✅ Receives `web_search` parameter
- ❌ No PubMed search parameter handling
- ❌ No visible tool implementation in codebase
- ❌ GPU API endpoint exists but implementation not in repo

#### 2.2 Missing Tool Calling Mechanism
- ❌ No structured tool calling format (JSON schema, function calling)
- ❌ No tool definitions visible in prompts
- ❌ Agent cannot invoke tools autonomously
- ❌ No tool result handling/formatting

#### 2.3 From Conversation Analysis (Image)
The conversation shows:
- ✅ Agent correctly identifies when to suggest PubMed search
- ✅ Agent offers to perform search ("¿Deseas que realice esa búsqueda?")
- ❌ But doesn't actually execute the search
- ❌ User must manually confirm, breaking flow
- ❌ No automatic tool invocation based on query intent

### 3. Critical Conversation History Issue ⚠️

#### 3.1 Problem: "Sí" Treated as New Query
**Issue**: When user responds "Sí" (Yes) to agent's offer, agent treats it as a new conversation starter instead of confirmation.

**Root Cause**:
- ❌ Frontend sends `history` parameter but backend **doesn't use it**
- ❌ `generate_answer()` function doesn't accept `history` parameter
- ❌ Prompt has no instructions about understanding conversational context
- ❌ No guidance on handling confirmations/affirmations ("Sí", "Sí por favor", etc.)

**Current Flow**:
```
User: "¿Qué tan prometedora es la termografía para tratar insuficiencia cardíaca?"
Agent: "¿Deseas que realice esa búsqueda para ti?"
User: "Sí"
Agent: [Treats "Sí" as new question, responds with greeting] ❌
```

**Expected Flow**:
```
User: "Sí"
Agent: [Understands confirmation, executes PubMed search, returns results] ✅
```

#### 3.2 Technical Details
- `frontend/src/components/MainLayout.tsx` line 303-306: Builds history correctly
- `frontend/src/app/api/query-stream/route.ts` line 26: Forwards history to GPU API
- `lambda/query/handler.py` line 158: `generate_answer()` **ignores history**
- Prompt construction doesn't include conversation context

### 4. Specific Problems from Example Conversation

**Example**: User asks about thermography for heart failure

**What worked**:
1. Agent provided multi-part answer (treatment vs diagnosis)
2. Agent correctly identified need for literature search
3. Agent offered to search PubMed

**What didn't work**:
1. Agent didn't automatically search when appropriate
2. Agent required explicit user confirmation
3. **Agent didn't understand "Sí" as confirmation** ⚠️
4. Agent didn't integrate search results into response
5. No follow-up with search results

### 4. Architecture Gaps

#### 4.1 Tool Integration Points Missing
```
Current Flow:
User Query → RAG Search → LLM → Response

Needed Flow:
User Query → Intent Detection → [RAG Search | Tool Call | Both] → LLM → Response
```

#### 4.2 No Tool Definitions
- No JSON schema for PubMed API
- No JSON schema for Web search API
- No function calling format defined
- No tool selection logic

### 5. Recommendations Priority

#### High Priority (Critical)
1. **Fix conversation history handling** ⚠️ **URGENT**
   - Update `generate_answer()` to accept and use `history` parameter
   - Add conversation context to prompt construction
   - Add instructions for understanding confirmations/affirmations
   - Handle short responses ("Sí", "No", "Claro") as context-dependent

2. **Add tool awareness to system prompt**
   - List available tools
   - Explain when to use each tool
   - Provide tool calling format

3. **Implement tool calling mechanism**
   - Define tool schemas
   - Add tool invocation logic
   - Handle tool results

4. **Fix prompt duplication**
   - Centralize prompt definitions
   - Use consistent prompts across all entry points

#### Medium Priority (Important)
4. **Add proactive tool usage**
   - Auto-detect when tools are needed
   - Suggest tools before user asks
   - Execute tools automatically when appropriate

5. **Improve multi-turn conversation**
   - Better context handling
   - Tool results integration
   - Follow-up question handling

#### Low Priority (Enhancement)
6. **Add tool result formatting**
   - Structured display of PubMed results
   - Web search result integration
   - Source attribution for tool results

## Next Steps

1. Review this evaluation
2. Prioritize improvements
3. Implement tool calling mechanism
4. Update system prompts
5. Test with real queries

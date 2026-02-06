# Fix: Conversation History & "Sí" Confirmation Issue

## Problem Summary

When a user responds "Sí" (Yes) to the agent's offer to search PubMed, the agent treats it as a new conversation starter instead of understanding it as a confirmation.

**Example of the bug:**
```
User: "¿Qué tan prometedora es la termografía para tratar insuficiencia cardíaca?"
Agent: "¿Deseas que realice esa búsqueda para ti?"
User: "Sí"
Agent: [Responds with greeting, treating "Sí" as new question] ❌
```

## Root Cause

1. **Backend doesn't use history**: Frontend sends `history` parameter, but `generate_answer()` function ignores it
2. **No confirmation detection**: Prompt has no instructions for understanding confirmations
3. **No context awareness**: Prompt construction doesn't include conversation history

## Solution

### Step 1: Update Backend Handler

**File**: `lambda/query/handler.py` (or GPU server equivalent)

**Changes needed**:
1. Update `generate_answer()` function signature to accept `history` parameter
2. Add confirmation detection logic
3. Update prompt construction to include conversation history
4. Use improved system prompt

**Reference**: See `lambda/query/handler_improved.py` for complete implementation

### Step 2: Update GPU Server (if separate)

If the GPU server (`http://44.215.64.245:8080`) is a separate service, apply the same changes there.

**Key changes**:
```python
# OLD
def generate_answer(question: str, context: str) -> str:
    # No history support

# NEW
def generate_answer(
    question: str, 
    context: str,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    # Includes history in prompt construction
```

### Step 3: Update Prompt Construction

**Key improvements**:
1. Add conversation history section to prompt
2. Detect confirmations ("Sí", "Claro", etc.)
3. Provide context-aware instructions when confirmation detected

**Example prompt structure**:
```
System Prompt: [Improved version with conversation awareness]

History Section:
Usuario: "¿Qué tan prometedora es la termografía..."
Asistente: "¿Deseas que realice esa búsqueda para ti?"

Current Question: "Sí"

[If confirmation detected]:
El usuario ha confirmado tu propuesta anterior.
ACCIÓN REQUERIDA: Procede inmediatamente con la búsqueda propuesta.
```

### Step 4: Test the Fix

**Test cases**:

1. **Confirmation Test**:
   ```
   User: "¿Qué es la diabetes?"
   Agent: "¿Deseas que busque más información en PubMed?"
   User: "Sí"
   Expected: Agent executes PubMed search, returns results
   ```

2. **Follow-up Test**:
   ```
   User: "¿Qué es la diabetes?"
   Agent: [Provides answer]
   User: "¿Y el diagnóstico?"
   Expected: Agent understands this is about diabetes diagnosis
   ```

3. **Negative Test**:
   ```
   User: "¿Deseas que busque más información?"
   Agent: "No"
   Expected: Agent respects rejection, offers alternatives
   ```

## Implementation Checklist

- [ ] Update `generate_answer()` function signature
- [ ] Add `detect_confirmation()` helper function
- [ ] Update `build_prompt_with_history()` function
- [ ] Replace system prompt with improved version
- [ ] Update handler to pass history to `generate_answer()`
- [ ] Test with confirmation scenarios
- [ ] Test with follow-up questions
- [ ] Test with negative responses
- [ ] Deploy to staging
- [ ] Monitor for false positives

## Files to Update

1. **Backend Lambda** (if used):
   - `lambda/query/handler.py`
   - `lambda/query/handler_authenticated.py`

2. **GPU Server** (if separate):
   - GPU server query handler (not in this repo)
   - Apply same pattern as `handler_improved.py`

3. **Reference Implementation**:
   - `lambda/query/handler_improved.py` (already created)

## Migration Notes

1. **Backward Compatibility**: The `history` parameter should be optional to maintain compatibility
2. **Performance**: Including history adds tokens, but improves context understanding significantly
3. **Testing**: Test thoroughly to avoid false positives (treating new questions as confirmations)

## Expected Outcome

After fix:
```
User: "¿Qué tan prometedora es la termografía para tratar insuficiencia cardíaca?"
Agent: "¿Deseas que realice esa búsqueda para ti?"
User: "Sí"
Agent: [Executes PubMed search, returns results] ✅
```

## Related Documents

- `docs/AGENT_EVALUATION.md` - Full evaluation of issues
- `docs/IMPROVED_PROMPTS.md` - Improved prompt templates
- `lambda/query/handler_improved.py` - Reference implementation

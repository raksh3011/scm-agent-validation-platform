# LLM API Usage in SCM Validator

## ✅ Good News: LLM API is OPTIONAL and FREE by Default

### Current Configuration

**No LLM API keys are configured or required!**

The validator works 100% without any paid LLM APIs.

---

## How LLM is Used (When Enabled)

### Optional LLM Insights Feature

The validator has an **optional, additive-only** LLM insights feature that:
- ✅ **Never affects the trust score** (score is fully deterministic)
- ✅ **Never blocks validation** (if disabled/fails, validation continues)
- ✅ **Only adds commentary** (plain-language insights about findings)

### Current Backend Configuration

No LLM environment variables are set in Railway:
```bash
# These are NOT configured (validator works fine without them):
OPENAI_API_KEY=<not set>
LLM_INSIGHTS_ENDPOINT=<not set>
LLM_INSIGHTS_MODEL=<not set>
```

---

## LLM Configuration Options

### Option 1: No LLM (Current Setup) ✅
**Cost**: $0
**Works**: ✅ Yes, fully functional

The validator runs completely without LLM:
- All scoring is deterministic rule-based
- All findings are code-analysis based
- No API calls to OpenAI/Anthropic/etc.

### Option 2: Local LLM (Free)
**Cost**: $0
**Setup**: Run Ollama locally

```bash
# Install Ollama
# https://ollama.com

# Pull a model
ollama pull qwen3:8b

# Run Ollama server
ollama serve
```

Set environment variables in Railway:
```bash
LLM_INSIGHTS_ENDPOINT=http://localhost:11434/api/generate
LLM_INSIGHTS_MODEL=qwen3:8b
```

### Option 3: OpenAI API (Paid)
**Cost**: ~$0.002 per validation run (very cheap)

Set environment variable in Railway:
```bash
OPENAI_API_KEY=sk-...
```

Modify `llm_insights.py` to use OpenAI instead of local endpoint.

### Option 4: Anthropic Claude (Paid)
**Cost**: ~$0.003 per validation run

Set environment variable in Railway:
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Modify `llm_insights.py` to use Anthropic SDK.

---

## Current Validator Behavior

### Without LLM Configuration (Current State)
```json
{
  "summary": { ... },
  "score_breakdown": [ ... ],
  "findings": [ ... ],
  "recommendations": [ ... ],
  "ai_insights": []  // ← Empty, but validation completes successfully
}
```

### With LLM Enabled
```json
{
  "summary": { ... },
  "score_breakdown": [ ... ],
  "findings": [ ... ],
  "recommendations": [ ... ],
  "ai_insights": [
    "Consider implementing circuit breakers for external LLM calls",
    "Missing cost tracking could lead to unexpected API bills",
    "Error handling should distinguish between rate limits and failures"
  ]
}
```

---

## Code Analysis Without LLM

The validator's **core functionality** is entirely LLM-free:

### What Works Without LLM (100% deterministic):
✅ **Static Code Analysis**: Parses Python files, detects patterns
✅ **Rule Engine**: 20+ validation rules checking for:
  - Error handling
  - Security issues  
  - Cost controls
  - Supply chain risks
  - Best practices
✅ **Scoring Engine**: Computes trust scores based on findings
✅ **Evidence Collection**: Extracts code snippets showing issues
✅ **Recommendations**: Generates actionable fix suggestions
✅ **Positive Signals**: Detects good patterns in code

### What's Optional (LLM-enhanced):
🔵 **AI Insights**: Natural language commentary about business risk
- Only runs if `enable_llm_insights` is set in request
- Only runs if `OPENAI_API_KEY` or `LLM_INSIGHTS_ENDPOINT` is configured
- Never blocks or fails validation if unavailable

---

## Cost Analysis

### Current Setup (No LLM)
```
Railway Backend: $0-5/month (free tier or hobby plan)
Vercel Frontend: $0/month (unlimited)
LLM API Costs: $0/month ✅

Total: $0-5/month
```

### With OpenAI API (Optional)
```
Railway Backend: $0-5/month
Vercel Frontend: $0/month
OpenAI API: ~$0.002 per validation
  - 100 validations/month = $0.20
  - 1,000 validations/month = $2.00

Total: $2-7/month (for 1,000 validations)
```

### With Local Ollama (Free)
```
Railway Backend: $0-5/month
Vercel Frontend: $0/month
Ollama (self-hosted): $0 (runs on your machine or server)

Total: $0-5/month ✅
```

---

## How to Enable LLM Insights (Optional)

If you want to add LLM commentary in the future:

### Using Ollama (Free, Recommended)

1. **Install Ollama locally or on a server**:
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Windows
   # Download from https://ollama.com
   ```

2. **Run Ollama and pull a model**:
   ```bash
   ollama pull qwen3:8b  # or llama3.2, mistral, etc.
   ollama serve
   ```

3. **Set Railway environment variables**:
   ```bash
   railway variables set LLM_INSIGHTS_ENDPOINT=http://your-ollama-server:11434/api/generate
   railway variables set LLM_INSIGHTS_MODEL=qwen3:8b
   ```

4. **Enable in API calls** (frontend):
   Add `enable_llm_insights: true` to validation request

### Using OpenAI (Paid)

1. **Get API key** from https://platform.openai.com

2. **Set Railway environment variable**:
   ```bash
   railway variables set OPENAI_API_KEY=sk-...
   ```

3. **Update `llm_insights.py`** to call OpenAI instead of Ollama

4. **Enable in API calls**: Add `enable_llm_insights: true`

---

## Summary

### ✅ Your Current Deployment

**LLM Status**: Not configured (by design)
**Cost**: $0 for LLM
**Functionality**: 100% operational without LLM
**Validation Quality**: Full deterministic analysis with 20+ rules

### 🎯 Key Takeaways

1. ✅ **No API keys needed** - validator works completely without LLM
2. ✅ **No credit costs** - all core features are LLM-free
3. ✅ **Optional enhancement** - LLM only adds commentary, never blocks
4. ✅ **Free alternatives** - use Ollama locally if you want LLM
5. ✅ **Low cost if paid** - OpenAI would be ~$0.002 per validation

### 💡 Recommendation

**Keep it as-is (no LLM)** unless you specifically want the AI insights commentary. The validator is fully functional and produces comprehensive validation reports without any LLM integration.

---

## Check Current Status

```bash
# See all environment variables in Railway
railway variables

# Current status: No LLM keys configured ✅
```

Your platform is **100% operational** and costs **$0 for LLM usage**! 🎉

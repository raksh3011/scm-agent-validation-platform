import os
import ast
import json
import hashlib
import sys
import argparse
from pathlib import Path
from openai import OpenAI
import requests



MAX_CONTEXT_CHARS = 50000
IGNORE_DIRS = {'.venv', 'venv', 'tests', 'docs', '.git', '__pycache__', 'output', 'config', 'generated'}
CACHE_DIR = '.cache'
CACHE_FILE = os.path.join(CACHE_DIR, 'auditor_cache.json')

class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.classes = []
        self.functions = []
        self.imports = []
        self.docstring = ""

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.functions.append(node.name)
        self.generic_visit(node)
        
    def visit_AsyncFunctionDef(self, node):
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)

def analyze_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        analyzer = CodeAnalyzer()
        analyzer.visit(tree)
        
        docstring = ast.get_docstring(tree)
        
        return {
            'size': len(content),
            'classes': analyzer.classes,
            'functions': analyzer.functions,
            'imports': list(set(analyzer.imports)),
            'has_docstring': bool(docstring)
        }
    except Exception as e:
        return {'error': str(e)}

def get_file_hash(filepath):
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            hasher.update(f.read())
        return hasher.hexdigest()
    except Exception:
        return None

def build_repo_summary(root_path):
    summary = {
        'files': 0,
        'classes': 0,
        'functions': 0,
        'key_modules': [],
        'file_details': {},
        'hashes': {}
    }
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        
        for file in filenames:
            if file.endswith('.py'):
                filepath = os.path.join(dirpath, file)
                rel_path = os.path.relpath(filepath, root_path)
                
                # Normalize slashes for consistency
                rel_path = rel_path.replace('\\', '/')
                
                file_hash = get_file_hash(filepath)
                analysis = analyze_file(filepath)
                
                if 'error' not in analysis:
                    summary['files'] += 1
                    summary['classes'] += len(analysis['classes'])
                    summary['functions'] += len(analysis['functions'])
                    summary['file_details'][rel_path] = analysis
                    summary['hashes'][rel_path] = file_hash
                    summary['key_modules'].append(rel_path)

    return summary

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache_data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2)

def call_llm(prompt):

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen3:8b",
            "prompt": prompt,
            "stream": False
        }
    )

    result = response.json()

    return json.loads(
        result["response"]
    )

def phase1_get_important_files(summary):
    # Compact summary for LLM
    compact_summary = {
        "files": summary["files"],
        "classes": summary["classes"],
        "functions": summary["functions"],
        "key_modules": summary["key_modules"]
    }
    
    prompt = f"""
    Analyze this repository summary:
    {json.dumps(compact_summary, indent=2)}
    
    Which files are most important for auditing this agent?
    Return a JSON object strictly in this format:
    {{"important_files": ["file1.py", "file2.py"]}}
    """
    
    result = call_llm(prompt)
    return result.get('important_files', [])

def phase2_audit_files(important_files, summary, root_path, cache):
    # Prepare context
    context = ""
    current_chars = 0
    
    # We will send all important files for a complete SCM audit
    files_to_send = important_files
    
    for file_path in files_to_send:
        full_path = os.path.join(root_path, file_path)
        if not os.path.exists(full_path):
            continue
            
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        file_header = f"\n\n--- FILE: {file_path} ---\n\n"
        if current_chars + len(content) + len(file_header) > MAX_CONTEXT_CHARS:
            # Truncate
            remaining = MAX_CONTEXT_CHARS - current_chars - len(file_header)
            if remaining > 0:
                context += file_header + content[:remaining] + "\n...[TRUNCATED DUE TO CONTEXT LIMIT]"
            break
        else:
            context += file_header + content
            current_chars += len(content) + len(file_header)
            
    prompt = f"""
    You are an SCM AI Agent Auditor.

    Your purpose is NOT to perform a software code review.

    Do NOT focus on coding style, import placement, formatting, naming conventions, linting issues, documentation quality, or generic software engineering observations unless they directly impact business trustworthiness.

    Your objective is to evaluate whether the SCM agent can be trusted to make supply-chain decisions.

    STEP 1: Identify the SCM agent type.
    Possible agent types include: Demand Forecasting Agent, Inventory Reorder Agent, Supplier Selection Agent, Procurement Agent, Logistics Agent, Production Planning Agent, Risk Monitoring Agent, Warehouse Optimization Agent, Generic SCM Agent.

    STEP 2: Extract the agent architecture.
    Identify: Perception Layer, Judgment Layer, Decision Layer, Action Layer.

    STEP 3: Evaluate SCM-specific trustworthiness.
    Focus on: Business logic correctness, Decision quality, Supply-chain assumptions, Constraint handling, Risk management, Explainability, Robustness, Governance.

    Examples of meaningful findings: Missing supplier capacity constraints, No lead-time uncertainty modeling, No forecast confidence estimation, Lack of budget constraints, Missing MOQ handling, No service-level objectives, Single-point supplier dependency, No disruption handling, Poor explainability of decisions.
    Examples of findings that should receive very low priority: Import placement, Variable naming, Code formatting, Function length, Style guide violations.

    STEP 4: Generate scores for:
    1. Perception Trust (0-100)
    2. Reasoning Trust (0-100)
    3. Decision Trust (0-100)
    4. Explainability (0-100)
    5. Robustness (0-100)
    6. Governance & Controls (0-100)

    STEP 5: Produce: Executive Summary, Agent Classification, Architecture Analysis, Strengths, SCM-Specific Risks, Trust Scores, Final Trust Verdict.

    Always prioritize SCM reasoning over software engineering critique. A defect should only be reported if it materially impacts the trustworthiness, reliability, safety, explainability, or business value of the SCM agent.
    
    FINDING QUALITY RULE:
    Maximum 20% generic software engineering findings.
    Minimum 80% SCM-specific findings.
    
    Source Code:
    {context}
    
    Return a JSON object strictly in this format:
    {{
      "executive_summary": "...",
      "agent_classification": {{
        "agent_type": "...",
        "confidence": 0.0
      }},
      "architecture": {{
        "perception": ["..."],
        "judgment": ["..."],
        "decision": ["..."],
        "action": ["..."]
      }},
      "strengths": ["...", "..."],
      "scm_risks": ["...", "..."],
      "trust_scores": {{
        "perception_trust": 0,
        "reasoning_trust": 0,
        "decision_trust": 0,
        "explainability": 0,
        "robustness": 0,
        "governance_controls": 0
      }},
      "final_verdict": {{
        "rating": "LOW|MEDIUM|HIGH",
        "summary": "..."
      }}
    }}
    """
    
    new_audit = call_llm(prompt)
    if not new_audit:
        raise RuntimeError(
         "Audit generation failed. "
         "No valid response received from Gemini."
        )
    
    return new_audit, True # Always return True to overwrite cache with new comprehensive format

def compute_trust_score(audit_report):
    scores = audit_report.get('trust_scores', {})
    
    perception = scores.get('perception_trust', 0)
    reasoning = scores.get('reasoning_trust', 0)
    decision = scores.get('decision_trust', 0)
    explainability = scores.get('explainability', 0)
    robustness = scores.get('robustness', 0)
    governance = scores.get('governance_controls', 0)
    
    overall = (
        perception * 0.15 +
        reasoning * 0.25 +
        decision * 0.25 +
        explainability * 0.10 +
        robustness * 0.15 +
        governance * 0.10
    )
    
    return round(overall)

def generate_html_report(report, trust_score):
    executive_summary = report.get('executive_summary', 'N/A')
    classification = report.get('agent_classification', {})
    agent_type = classification.get('agent_type', 'Unknown')
    confidence = classification.get('confidence', 0.0)
    
    verdict = report.get('final_verdict', {})
    rating = verdict.get('rating', 'UNKNOWN')
    verdict_summary = verdict.get('summary', 'N/A')
    
    scores = report.get('trust_scores', {})
    arch = report.get('architecture', {})
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SCM Agent Audit Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }}
            h1, h2, h3 {{ color: #2c3e50; border-bottom: 2px solid #e9ecef; padding-bottom: 5px; }}
            .dashboard-header {{ display: flex; justify-content: space-between; align-items: center; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            .score-card {{ text-align: center; }}
            .score-card .score {{ font-size: 54px; font-weight: bold; color: #007bff; }}
            .verdict-card {{ text-align: right; }}
            .verdict-card .rating {{ font-size: 32px; font-weight: bold; padding: 5px 15px; border-radius: 4px; display: inline-block; }}
            .rating-HIGH {{ background-color: #d4edda; color: #155724; }}
            .rating-MEDIUM {{ background-color: #fff3cd; color: #856404; }}
            .rating-LOW {{ background-color: #f8d7da; color: #721c24; }}
            
            .section-box {{ background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
            
            .grid-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }}
            .sub-score {{ background-color: #e9ecef; padding: 15px; border-radius: 8px; text-align: center; }}
            .sub-score-val {{ font-size: 24px; font-weight: bold; color: #495057; }}
            
            .architecture-layer {{ background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #17a2b8; }}
            .architecture-layer h3 {{ margin-top: 0; color: #17a2b8; border-bottom: none; }}
            
            .risks {{ background-color: #fff3f3; border-left: 4px solid #dc3545; padding: 15px; border-radius: 8px; }}
            .strengths {{ background-color: #f3fff5; border-left: 4px solid #28a745; padding: 15px; border-radius: 8px; }}
            ul {{ padding-left: 20px; margin-top: 10px; }}
            li {{ margin-bottom: 8px; }}
        </style>
    </head>
    <body>
        <h1>SCM Agent Validation Dashboard</h1>
        
        <div class="dashboard-header">
            <div class="score-card">
                <h2>Overall Trust Score</h2>
                <div class="score">{trust_score}/100</div>
                <p>Weighted average of SCM trust pillars</p>
            </div>
            <div class="verdict-card">
                <h2>Final Verdict</h2>
                <div class="rating rating-{rating}">{rating}</div>
            </div>
        </div>
        
        <div class="section-box">
            <h2>Executive Summary</h2>
            <p><strong>Classification:</strong> {agent_type} (Confidence: {confidence})</p>
            <p>{executive_summary}</p>
            <p><strong>Verdict Summary:</strong> {verdict_summary}</p>
        </div>
        
        <h2>Trust Score Breakdown</h2>
        <div class="grid-container">
            <div class="sub-score"><div>Perception Trust</div><div class="sub-score-val">{scores.get('perception_trust', 0)}</div></div>
            <div class="sub-score"><div>Reasoning Trust</div><div class="sub-score-val">{scores.get('reasoning_trust', 0)}</div></div>
            <div class="sub-score"><div>Decision Trust</div><div class="sub-score-val">{scores.get('decision_trust', 0)}</div></div>
            <div class="sub-score"><div>Explainability</div><div class="sub-score-val">{scores.get('explainability', 0)}</div></div>
            <div class="sub-score"><div>Robustness</div><div class="sub-score-val">{scores.get('robustness', 0)}</div></div>
            <div class="sub-score"><div>Governance & Controls</div><div class="sub-score-val">{scores.get('governance_controls', 0)}</div></div>
        </div>
        
        <div class="grid-container">
            <div class="risks">
                <h2>SCM-Specific Risks ({len(report.get('scm_risks', []))})</h2>
                <ul>
                    {"".join(f"<li>{r}</li>" for r in report.get('scm_risks', []))}
                </ul>
            </div>
            <div class="strengths">
                <h2>Strengths ({len(report.get('strengths', []))})</h2>
                <ul>
                    {"".join(f"<li>{s}</li>" for s in report.get('strengths', []))}
                </ul>
            </div>
        </div>
        
        <div class="section-box">
            <h2>Architecture Analysis</h2>
            <div class="architecture-layer">
                <h3>Perception Layer</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in arch.get('perception', []))}</ul>
            </div>
            <div class="architecture-layer">
                <h3>Judgment Layer</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in arch.get('judgment', []))}</ul>
            </div>
            <div class="architecture-layer">
                <h3>Decision Layer</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in arch.get('decision', []))}</ul>
            </div>
            <div class="architecture-layer">
                <h3>Action Layer</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in arch.get('action', []))}</ul>
            </div>
        </div>
    </body>
    </html>
    """
    with open('audit_report.html', 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    parser = argparse.ArgumentParser(description="Agent Auditor")
    parser.add_argument("--target", "-t", help="Specific agent file to audit (e.g. smart_reorder_agent.py)", default=None)
    args = parser.parse_args()

    root_path = "."
    print("Phase 1: Local Analysis...")
    summary = build_repo_summary(root_path)
    
    print(f"Analyzed {summary['files']} files. Found {summary['classes']} classes and {summary['functions']} functions.")
    
    cache = load_cache()
    
    if args.target:
        print(f"\nPhase 2: Target specified. Bypassing LLM identification.")
        important_files = [args.target]
    else:
        print("\nPhase 2: Identifying Important Files...")
        important_files = phase1_get_important_files(summary)
        print(f"LLM identified {len(important_files)} important files: {important_files}")
    
    print("\nPhase 3 & 4: Auditing Selected Files...")
    audit_report, has_changed = phase2_audit_files(important_files, summary, root_path, cache)
    
    # Deterministic Scoring
    trust_score = compute_trust_score(audit_report)
    audit_report['trust_score'] = trust_score
    
    # Generate Outputs
    with open('audit_report.json', 'w', encoding='utf-8') as f:
        json.dump(audit_report, f, indent=2)
        
    generate_html_report(audit_report, trust_score)
    
    # Update Cache if changed
    if has_changed:
        cache['hashes'] = summary['hashes']
        cache['important_files'] = important_files
        cache['audit_report'] = audit_report
        save_cache(cache)
        
    print("\nAudit complete! Reports generated: audit_report.json, audit_report.html")
    print(f"Trust Score: {trust_score}")

if __name__ == "__main__":
    main()

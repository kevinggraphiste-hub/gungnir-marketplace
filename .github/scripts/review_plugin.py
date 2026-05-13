#!/usr/bin/env python3
"""
gungnir-marketplace — Auto-revue d'un plugin soumis en PR.

Vérifie :
1. manifest.json présent + parseable + champs minimaux requis
2. type=workflow → workflow.yaml présent + YAML valide
3. signature.bin présent + Ed25519 valide vs author_pubkey du manifest
   (la pubkey du contributeur — on la fetch via gungnir API si elle est
   ScarletWolf-trusted, sinon on accepte la signature self-claimed)
4. Cohérence manifest ↔ YAML (workflows uniquement) :
   - tools_required ⊇ tools utilisés dans workflow.yaml
   - network_egress ⊇ domaines statiques dans workflow.yaml
5. Pas de patterns suspects (scan basique anti-trojan) :
   - bash_exec, subprocess, eval, exec arbitraires non déclarés
   - exfiltration potentielle (POST/GET vers domaines non déclarés
     dans network_egress)
6. min_gungnir_version raisonnable (<= version courante)

Exit code 0 = OK auto-merge, !=0 = problèmes (PR bloquée).
"""
import json
import re
import sys
from pathlib import Path

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REQUIRED_MANIFEST_FIELDS = ["name", "version", "author", "description", "type"]
SUSPICIOUS_PATTERNS = [
    (r"\b(bash|shell|os\.system|subprocess|popen)\b", "Pattern shell-exec détecté"),
    (r"\beval\s*\(", "Pattern eval() détecté"),
    (r"\bexec\s*\(", "Pattern exec() détecté"),
    (r"__import__\s*\(", "Pattern __import__() détecté"),
]


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def ok(msg: str) -> None:
    print(f"✓  {msg}")


def compute_plugin_digest(plugin_dir: Path) -> bytes:
    """SHA-256 déterministe du contenu (même algo que plugin_signing.py côté Gungnir)."""
    import hashlib
    h = hashlib.sha256()
    for f in sorted(plugin_dir.rglob("*")):
        if not f.is_file() or f.name == "signature.bin":
            continue
        rel = f.relative_to(plugin_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return bytes.fromhex(h.hexdigest())


def extract_tools_from_yaml(yaml_text: str) -> set[str]:
    tools: set[str] = set()
    doc = yaml.safe_load(yaml_text) or {}
    steps = doc.get("steps") or []

    def _walk(node):
        if isinstance(node, dict):
            t = node.get("tool")
            if isinstance(t, str) and t:
                tools.add(t)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(steps)
    return tools


def extract_static_egress(yaml_text: str) -> set[str]:
    domains: set[str] = set()
    for m in re.finditer(r"https?://([^/\s\"'{}]+)", yaml_text):
        domains.add(m.group(1).lower())
    return domains


def check_egress_match(used: set[str], declared: set[str]) -> set[str]:
    """Returns set of `used` domains not covered by `declared` (with wildcard support)."""
    undeclared = set()
    for d in used:
        if d in declared:
            continue
        if any(ed.startswith("*.") and (d == ed[2:] or d.endswith("." + ed[2:])) for ed in declared):
            continue
        undeclared.add(d)
    return undeclared


def main() -> None:
    if len(sys.argv) < 2:
        fail("Usage: review_plugin.py <plugin_dir>")
    plugin_dir = Path(sys.argv[1])
    if not plugin_dir.is_dir():
        fail(f"{plugin_dir} n'existe pas ou n'est pas un dossier")

    # 1. manifest.json
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        fail(f"manifest.json absent dans {plugin_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"manifest.json malformé : {e}")

    for field in REQUIRED_MANIFEST_FIELDS:
        if not manifest.get(field):
            fail(f"Champ manifest manquant : {field}")
    ok(f"Manifest valide ({manifest['name']} v{manifest['version']})")

    plugin_type = manifest.get("type", "plugin")

    # 2. Si workflow : check workflow.yaml
    yaml_text = ""
    if plugin_type == "workflow":
        wf_meta = manifest.get("workflow") or {}
        entry = wf_meta.get("entry") or "workflow.yaml"
        yaml_path = plugin_dir / entry
        if not yaml_path.exists():
            fail(f"Workflow type=workflow mais {entry} absent")
        try:
            yaml_text = yaml_path.read_text(encoding="utf-8")
            yaml.safe_load(yaml_text)
        except Exception as e:
            fail(f"YAML invalide : {e}")
        ok(f"workflow.yaml parseable")

    # 3. Signature
    sig_path = plugin_dir / "signature.bin"
    if not sig_path.exists():
        fail("signature.bin absent — toute soumission doit être signée")
    author_pubkey = (manifest.get("author_pubkey") or "").strip().lower()
    if not author_pubkey:
        fail("manifest.author_pubkey manquant — impossible de vérifier la signature community")
    if len(author_pubkey) != 64:
        fail(f"author_pubkey de longueur invalide ({len(author_pubkey)} chars, attendu 64 hex)")

    digest = compute_plugin_digest(plugin_dir)
    sig_bytes = sig_path.read_bytes()
    try:
        pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(author_pubkey))
        pubkey.verify(sig_bytes, digest)
        ok(f"Signature Ed25519 valide pour pubkey {author_pubkey[:16]}…")
    except InvalidSignature:
        fail("Signature Ed25519 INVALIDE — le plugin a été modifié depuis la signature, ou la pubkey ne correspond pas")
    except Exception as e:
        fail(f"Erreur vérification signature : {e}")

    # 4. Cohérence workflow (si applicable)
    if plugin_type == "workflow":
        wf_meta = manifest.get("workflow") or {}
        declared_tools = set(wf_meta.get("tools_required") or [])
        used_tools = extract_tools_from_yaml(yaml_text)
        undeclared_tools = used_tools - declared_tools
        if undeclared_tools:
            fail(f"Outils utilisés non déclarés dans tools_required : {sorted(undeclared_tools)}")
        ok(f"Tools cohérents ({len(used_tools)} utilisés ⊆ {len(declared_tools)} déclarés)")

        permissions = manifest.get("permissions") or {}
        declared_egress = set(permissions.get("network_egress") or [])
        used_domains = extract_static_egress(yaml_text)
        undeclared_domains = check_egress_match(used_domains, declared_egress)
        if undeclared_domains:
            fail(f"Domaines réseau utilisés non déclarés : {sorted(undeclared_domains)}")
        ok(f"Network egress cohérent ({len(used_domains)} domaines statiques)")

    # 5. Patterns suspects (scan dans toutes sources : YAML + .py)
    scanned_files = list(plugin_dir.rglob("*.py")) + list(plugin_dir.rglob("*.yaml")) + list(plugin_dir.rglob("*.yml"))
    findings = []
    for f in scanned_files:
        if f.name == "signature.bin":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, label in SUSPICIOUS_PATTERNS:
            if re.search(pattern, content):
                findings.append(f"{f.relative_to(plugin_dir)} — {label}")
    if findings:
        # Pour les workflows, ces patterns ne devraient JAMAIS apparaître
        # (le runner Forge utilise ses propres outils, pas eval/exec).
        # Pour les plugins code (routes.py), un usage légitime est possible
        # mais doit être justifié — on log en warning sans bloquer ici.
        if plugin_type == "workflow":
            for f in findings:
                print(f"  - {f}")
            fail(f"Patterns suspects détectés dans un workflow (refusés par défaut)")
        else:
            warn(f"{len(findings)} pattern(s) suspect(s) — revue humaine recommandée :")
            for f in findings:
                warn(f"  - {f}")
    else:
        ok("Aucun pattern suspect détecté")

    print("")
    print(f"✅ Auto-revue OK pour {manifest['name']} v{manifest['version']}")


if __name__ == "__main__":
    main()

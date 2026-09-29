"""Documentary evidence for REM-19, REM-20, REM-21 and missing PRIV/EDPB coverage."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "labs" / "LAB-LF-003" / "REGISTRO_PROVEEDORES_Y_OPERACION_R5.md"
text = path.read_text(encoding="utf-8")
checks = {}


def check(name, condition):
    checks[name] = bool(condition)
    print(("PASS" if condition else "FAIL") + " " + name)


check("R5-provider-register", all(term in text for term in ("| HubSpot |", "| Hunter |", "| Slack |", "Owner lógico", "DPA, retención y DSR")))
check("R5-hubspot-account-gaps", all(term.lower() in text.lower() for term in ("Contacts read/write", "Estados Unidos (Este)", "enrichment adicional")))
check("R5-hunter-free-reconciliation", all(term in text for term in ("`GET /v2/combined/find`", "Cuenta observada Free", "Reconciliar capacidad real")))
check("R5-slack-not-configured-v01-v08", "**NOT_CONFIGURED**" in text and all(f"**V0{i}" in text for i in range(1, 9)))
check("R5-incident-procedure", all(term in text for term in ("Detección", "Clasificación", "Contención", "Escalamiento", "Evidencia", "Cierre", "Revisión")))
check("R5-dsr-existing-capabilities", all(term in text for term in ("LOCATE/EXPORT/ANNOTATE", "DELETE/RESTRICT", "aprobador independiente", "tombstones/restricciones")))
check("R5-risk-register-raci", "Risk register residual" in text and "RACI lógico" in text and "Cliente Controller" in text)
check("R5-transfer-dpia", "Transferencias y criterio DPIA" in text and "alto riesgo" in text and "NOT_VERIFIED" in text)
check("R5-tabletops-synthetic", "**Incidente:**" in text and "**DSR:**" in text and "No se llamó a proveedores reales" in text)
check("R5-rem21-environment-evidence", "**REM-21=NOT_VERIFIED / ENVIRONMENT.**" in text and "No se cierra con documentación general" in text)
check("R6-priv-map-complete", all(f"PRIV-T{i:02d}" in text for i in range(1, 11)))
check("R6-edpb-map-complete", all(f"EDPB-T{i:02d}" in text for i in range(1, 10)))

failed = [name for name, value in checks.items() if not value]
print(f"RESULT: {'FAIL' if failed else 'PASS'}; passed={sum(checks.values())}/{len(checks)}")
sys.exit(1 if failed else 0)

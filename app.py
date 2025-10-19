
import streamlit as st
import supabase

import uuid
from datetime import datetime

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY")

try:
    from supabase import create_client, Client
except Exception:
    Client = None
    create_client = None

supabase: "Client | None" = None
if create_client and SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as _e:
        supabase = None
        st.session_state["_usage_err_init"] = str(_e)

# Sesión pseudo-única por navegador
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


def _safe_insert_usage(sex: str, fossi_value: float, risk_label: str):
    """Inserta un registro de uso en Supabase; falla en silencio con aviso."""
    if not supabase:
        return
    try:
        payload = {
            "id": str(uuid.uuid4()),
            "ts": datetime.utcnow().isoformat(),
            "session_id": st.session_state.session_id,
            "sex": sex,
            "fossi": float(fossi_value),
            "risk_label": risk_label
        }
        supabase.table("usage").insert(payload).execute()
    except Exception as e:
        st.session_state["_usage_err_insert"] = str(e)

def _safe_get_global_count() -> int | None:
    """Devuelve el conteo global de cálculos registrados en Supabase."""
    if not supabase:
        return None
    try:
        # Truco del count: select con count='exact'
        resp = supabase.table("usage").select("id", count="exact").execute()
        # En supabase-py, el conteo viene en resp.count
        return int(resp.count) if hasattr(resp, "count") and resp.count is not None else None
    except Exception as e:
        st.session_state["_usage_err_count"] = str(e)
        return None


st.set_page_config(page_title="FOSSI Online Calculator", page_icon="🧮", layout="centered")

st.title("FOSSI Online Calculator")
st.caption("Fast Ossifier Stratification Index in Diffuse Idiopathic Skeletal Hyperostosis (DISH)")

st.markdown(
    """
**What is FOSSI?**  
FOSSI (Fast Ossifier Stratification Index) provides sex-specific risk stratification for accelerated ossification in DISH:
- **FOSSI-F (females)** - predominantly insulin resistance-driven
- **FOSSI-M (males)** - inflammation / endocrine-driven

This calculator implements the validated equations and thresholds described in the FOSSI manuscript.
"""
)

st.divider()

with st.expander("Input settings"):
    sex = st.selectbox("Sex", options=["Female", "Male"])
    col1, col2 = st.columns(2)
    age = col1.number_input("Age (years)", min_value=18, max_value=100, value=62, step=1)
    bmi = col2.number_input("BMI (kg/m²)", min_value=10.0, max_value=60.0, value=31.0, step=0.1, format="%.1f")

    col3, col4 = st.columns(2)
    height_cm = col3.number_input("Height (cm)", min_value=120.0, max_value=220.0, value=160.0, step=0.1, format="%.1f")
    wc_cm = col4.number_input("Waist circumference (cm)", min_value=50.0, max_value=180.0, value=98.0, step=0.1, format="%.1f")

    st.markdown("**Lipids unit**")
    unit = st.radio("Choose units for TG and HDL", options=["mmol/L", "mg/dL"], index=0, horizontal=True)

    col5, col6 = st.columns(2)
    tg = col5.number_input(f"Triglycerides (TG) ({unit})", min_value=0.1, max_value=20.0 if unit=="mmol/L" else 2000.0, value=1.9 if unit=="mmol/L" else 168.0, step=0.1, format="%.2f")
    hdl = col6.number_input(f"HDL cholesterol ({unit})", min_value=0.1, max_value=10.0 if unit=="mmol/L" else 400.0, value=1.0 if unit=="mmol/L" else 39.0, step=0.01, format="%.2f")

    ht = st.selectbox("Hypertension", options=["No (0)", "Yes (1)"], index=1)
    hypertension = 1 if "Yes" in ht else 0

# Unit conversion if needed
# mg/dL -> mmol/L conversions: TG: /88.57 ; HDL: /38.67
if unit == "mg/dL":
    tg_mmol = tg / 88.57
    hdl_mmol = hdl / 38.67
else:
    tg_mmol = tg
    hdl_mmol = hdl

# Derived indices
# CMI = [TG (mmol/L)/HDL (mmol/L)] × [WC (cm)/Height (cm)]
cmi = (tg_mmol / hdl_mmol) * (wc_cm / height_cm)

# VAI (females) = [WC / (36.58 + 1.89 × BMI)] × [TG/0.81] × [1.52/HDL]
vai = None
if sex == "Female":
    vai = (wc_cm / (36.58 + 1.89*bmi)) * (tg_mmol/0.81) * (1.52/hdl_mmol)

# FOSSI equations
# FOSSI-F = -18.811 + (0.209×Age) + (0.350×BMI) + (1.359×CMI) + (0.799×Hypertension) + (0.203×VAI)
# FOSSI-M = -4.663 + (0.039×Age) + (0.045×BMI) - (0.223×CMI) + (0.015×WC)
if sex == "Female":
    fossi = -18.811 + (0.209*age) + (0.350*bmi) + (1.359*cmi) + (0.799*hypertension) + (0.203*(vai if vai is not None else 0.0))
else:
    fossi = -4.663 + (0.039*age) + (0.045*bmi) - (0.223*cmi) + (0.015*wc_cm)

# Risk categorization & messaging
def format_number(x, dec=2):
    try:
        return f"{x:.{dec}f}"
    except Exception:
        return "—"

if sex == "Female":
    # thresholds: <5.84 low; 5.84–7.88 intermediate; 7.89–9.58 high; >9.58 very high
    if fossi < 5.84:
        risk_label, color, expl = "Low", "green", "Metabolically quiescent; FO prevalence ~12%."
    elif fossi <= 7.88:
        risk_label, color, expl = "Intermediate", "yellow", "Early metabolic priming; bone status variable."
    elif fossi <= 9.58:
        risk_label, color, expl = "High", "orange", "High-risk metabolic footprint; trabecular damage likely."
    else:
        risk_label, color, expl = "Very High", "red", "Near-certain FO; severe metabolic burden; trabecular deterioration."
else:
    # thresholds: <0.71 grey zone; >=0.71 high/very high
    if fossi < 0.71:
        risk_label, color, expl = "Grey zone (<0.71)", "yellow", "Baseline FO prevalence ~17%; monitor closely."
    else:
        risk_label, color, expl = "High/Very High (≥0.71)", "red", "Full FO phenotype; pronounced metabolic overload and trabecular decline."

# =========================
#   CONTADOR (local + Supabase)
# =========================
if "fossi_counter" not in st.session_state:
    st.session_state.fossi_counter = 0
    st.session_state.last_fossi = None
    st.session_state.last_risk = None

# Incrementar sólo si ha cambiado el valor (evita contar simples repaints)
if st.session_state.last_fossi != fossi:
    st.session_state.fossi_counter += 1
    st.session_state.last_fossi = fossi
    st.session_state.last_risk = risk_label
    # Registrar en Supabase (persistente)
    _safe_insert_usage(sex=sex, fossi_value=fossi, risk_label=risk_label)

# Consultar contador global (una vez por render — es rápido; si lo prefieres, envuélvelo en st.cache_data con ttl)
global_count = _safe_get_global_count()


st.divider()
st.subheader("Results")

# Color box
color_map = {"green":"#E8F5E9", "yellow":"#FFFDE7", "orange":"#FFF3E0", "red":"#FFEBEE"}
st.markdown(
    f"""
    <div style="padding:1rem;border-radius:12px;background:{color_map.get(color,'#F5F5F5')};border:1px solid #e0e0e0;">
    <b>FOSSI value:</b> {format_number(fossi,2)}<br/>
    <b>Risk category:</b> {risk_label}<br/>
    <i>{expl}</i>
    </div>
    """,
    unsafe_allow_html=True
)

st.divider()
colG1, colG2 = st.columns(2)
colG1.metric("Your session calculations", st.session_state.get("fossi_counter", 0))
colG2.metric("Global calculations (all users)", "—" if global_count is None else f"{global_count:,}")

# Mensajes de diagnóstico (opcionales)
if "_usage_err_init" in st.session_state:
    st.info(f"Telemetry disabled (init): {st.session_state['_usage_err_init']}")
if "_usage_err_insert" in st.session_state:
    st.info(f"Usage not logged: {st.session_state['_usage_err_insert']}")
if "_usage_err_count" in st.session_state:
    st.info(f"Global count unavailable: {st.session_state['_usage_err_count']}")


with st.expander("Details and derived indices"):
    colA, colB = st.columns(2)
    colA.metric("CMI", format_number(cmi, 3))
    if sex == "Female":
        colB.metric("VAI (females)", format_number(vai, 3))
    else:
        colB.metric("Waist (cm)", format_number(wc_cm, 1))
    colC, colD = st.columns(2)
    colC.metric("TG (mmol/L)", format_number(tg_mmol, 3))
    colD.metric("HDL (mmol/L)", format_number(hdl_mmol, 3))

st.divider()

st.markdown(
    """
**Equation summary**  
- **FOSSI-F (females):** -18.811 + (0.209×Age) + (0.350×BMI) + (1.359×CMI) + (0.799×Hypertension) + (0.203×VAI)  
- **FOSSI-M (males):** -4.663 + (0.039×Age) + (0.045×BMI) - (0.223×CMI) + (0.015×WC)

**Thresholds**  
- **Women:** <5.84 (Low), 5.84–7.88 (Intermediate), 7.89–9.58 (High), >9.58 (Very High)  
- **Men:** <0.71 (Grey zone), ≥0.71 (High/Very High)

> **Unit note:** If you enter lipids in mg/dL, the app converts internally to mmol/L (TG ÷ 88.57; HDL ÷ 38.67).
"""
)

st.caption(
    "References: Pariente et al. 'Fast Ossifier' in DISH, RMD Open (2025) 11:e006024; "
    "FOSSI manuscript (Sept 2025). This tool provides research-oriented risk stratification and "
    "does not replace clinical judgement. No data are transmitted off your browser in the Streamlit Cloud deployment."
)

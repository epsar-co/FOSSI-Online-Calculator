# app.py — FOSSI Online Calculator (Supabase: visitas + cálculos + mini dashboard)

import os
import uuid
from typing import Optional
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd

# =========================
#   CONFIGURACIÓN PÁGINA
# =========================
st.set_page_config(
    page_title="FOSSI Online Calculator",
    page_icon="🧮",
    layout="centered"
)

# =========================
#   SUPABASE (TELEMETRÍA)
# =========================
try:
    from supabase import create_client, Client
except Exception:
    create_client, Client = None, None

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY")

supabase: Optional["Client"] = None
if create_client and SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        supabase = None
        st.session_state["_usage_err_init"] = str(e)

# Sesión pseudo-única por navegador
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

def _safe_user_agent() -> str:
    # st.request puede no existir en algunas versiones/entornos
    try:
        return st.request.headers.get("User-Agent", "unknown")
    except Exception:
        return os.environ.get("HTTP_USER_AGENT", "unknown") or "unknown"

def log_event(event: str, fossi_type: Optional[str] = None) -> None:
    """Inserta un evento (visit / calculate). Nunca rompe la app si falla."""
    if not supabase:
        return
    try:
        ua = _safe_user_agent()
        supabase.table("usage_stats").insert({
            "session_id": st.session_state.session_id,
            "event": event,
            "user_agent": ua[:500],
            "fossi_type": fossi_type
        }).execute()
    except Exception as e:
        st.session_state["_usage_err"] = str(e)

# Registrar visita una sola vez por sesión
if "visited" not in st.session_state:
    log_event("visit")
    st.session_state.visited = True

# =========================
#   UI PRINCIPAL
# =========================
st.title("FOSSI Online Calculator")
st.caption("Fast Ossifier Stratification Index in Diffuse Idiopathic Skeletal Hyperostosis (DISH) v1.0")

# (Opcional) Pastilla de cálculos totales
if supabase:
    try:
        resp = supabase.table("usage_stats").select("id", count="exact").eq("event", "calculate").execute()
        total_calcs = getattr(resp, "count", None)
        if total_calcs is not None:
            st.markdown(
                f"<div style='display:inline-block;padding:.35rem .7rem;border-radius:999px;"
                f"background:#EEF2FF;border:1px solid #E0E7FF;color:#3730A3;font-weight:600;margin-bottom:2rem'>"
                f"👥 Number of calculations: {total_calcs}</div>",
                unsafe_allow_html=True
            )
    except Exception:
        pass

st.markdown(
    """
**What is FOSSI?**  
FOSSI (Fast Ossifier Stratification Index) provides sex-specific risk stratification for accelerated ossification and early trabecular impairment in DISH:
- **FOSSI-F (females)** — predominantly insulin resistance–driven  
- **FOSSI-M (males)** — inflammation / endocrine–driven

This calculator implements the validated equations and thresholds described in the FOSSI manuscript:  
*Pariente et al., Fast Ossifier Stratification Index (FOSSI): A propensity score–derived tool in DISH (Oct 2025, submitted).*
"""
)
st.divider()

with st.expander("Input settings", expanded=True):
    sex = st.selectbox("Sex", options=["Female", "Male"])
    is_female = (sex == "Female")

    col1, col2 = st.columns(2)
    age = col1.number_input("Age (years)", min_value=18, max_value=100, value=62, step=1)
    bmi = col2.number_input("BMI (kg/m²)", min_value=10.0, max_value=60.0, value=31.0, step=0.1, format="%.1f")

    col3, col4 = st.columns(2)
    height_cm = col3.number_input("Height (cm)", min_value=120.0, max_value=220.0, value=160.0, step=0.1, format="%.1f")
    wc_cm = col4.number_input("Waist circumference (cm)", min_value=50.0, max_value=180.0, value=98.0, step=0.1, format="%.1f")

    st.markdown("**Lipids unit**")
    unit = st.radio("Choose units for TG and HDL", options=["mmol/L", "mg/dL"], index=0, horizontal=True)

    col5, col6 = st.columns(2)
    tg = col5.number_input(
        f"Triglycerides (TG) ({unit})",
        min_value=0.1,
        max_value=20.0 if unit == "mmol/L" else 2000.0,
        value=1.9 if unit == "mmol/L" else 168.0,
        step=0.1, format="%.2f"
    )
    hdl = col6.number_input(
        f"HDL cholesterol ({unit})",
        min_value=0.1,
        max_value=10.0 if unit == "mmol/L" else 400.0,
        value=1.0 if unit == "mmol/L" else 39.0,
        step=0.01, format="%.2f"
    )

    ht = st.selectbox("Hypertension", options=["No (0)", "Yes (1)"], index=1)
    hypertension = 1 if "Yes" in ht else 0

# =========================
#   CÁLCULOS
# =========================
# Conversión unidades mg/dL -> mmol/L (TG: ÷88.57 ; HDL: ÷38.67)
if unit == "mg/dL":
    tg_mmol = tg / 88.57
    hdl_mmol = hdl / 38.67
else:
    tg_mmol = tg
    hdl_mmol = hdl

# CMI = [TG (mmol/L) / HDL (mmol/L)] × [WC (cm) / Height (cm)]
cmi = (tg_mmol / hdl_mmol) * (wc_cm / height_cm)

# VAI (females)
vai = None
if is_female:
    vai = (wc_cm / (36.58 + 1.89 * bmi)) * (tg_mmol / 0.81) * (1.52 / hdl_mmol)

# FOSSI
if is_female:
    fossi = -18.811 + (0.209 * age) + (0.350 * bmi) + (1.359 * cmi) + (0.799 * hypertension) + (0.203 * (vai if vai is not None else 0.0))
else:
    fossi = -4.663 + (0.039 * age) + (0.045 * bmi) - (0.223 * cmi) + (0.015 * wc_cm)

def format_number(x, dec=2):
    try:
        return f"{x:.{dec}f}"
    except Exception:
        return "—"

# =========================
#   BOTÓN CALCULAR + LOG
# =========================
calc = st.button("Calculate FOSSI risk", type="primary")

if calc:
    # registrar cálculo
    log_event("calculate", fossi_type="FOSSI-F" if is_female else "FOSSI-M")

    # Umbrales y mensajes
    if is_female:
        if fossi < 5.84:
            risk_label, color, expl = "Low", "green", "Metabolically quiescent; FO prevalence ~12%."
        elif fossi <= 7.88:
            risk_label, color, expl = "Intermediate", "yellow", "Early metabolic priming; bone status variable."
        elif fossi <= 9.58:
            risk_label, color, expl = "High", "orange", "High-risk metabolic footprint; trabecular damage likely."
        else:
            risk_label, color, expl = "Very High", "red", "Near-certain FO; severe metabolic burden; trabecular deterioration."
    else:
        if fossi < 0.71:
            risk_label, color, expl = "Grey zone (<0.71)", "yellow", "Baseline FO prevalence ~17%; monitor closely."
        else:
            risk_label, color, expl = "High/Very High (≥0.71)", "red", "Full FO phenotype; pronounced metabolic overload and trabecular decline."

    st.divider()
    st.subheader("Results")

    # Caja de color
    color_map = {"green": "#E8F5E9", "yellow": "#FFFDE7", "orange": "#FFF3E0", "red": "#FFEBEE"}
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

    # =========================
#   FOSSI PLOT (Python)
# =========================
import io
import numpy as np
import matplotlib.pyplot as plt

def make_fossi_curve(is_female: bool):
    """
    Devuelve (x, prob, cutoffs, zones, title, subtitle, x_limits) replicando el script R.
    - Mujeres: sigmoide 1/(1+exp(-1.2*(x-8.7))) con x en [2.5, 16.5]
    - Hombres: curva más 'vertical' alrededor del corte 0.71 (ajuste ilustrativo)
    """
    if is_female:
        x = np.linspace(2.5, 16.5, 600)
        prob = 1/(1 + np.exp(-1.2*(x - 8.7)))
        cutoffs = [5.84, 7.88, 9.58]
        zones = ["Low", "Intermediate", "High", "Very high"]
        title = "FOSSI-F (women): Non-linear risk"
        subtitle = "Sigmoid trajectory with wide transition zone"
        x_limits = (2.5, 16.5)
    else:
        # --- FOSSI-M: near-vertical tipping point 0.45–0.71 ---
        x = np.linspace(0.40, 1.00, 600)
        baseline, top, center, slope = 0.12, 0.98, 0.58, 92
        # Reproduce el comportamiento de plogis((x-center)*slope)
        prob = np.where(
            x < 0.45, baseline,
            np.where(
                x > 0.71, top,
                baseline + (top - baseline) / (1 + np.exp(-(x - center) * slope))
            )
        )
        cutoffs = [0.71]
        zones = ["Grey/Low", "High"]
        title = "FOSSI-M: Non-linear risk"
        subtitle = "Near-vertical tipping point (0.45–0.71); ROC cut-off at 0.71"
        x_limits = (0.40, 1.00)
    return x, prob, cutoffs, zones, title, subtitle, x_limits

def plot_fossi_curve_py(x, prob, cutoffs, zones, patient_x, title, subtitle, x_limits):
    import io
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    all_breaks = [-np.inf] + list(cutoffs) + [np.inf]
    xmin, xmax = x_limits

    # Colores zonas (gris, amarillo, naranja, rojo)
    if len(zones) == 4:
        fills = [(0.83,0.83,0.83,0.35), (1.0,1.0,0.0,0.35), (1.0,0.65,0.0,0.35), (1.0,0.0,0.0,0.2)]
    else:
        fills = [(0.83,0.83,0.83,0.35), (1.0,0.0,0.0,0.25)]

    # ↑ altura mayor y márgenes
    fig, ax = plt.subplots(figsize=(7.5,6.2))
    fig.subplots_adjust(top=0.80, bottom=0.12, left=0.10, right=0.98)

    # Rectángulos por zona
    for i in range(len(zones)):
        z_xmin = max(all_breaks[i], xmin)
        z_xmax = min(all_breaks[i+1], xmax)
        if z_xmin < z_xmax:
            ax.axvspan(z_xmin, z_xmax, ymin=0, ymax=1, facecolor=fills[i], edgecolor=None)

    # Línea de prob
    prob_line, = ax.plot(x, prob, linewidth=2, label="FO probability")

    # Líneas de corte (una sola entrada en leyenda para todos)
    cutoff_handles = []
    for j, c in enumerate(cutoffs):
        if xmin <= c <= xmax:
            ax.axvline(c, linestyle="--", linewidth=1, color="black")
            if j == 0:
                cutoff_handles = [Line2D([0], [0], color="black", linestyle="--", linewidth=1, label="Cut-offs")]

    # Punto del paciente
    patient_handle = []
    if patient_x is not None:
        if patient_x <= x.min():
            p_y = prob[0]
        elif patient_x >= x.max():
            p_y = prob[-1]
        else:
            i = np.searchsorted(x, patient_x) - 1
            i = np.clip(i, 0, len(x)-2)
            t = (patient_x - x[i]) / (x[i+1]-x[i])
            p_y = prob[i] + t*(prob[i+1]-prob[i])

        ax.plot([patient_x], [p_y], marker='o', markersize=6,
                markeredgecolor='black', markerfacecolor='white', linewidth=0)
        ax.text(patient_x, min(1.0, p_y + 0.05), f"Patient: {patient_x:.2f}",
                fontsize=10, fontweight='bold', ha='center', va='bottom')
        patient_handle = [Line2D([0],[0], marker='o', linestyle='None',
                                 markerfacecolor='white', markeredgecolor='black',
                                 markersize=6, label="Patient")]

    # Ejes y títulos
    ax.set_xlim(x_limits)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Probability of Fast Ossifier (FO)")
    ax.set_xlabel("FOSSI value and clinical cut-off points (dashed lines)")

    # Usamos suptitle (título principal) + título del eje (como subtítulo) para evitar solapes
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.94)
    ax.set_title(subtitle, fontsize=11, pad=8)

    # Grid y ticks %
    ax.grid(True, which='major', linewidth=0.6, alpha=0.5)
    yticks = np.linspace(0,1,6)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{int(y*100)}%" for y in yticks])

    # Leyenda: parches para zonas
    zone_patches = [Patch(facecolor=fills[i], edgecolor='none', label=zones[i]) for i in range(len(zones))]
    handles = zone_patches + cutoff_handles

    # Colocamos la leyenda arriba fuera del área del gráfico para no tapar títulos
    leg = ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.2),
                    ncol=len(handles), frameon=False)

    # Asegurar buen layout final
    plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.94])  # deja sitio al suptitle y leyenda

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


# ------ Renderizar en la UI tras calcular ------
if calc:
    x, prob, cutoffs, zones, title, subtitle, x_limits = make_fossi_curve(is_female)
    png_buf = plot_fossi_curve_py(x, prob, cutoffs, zones, fossi, title, subtitle, x_limits)

    st.subheader("Risk curve")
    st.image(png_buf, caption="FOSSI probability curve with clinical cut-offs and patient marker", use_container_width=True)

    st.download_button(
        "Download PNG",
        data=png_buf,
        file_name=f"{'FOSSI_F' if is_female else 'FOSSI_M'}_{fossi:.2f}.png",
        mime="image/png",
        type="secondary",
        help="Save the figure as a 300 dpi PNG"
    )


    with st.expander("Details and derived indices"):
        colA, colB = st.columns(2)
        colA.metric("CMI", format_number(cmi, 3))
        if is_female:
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
    "References: Pariente et al., 'Fast Ossifier in DISH.' RMD Open, Sept 2025. "
    "https://doi.org/10.1136/rmdopen-2025-006024 | "
    "'Fast Ossifier Stratification Index (FOSSI): A propensity score-derived tool in DISH' "
    "(Oct 2025, submitted).\n\n"
    "This tool provides research-oriented risk stratification and does not replace clinical judgment. "
)

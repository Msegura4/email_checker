"""
streamlit_app.py
Interface Streamlit pour l'agent de traitement de tickets email.
"""

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv, set_key

load_dotenv()

# ── Lecture des secrets (Streamlit Cloud > .env) ──────────────────────────────
def _secret(key: str, default: str = "") -> str:
    """Lit depuis st.secrets en priorité, puis os.getenv, puis default."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

def _inject_secrets_to_env():
    """Injecte les st.secrets dans os.environ pour compatibilité avec dotenv."""
    for key in ["GROQ_KEY", "MAIL_PROVIDER", "IMAP_HOST", "IMAP_PORT",
                "IMAP_USER", "IMAP_PASSWORD", "IMAP_FOLDER", "IMAP_USE_SSL"]:
        val = _secret(key)
        if val:
            os.environ[key] = val

    # Gmail OAuth via secrets : écriture des fichiers JSON si absents
    gmail_token = _secret("GMAIL_TOKEN")
    if gmail_token and not Path("token.json").exists():
        Path("token.json").write_text(gmail_token, encoding="utf-8")

    gmail_creds = _secret("GMAIL_CREDENTIALS")
    if gmail_creds and not Path("credentials.json").exists():
        Path("credentials.json").write_text(gmail_creds, encoding="utf-8")

_inject_secrets_to_env()

from profile_manager import (
    list_profiles,
    list_default_profiles,
    list_user_profiles,
    load_profile,
    save_profile,
    delete_profile,
    duplicate_profile,
    is_default_profile,
    slugify,
    build_context_txt,
    build_prompt_txt,
    get_category_to_sheet,
)

# ── Config page ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Email Checker",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded",
)

ENV_FILE = Path(".env")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _profile_label(p: dict) -> str:
    lock = " 🔒" if p.get("_is_default") else ""
    return f"{p.get('emoji','📁')} {p['nom']}{lock}"


def _reload_profiles():
    st.session_state.pop("profiles_cache", None)


def _get_profiles() -> list[dict]:
    if "profiles_cache" not in st.session_state:
        st.session_state.profiles_cache = list_profiles()
    return st.session_state.profiles_cache


def _nav(page_id: str):
    st.session_state.page = page_id
    st.rerun()


# ── Session state init ────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "lancer"
if "active_profile_idx" not in st.session_state:
    st.session_state.active_profile_idx = 0

page = st.session_state.page



# ── Modal : choisir un profil ─────────────────────────────────────────────────
@st.dialog("Choisir un profil", width="large")
def profile_picker():
    profiles_all = _get_profiles()

    st.markdown("""
    <style>
    .profile-card {
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
        cursor: pointer;
        transition: background 0.2s, border-color 0.2s;
        background: rgba(255,255,255,0.03);
        min-height: 90px;
    }
    .profile-card:hover {
        background: rgba(255,255,255,0.08);
        border-color: rgba(255,255,255,0.25);
    }
    .profile-card.active {
        border-color: #4f8ef7;
        background: rgba(79,142,247,0.08);
    }
    .profile-card-title {
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .profile-card-desc {
        font-size: 0.82rem;
        color: #94a3b8;
        margin: 0;
    }
    </style>
    """, unsafe_allow_html=True)

    cols = st.columns(2)
    for i, p in enumerate(profiles_all):
        lock     = " 🔒" if p.get("_is_default") else ""
        emoji    = p.get("emoji", "📁")
        nom      = p["nom"]
        desc     = p.get("description", "")
        is_active = (i == st.session_state.active_profile_idx)
        active_class = "active" if is_active else ""
        active_badge = " ✅" if is_active else ""

        with cols[i % 2]:
            st.markdown(
                f"""<div class="profile-card {active_class}">
                    <div class="profile-card-title">{emoji} {nom}{lock}{active_badge}</div>
                    <p class="profile-card-desc">{desc}</p>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Sélectionner", key=f"pick_{i}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_profile_idx = i
                st.session_state.pop("profiles_cache", None)
                st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<style>
div[data-testid="stSidebarNav"] { display: none; }
.nav-section { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
               letter-spacing: 0.08em; color: #94a3b8; margin: 1rem 0 0.3rem 0; }
div[data-testid="stSidebar"] button {
    width: 100%; text-align: left; background: transparent;
    border: none; border-radius: 6px; padding: 0.35rem 0.6rem;
    color: #e2e8f0; font-size: 0.9rem; cursor: pointer;
    transition: background 0.15s;
}
div[data-testid="stSidebar"] button:hover { background: rgba(255,255,255,0.08); }
</style>
""", unsafe_allow_html=True)

# Profil actif
profiles = _get_profiles()
if st.session_state.active_profile_idx >= len(profiles):
    st.session_state.active_profile_idx = 0
active_profile = profiles[st.session_state.active_profile_idx] if profiles else None

# En-tête : titre + profil actif dans le même bloc
st.sidebar.title("Bienvenu dans l'application Email Checker")
if active_profile:
    st.sidebar.markdown(
        f"<strong>Tri actif :<br>{active_profile.get('emoji','📁')} {active_profile['nom']}</strong>",
        unsafe_allow_html=True,
    )
if st.sidebar.button("↩ Changer de profil", key="btn_change_profile"):
    profile_picker()

st.sidebar.divider()


# ── Section 1 : Principal ─────────────────────────────────────────────────────
st.sidebar.markdown('<p class="nav-section">Principal</p>', unsafe_allow_html=True)
if st.sidebar.button("🚀 Lancer le tri", key="nav_lancer"):
    _nav("lancer")
if st.sidebar.button("📬 Connexion mail", key="nav_mail"):
    _nav("admin_mail")

st.sidebar.divider()

# ── Section 2 : Gestion des tris ──────────────────────────────────────────
st.sidebar.markdown('<p class="nav-section">Gestion des tris</p>', unsafe_allow_html=True)
if st.sidebar.button("🔒 Tris par défaut", key="nav_defaut"):
    _nav("profils_defaut")
if st.sidebar.button("📋 Dupliquer un tri par défaut", key="nav_dupliquer"):
    _nav("profils_dupliquer")
if st.sidebar.button("➕ Créer un tri", key="nav_creer"):
    _nav("profils_creer")
if st.sidebar.button("✏️ Mes tris", key="nav_mes"):
    _nav("mes_profils")

st.sidebar.divider()

# ── Section 3 : Administration ────────────────────────────────────────────────
st.sidebar.markdown('<p class="nav-section">Administration</p>', unsafe_allow_html=True)
if st.sidebar.button("🔑 API", key="nav_api"):
    _nav("admin_api")
if st.sidebar.button("🔍 Diagnostic", key="nav_diag"):
    _nav("admin_diag")
if st.sidebar.button("🚧 Améliorations à venir", key="nav_roadmap"):
    _nav("roadmap")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Lancer le traitement
# ═════════════════════════════════════════════════════════════════════════════
if page == "lancer":
    st.title("🚀 Lancer le tri")
    if not active_profile:
        st.warning("Aucun tri disponible.")
        st.stop()

    st.divider()

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        max_emails = st.number_input("Nombre max d'emails", min_value=1, max_value=1000, value=50)
    with col_b:
        mark_as_read = st.toggle("Marquer comme lus après traitement", value=False)
    with col_c:
        delay = st.slider("Délai entre appels LLM (s)", 0.0, 2.0, 0.5, 0.1)

    st.divider()
    log_area = st.empty()

    groq_ok  = bool(os.getenv("GROQ_KEY"))

    if st.button("▶️ Démarrer", type="primary", use_container_width=True):
        if not groq_ok:
            st.error("Clé Groq manquante. Configurez-la dans 🔑 API.")
            st.stop()

        Path("context.txt").write_text(build_context_txt(active_profile), encoding="utf-8")
        Path("prompt.txt").write_text(build_prompt_txt(active_profile),   encoding="utf-8")

        logs = []

        def add_log(msg):
            logs.append(msg)
            log_area.code("\n".join(logs), language=None)

        with st.spinner("Traitement en cours..."):
            try:
                from agent_mail import classify_mail

                provider = os.getenv("MAIL_PROVIDER", "gmail").lower()
                if provider == "gmail":
                    from mail_reader_gmail import GmailReader as MailReader
                else:
                    from mail_reader_imap import IMAPReader as MailReader

                add_log(f"[INFO] Profil : {active_profile['nom']}")
                add_log(f"[INFO] Provider : {provider.upper()}")
                add_log("[INFO] Connexion au provider mail...")

                category_to_sheet = get_category_to_sheet(active_profile)

                with MailReader() as reader:
                    add_log(f"[INFO] Récupération des emails (max {max_emails})...")
                    tickets = reader.fetch_unread_emails(max_results=max_emails, mark_as_read=False)
                    add_log(f"[INFO] {len(tickets)} emails récupérés.")

                    if not tickets:
                        add_log("[OK] Aucun email non lu à traiter.")
                        st.success("Aucun email non lu.")
                        st.stop()

                    results = []
                    success, errors = 0, 0

                    for i, ticket in enumerate(tickets, 1):
                        sujet   = ticket.get("sujet", "(Sans sujet)")
                        corps   = ticket.get("corps", "")
                        mail_id = ticket.get("id")
                        add_log(f"[{i}/{len(tickets)}] {sujet[:60]}...")

                        try:
                            result    = classify_mail(f"Sujet : {sujet}\n\n{corps}")
                            categorie = result.get("categorie", "")
                            urgence   = result.get("urgence",   "")
                            resume    = result.get("résumé",    sujet)
                            results.append({
                                "Sujet":     sujet,
                                "Catégorie": categorie,
                                "Urgence":   urgence,
                                "Synthèse":  resume,
                                "Corps":     corps,
                                "_mail_id":  mail_id,
                            })
                            if mark_as_read:
                                reader.mark_as_read(mail_id)
                            add_log(f"  → {categorie} | {urgence}")
                            success += 1
                        except Exception as e:
                            add_log(f"  ❌ Erreur : {e}")
                            errors += 1

                        if i < len(tickets):
                            time.sleep(delay)

                st.session_state["last_results"] = results
                add_log(f"\n✅ Terminé — {success} succès, {errors} erreurs.")

                if errors == 0:
                    st.success(f"✅ {success} emails traités avec succès !")
                else:
                    st.warning(f"⚠️ {success} succès, {errors} erreurs.")

            except Exception as e:
                add_log(f"\n❌ Erreur fatale : {e}")
                st.error(f"Erreur : {e}")

    # ── Résultats ─────────────────────────────────────────────────────────────
    if "last_results" in st.session_state and st.session_state["last_results"]:
        import pandas as pd
        st.divider()
        results = st.session_state["last_results"]

        # Init état des actions
        if "mail_actions" not in st.session_state:
            st.session_state.mail_actions = {}  # idx -> "supprimer" | "conserver" | None

        # Compter les emails actifs (non supprimés)
        actifs = [r for i, r in enumerate(results) if st.session_state.mail_actions.get(i) != "supprimer"]
        conserves = sum(1 for v in st.session_state.mail_actions.values() if v == "conserver")
        supprimes = sum(1 for v in st.session_state.mail_actions.values() if v == "supprimer")

        col_title, col_stats = st.columns([3, 2])
        with col_title:
            st.markdown(f"### 📋 Résultats — {len(actifs)} emails")
        with col_stats:
            st.caption(f"{conserves} à conserver · 🗑️ {supprimes} à supprimer")

        # Dialog pour afficher un email complet
        @st.dialog("📧 Contenu de l'email", width="large")
        def show_email(idx):
            import re
            mail = results[idx]
            st.markdown(f"**Sujet :** {mail['Sujet']}")
            st.markdown(f"**Catégorie :** {mail['Catégorie']}")
            st.markdown(f"**Urgence :** {mail['Urgence']}")
            st.divider()
            st.markdown("**Synthèse :**")
            st.info(mail["Synthèse"])
            st.markdown("**Corps du mail :**")
            corps = mail.get("Corps", "(Corps non disponible)")
            corps = re.sub(r"<style[^>]*>.*?</style>", " ", corps, flags=re.DOTALL)
            corps = re.sub(r"<script[^>]*>.*?</script>", " ", corps, flags=re.DOTALL)
            corps = re.sub(r"<[^>]+>", " ", corps)
            corps = re.sub(r"&nbsp;", " ", corps)
            corps = re.sub(r"&amp;", "&", corps)
            corps = re.sub(r"&lt;", "<", corps)
            corps = re.sub(r"&gt;", ">", corps)
            corps = re.sub(r"[ \t]{2,}", " ", corps)
            corps = re.sub(r"\n{3,}", "\n\n", corps).strip()
            st.markdown(
                f"<div style='background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); "
                f"border-radius:8px; padding:16px; font-size:0.88rem; line-height:1.6; "
                f"white-space:pre-wrap; user-select:text; color:#e2e8f0; max-height:350px; overflow-y:auto;'>"
                f"{corps}</div>",
                unsafe_allow_html=True,
            )

        # Fonction pour mettre à la corbeille sur Gmail
        def trash_on_gmail(mail_ids: list) -> tuple[int, int]:
            provider = os.getenv("MAIL_PROVIDER", "gmail").lower()
            ok, fail = 0, 0
            if provider == "gmail":
                try:
                    from google.oauth2.credentials import Credentials as _GC
                    from googleapiclient.discovery import build as _gb
                    _creds = _GC.from_authorized_user_file("token.json")
                    _svc   = _gb("gmail", "v1", credentials=_creds)
                    for mid in mail_ids:
                        if mid:
                            try:
                                _svc.users().messages().trash(userId="me", id=mid).execute()
                                ok += 1
                            except Exception:
                                fail += 1
                except Exception:
                    fail += len(mail_ids)
            return ok, fail
        urgency_order = {u["label"]: i for i, u in enumerate(active_profile.get("urgences", []))}
        sorted_results = sorted(
            enumerate(results),
            key=lambda x: urgency_order.get(x[1]["Urgence"], 99)
        )

        # Onglets par catégorie
        categories = [c["label"] for c in active_profile.get("categories", [])]
        tab_labels = []
        for cat in categories:
            count = sum(1 for _, r in sorted_results
                        if r["Catégorie"] == cat
                        and st.session_state.mail_actions.get(_) != "supprimer")
            tab_labels.append(f"{cat} ({count})")

        tabs = st.tabs(tab_labels)
        for tab, cat in zip(tabs, categories):
            with tab:
                cat_results = [(gi, r) for gi, r in sorted_results
                               if r["Catégorie"] == cat
                               and st.session_state.mail_actions.get(gi) != "supprimer"]
                if not cat_results:
                    st.caption("Aucun email dans cette catégorie.")
                else:
                    # En-tête colonnes
                    h1, h2, h3, h4, h5 = st.columns([0.5, 5, 2, 1, 1])
                    with h1: st.caption("☑")
                    with h2: st.caption("Sujet")
                    with h3: st.caption("Urgence")
                    with h4: st.caption("")
                    with h5: st.caption("")

                    for gi, mail in cat_results:
                        action = st.session_state.mail_actions.get(gi)
                        is_kept = action == "conserver"

                        col_chk, col_sujet, col_urg, col_view, col_act = st.columns([0.5, 5, 2, 1, 1])

                        with col_chk:
                            checked = st.checkbox("", key=f"chk_{gi}", value=is_kept, label_visibility="collapsed")

                        with col_sujet:
                            style = "color:#4ade80;" if is_kept else ""
                            st.markdown(
                                f"<span style='font-size:0.9rem;{style}'>{mail['Sujet'][:75]}</span>",
                                unsafe_allow_html=True
                            )

                        with col_urg:
                            st.caption(mail["Urgence"])

                        with col_view:
                            if st.button("👁️", key=f"view_{gi}", help="Voir l'email"):
                                show_email(gi)

                        with col_act:
                            if checked and not is_kept:
                                st.session_state.mail_actions[gi] = "conserver"
                                st.rerun()
                            elif not checked and is_kept:
                                st.session_state.mail_actions[gi] = None
                                st.rerun()

                    # Bouton supprimer les sélectionnés
                    selected = [gi for gi, _ in cat_results if st.session_state.mail_actions.get(gi) == "conserver"]
                    if selected:
                        st.markdown("")
                        col_del, col_reset = st.columns([1, 1])
                        with col_del:
                            if st.button(f"🗑️ Supprimer la sélection ({len(selected)})", key=f"del_{cat}", type="secondary"):
                                mail_ids = [results[gi].get("_mail_id") for gi in selected]
                                ok, fail = trash_on_gmail(mail_ids)
                                for gi in selected:
                                    st.session_state.mail_actions[gi] = "supprimer"
                                if ok:
                                    st.success(f"✅ {ok} email(s) mis à la corbeille sur Gmail.")
                                if fail:
                                    st.warning(f"⚠️ {fail} email(s) non supprimés (IMAP ou erreur).")
                                st.rerun()
                        with col_reset:
                            if st.button("↩️ Désélectionner", key=f"reset_{cat}", type="secondary"):
                                for gi in selected:
                                    st.session_state.mail_actions[gi] = None
                                st.rerun()

        st.divider()
        col_csv, col_clear = st.columns([2, 1])
        with col_csv:
            df_export = pd.DataFrame([
                {k: v for k, v in r.items() if k != "Corps"}
                for i, r in enumerate(results)
                if st.session_state.mail_actions.get(i) != "supprimer"
            ])
            csv = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Exporter en CSV",
                data=csv,
                file_name=f"resultats_{active_profile['id']}.csv",
                mime="text/csv",
                type="primary",
            )
        with col_clear:
            if st.button("🔄 Réinitialiser les actions", type="secondary"):
                st.session_state.mail_actions = {}
                st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Profils par défaut
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_defaut":
    st.title("🔒 Tris par défaut")

    st.markdown("""
    <style>
    details[open] > summary {
        background-color: #fef2f2 !important;
        border-left: 4px solid #f87171 !important;
        border-radius: 0 6px 6px 0;
        padding-left: 1rem !important;
    }
    details[open] > summary p { color: #b91c1c !important; font-weight: 600; }
    details[open] > summary svg { fill: #ef4444 !important; }
    </style>
    """, unsafe_allow_html=True)

    default_profiles = list_default_profiles()
    if not default_profiles:
        st.info("Aucun profil par défaut trouvé dans profiles/defaults/.")
    else:
        st.info(
            "Ces propositions de tris sont fournis avec l'application et ne peuvent pas être modifiés. "
            "Dépliez-les pour voir leur contenu complet, et **dupliquez-les** pour créer votre propre version."
        )
        st.divider()

        for p in default_profiles:
            pid   = p["id"]
            pcats = p.get("categories", [])
            purgs = p.get("urgences",   [])

            with st.expander(f"{p.get('emoji','📁')} **{p['nom']}**  🔒", expanded=False):
                st.markdown(f"_{p.get('description', '')}_")
                st.divider()

                st.markdown("**📂 Catégories**")
                for cat in pcats:
                    col_lbl, col_dsc = st.columns([1, 2])
                    with col_lbl:
                        st.markdown(f"**`{cat['label']}`**")
                    with col_dsc:
                        st.markdown(f"<span style='color:#555'>{cat.get('description','')}</span>",
                                    unsafe_allow_html=True)

                st.divider()

                st.markdown("**🚨 Niveaux d'urgence**")
                for urg in purgs:
                    col_lbl, col_dsc = st.columns([1, 2])
                    with col_lbl:
                        st.markdown(f"**`{urg['label']}`**")
                    with col_dsc:
                        st.markdown(f"<span style='color:#555'>{urg.get('description','')}</span>",
                                    unsafe_allow_html=True)

                st.divider()

                st.markdown("**📝 Contexte & Prompt LLM**")
                st.markdown("**Contexte**")
                st.code(p.get("context", ""), language=None)
                st.markdown("**Prompt de base**")
                st.code(p.get("prompt", ""), language=None)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Créer depuis un défaut
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_dupliquer":
    st.title("📋 Créer à partir d'un tri par défaut")

    default_profiles = list_default_profiles()
    if not default_profiles:
        st.info("Aucun tri par défaut disponible.")
    else:
        st.info("Choisissez un tri par défaut comme point de départ, donnez-lui un nouveau nom, puis personnalisez-le dans **✏️ Mes tris**.")
        st.divider()

        default_ids = [p["id"] for p in default_profiles]
        source_id = st.selectbox(
            "Tri source",
            default_ids,
            format_func=lambda pid: next(
                (f"{p.get('emoji','📁')} {p['nom']}" for p in default_profiles if p["id"] == pid),
                pid,
            ),
        )
        source = next((p for p in default_profiles if p["id"] == source_id), None)

        new_name = st.text_input(
            "Nom du nouveau tri",
            value=f"{source['nom']} (copie)" if source else "",
            placeholder="ex : Support IT — Équipe Lyon",
        )

        if st.button("📋 Créer ce profil", type="primary", use_container_width=True):
            if not new_name.strip():
                st.error("Le nom ne peut pas être vide.")
            else:
                try:
                    new_p = duplicate_profile(source_id, new_name.strip())
                    _reload_profiles()
                    st.success(f"✅ Profil **'{new_p['nom']}'** créé ! Rendez-vous dans **✏️ Mes profils** pour le modifier.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Créer un profil from scratch
# ═════════════════════════════════════════════════════════════════════════════
elif page == "profils_creer":
    st.title("➕ Créer un tri")

    with st.form("new_profile"):
        col1, col2 = st.columns([3, 1])
        with col1:
            nom   = st.text_input("Nom du nouveau tri *", placeholder="ex: Chargé RH")
        with col2:
            emoji = st.text_input("Emoji", value="📁", max_chars=2)
        desc    = st.text_area("Description", height=80)
        context = st.text_area("Contexte LLM", height=100, placeholder="Les emails proviennent de...")
        prompt  = st.text_area("Prompt de base", height=100, placeholder="Tu es un agent spécialisé dans...")

        st.subheader("Catégories (min. 2)")
        cats = []
        for j in range(5):
            c1, c2 = st.columns([2, 4])
            with c1:
                lbl = st.text_input(f"Catégorie {j+1}", key=f"new_cat_{j}")
            with c2:
                dsc = st.text_input("Description", key=f"new_cat_dsc_{j}", label_visibility="collapsed")
            if lbl:
                cats.append({"id": slugify(lbl), "label": lbl, "description": dsc})

        st.subheader("Urgences")
        use_default_urgences = st.checkbox("Utiliser les urgences standard (Critique → Anodine)", value=True)

        submitted = st.form_submit_button("✅ Créer le profil", type="primary")

    if submitted:
        if not nom:
            st.error("Le nom est obligatoire.")
        elif len(cats) < 2:
            st.error("Ajoutez au moins 2 catégories.")
        else:
            default_urgences = [
                {"label": "Critique", "description": "Impact majeur, opération impossible."},
                {"label": "Élevée",   "description": "Forte gêne, traitement prioritaire."},
                {"label": "Modérée",  "description": "Gêne notable mais non bloquante."},
                {"label": "Faible",   "description": "Problème mineur."},
                {"label": "Anodine",  "description": "Demande simple, aucun enjeu d'urgence."},
            ]
            new_profile = {
                "id":          slugify(nom),
                "nom":         nom,
                "emoji":       emoji,
                "description": desc,
                "context":     context,
                "prompt":      prompt,
                "categories":  cats,
                "urgences":    default_urgences if use_default_urgences else [],
            }
            try:
                save_profile(new_profile)
                _reload_profiles()
                st.success(f"✅ Profil '{nom}' créé !")
                st.rerun()
            except Exception as e:
                st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Mes profils
# ═════════════════════════════════════════════════════════════════════════════
elif page == "mes_profils":
    st.title("✏️ Mes profils")

    st.markdown("""
    <style>
    details[open] > summary {
        background-color: #fef2f2 !important;
        border-left: 4px solid #f87171 !important;
        border-radius: 0 6px 6px 0;
        padding-left: 1rem !important;
    }
    details[open] > summary p { color: #b91c1c !important; font-weight: 600; }
    details[open] > summary svg { fill: #ef4444 !important; }
    </style>
    """, unsafe_allow_html=True)

    user_profiles = list_user_profiles()

    if not user_profiles:
        st.info(
            "Vous n'avez pas encore de tri personnalisé. "
            "Dupliquez un profil par défaut ou créez-en un depuis les boutons dédiés"
        )
    else:
        st.caption("Dépliez un profil pour le modifier. La suppression est disponible en bas de chaque fiche.")
        st.divider()

        for p in user_profiles:
            pid   = p["id"]
            pcats = p.get("categories", [])
            purgs = p.get("urgences",   [])

            with st.expander(f"{p.get('emoji','📁')} **{p['nom']}**", expanded=False):

                with st.form(f"edit_{pid}"):
                    st.markdown("**Informations générales**")
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        new_nom   = st.text_input("Nom", value=p["nom"], key=f"nom_{pid}")
                    with col2:
                        new_emoji = st.text_input("Emoji", value=p.get("emoji", "📁"), max_chars=2, key=f"emoji_{pid}")
                    new_desc = st.text_area("Description", value=p.get("description", ""), height=68, key=f"desc_{pid}")

                    st.divider()

                    st.markdown("**📝 Contexte & Prompt LLM**")
                    new_context = st.text_area("Contexte",       value=p.get("context", ""), height=110, key=f"ctx_{pid}")
                    new_prompt  = st.text_area("Prompt de base", value=p.get("prompt",  ""), height=110, key=f"prompt_{pid}")

                    st.divider()

                    st.markdown("**📂 Catégories**")
                    new_cats = []
                    for j, cat in enumerate(pcats):
                        c1, c2, c3 = st.columns([2, 3, 0.7])
                        with c1:
                            lbl  = st.text_input("Label",       value=cat["label"],                key=f"cat_lbl_{pid}_{j}", label_visibility="collapsed")
                        with c2:
                            dsc  = st.text_input("Description", value=cat.get("description", ""), key=f"cat_dsc_{pid}_{j}", label_visibility="collapsed")
                        with c3:
                            keep = st.checkbox("✓", value=True, key=f"cat_keep_{pid}_{j}", help="Décocher pour supprimer")
                        if keep and lbl:
                            new_cats.append({"id": slugify(lbl), "label": lbl, "description": dsc})

                    st.caption("Nouvelle catégorie")
                    na1, na2 = st.columns([2, 3])
                    with na1:
                        add_lbl = st.text_input("Label",       key=f"add_cat_lbl_{pid}", placeholder="Label...",       label_visibility="collapsed")
                    with na2:
                        add_dsc = st.text_input("Description", key=f"add_cat_dsc_{pid}", placeholder="Description...", label_visibility="collapsed")
                    if add_lbl:
                        new_cats.append({"id": slugify(add_lbl), "label": add_lbl, "description": add_dsc})

                    st.divider()

                    st.markdown("**🚨 Niveaux d'urgence**")
                    new_urgences = []
                    for k, urg in enumerate(purgs):
                        u1, u2 = st.columns([1, 3])
                        with u1:
                            ulbl = st.text_input("Niveau",      value=urg["label"],                key=f"urg_lbl_{pid}_{k}", label_visibility="collapsed")
                        with u2:
                            udsc = st.text_input("Description", value=urg.get("description", ""), key=f"urg_dsc_{pid}_{k}", label_visibility="collapsed")
                        if ulbl:
                            new_urgences.append({"label": ulbl, "description": udsc})

                    st.divider()
                    saved = st.form_submit_button("💾 Enregistrer les modifications", type="primary", use_container_width=True)

                if saved:
                    updated = {
                        "id": pid, "nom": new_nom, "emoji": new_emoji, "description": new_desc,
                        "context": new_context, "prompt": new_prompt,
                        "categories": new_cats, "urgences": new_urgences,
                    }
                    try:
                        save_profile(updated)
                        _reload_profiles()
                        st.success("✅ Profil enregistré !")
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))

                st.markdown("<div style='margin-top: 8px'></div>", unsafe_allow_html=True)
                col_spacer, col_del = st.columns([3, 1])
                with col_del:
                    if st.button("🗑️ Supprimer ce profil", key=f"del_{pid}", use_container_width=True):
                        try:
                            delete_profile(pid)
                            _reload_profiles()
                            st.warning(f"Profil '{p['nom']}' supprimé.")
                            st.rerun()
                        except PermissionError as e:
                            st.error(str(e))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — API
# ═════════════════════════════════════════════════════════════════════════════
elif page == "admin_api":
    st.title("🔑 API")
    st.caption("Ces valeurs sont sauvegardées dans votre fichier `.env`.")

    with st.form("env_form"):
        groq_key = st.text_input(
            "Clé API Groq (GROQ_KEY)",
            value=os.getenv("GROQ_KEY", ""),
            type="password",
            help="Obtenir sur console.groq.com/keys",
        )
        save_env = st.form_submit_button("💾 Sauvegarder", type="primary")

    if save_env:
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        if groq_key:
            set_key(str(ENV_FILE), "GROQ_KEY", groq_key)
        st.success("✅ Variables sauvegardées dans .env")
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Connexion mail
# ═════════════════════════════════════════════════════════════════════════════
elif page == "admin_mail":
    st.title("📬 Connexion mail")

    current_provider = os.getenv("MAIL_PROVIDER", "gmail")
    provider = st.radio(
        "Choisir le type de compte mail",
        ["gmail", "imap"],
        index=0 if current_provider == "gmail" else 1,
        horizontal=True,
        format_func=lambda x: "📧 Gmail (OAuth2)" if x == "gmail" else "📬 IMAP (Thunderbird, Outlook...)",
    )
    if provider != current_provider:
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        set_key(str(ENV_FILE), "MAIL_PROVIDER", provider)
        st.rerun()

    if provider == "gmail":

        st.divider()
        st.markdown("**📧 Compte connecté**")
        if not Path("token.json").exists():
            st.warning("⚠️ Aucun token trouvé — lancez `python3 generate_token.py` pour vous connecter.")
        else:
            try:
                from google.oauth2.credentials import Credentials as _GCreds
                from google.auth.transport.requests import Request as _GRequest
                from googleapiclient.discovery import build as _gbuild

                _creds = _GCreds.from_authorized_user_file("token.json")
                if _creds.expired and _creds.refresh_token:
                    _creds.refresh(_GRequest())
                _svc      = _gbuild("gmail", "v1", credentials=_creds)
                _profile  = _svc.users().getProfile(userId="me").execute()
                _email    = _profile.get("emailAddress", "inconnu")
                _n_msgs   = _profile.get("messagesTotal", "?")
                _n_threads = _profile.get("threadsTotal", "?")

                st.success(f"✅ Connecté en tant que **{_email}**")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Messages totaux", f"{_n_msgs:,}" if isinstance(_n_msgs, int) else _n_msgs)
                with col2:
                    st.metric("Fils de discussion", f"{_n_threads:,}" if isinstance(_n_threads, int) else _n_threads)
            except Exception as e:
                st.error(f"❌ Impossible de lire le compte : {e}")

    else:
        st.subheader("Configuration IMAP")
        with st.form("imap_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                imap_host = st.text_input("Hôte IMAP", value=os.getenv("IMAP_HOST", ""), placeholder="imap.gmail.com")
            with col2:
                imap_port = st.text_input("Port", value=os.getenv("IMAP_PORT", "993"))
            imap_user   = st.text_input("Email",        value=os.getenv("IMAP_USER",     ""))
            imap_pass   = st.text_input("Mot de passe", value=os.getenv("IMAP_PASSWORD", ""), type="password")
            imap_folder = st.text_input("Dossier",      value=os.getenv("IMAP_FOLDER",   "INBOX"))
            imap_ssl    = st.checkbox("SSL", value=os.getenv("IMAP_USE_SSL", "true") == "true")
            save_imap   = st.form_submit_button("💾 Sauvegarder la config IMAP", type="primary")

        if save_imap:
            if not ENV_FILE.exists():
                ENV_FILE.touch()
            set_key(str(ENV_FILE), "IMAP_HOST",     imap_host)
            set_key(str(ENV_FILE), "IMAP_PORT",     str(imap_port))
            set_key(str(ENV_FILE), "IMAP_USER",     imap_user)
            set_key(str(ENV_FILE), "IMAP_PASSWORD", imap_pass)
            set_key(str(ENV_FILE), "IMAP_FOLDER",   imap_folder)
            set_key(str(ENV_FILE), "IMAP_USE_SSL",  "true" if imap_ssl else "false")
            set_key(str(ENV_FILE), "MAIL_PROVIDER", "imap")
            st.success("✅ Config IMAP sauvegardée.")
            st.rerun()

        st.divider()
        st.markdown("**Hôtes IMAP courants**")
        st.table({
            "Service":   ["Gmail", "Outlook", "Yahoo", "OVH"],
            "IMAP_HOST": ["imap.gmail.com", "outlook.office365.com", "imap.mail.yahoo.com", "ssl0.ovh.net"],
            "Port":      ["993", "993", "993", "993"],
        })


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Diagnostic
# ═════════════════════════════════════════════════════════════════════════════
elif page == "admin_diag":
    st.title("🔍 Diagnostic")
    st.caption("Vérification de l'état de toutes les connexions et dépendances.")

    if st.button("🔄 Lancer les vérifications", type="primary"):
        st.session_state["run_diag"] = True

    if st.session_state.get("run_diag"):
        st.divider()

        # 1. Fichiers
        st.subheader("📁 Fichiers google (dev)")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("credentials.json", "Présent" if Path("credentials.json").exists() else "❌ Absent")
        with col2:
            st.metric("token.json", "Présent" if Path("token.json").exists() else "❌ Absent")

        st.divider()

        # 2. Variables d'environnement
        st.subheader("⚙️ Variables d'environnement")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("GROQ_KEY", "Définie" if os.getenv("GROQ_KEY") else "❌ Manquante")
        with col2:
            st.metric("Type de compte", os.getenv("MAIL_PROVIDER", "gmail").upper())

        st.divider()

        # 3. API Groq
        st.subheader("🤖 API Groq")
        groq_key = os.getenv("GROQ_KEY", "")
        if not groq_key:
            st.error("❌ Clé Groq non configurée.")
        else:
            with st.spinner("Test Groq..."):
                try:
                    from groq import Groq
                    _client = Groq(api_key=groq_key)
                    _client.chat.completions.create(
                        messages=[{"role": "user", "content": "OK"}],
                        model="llama-3.3-70b-versatile",
                        max_tokens=5,
                    )
                    st.success("Groq opérationnel — modèle : `llama-3.3-70b-versatile`")
                except Exception as e:
                    st.error(f"❌ Groq inaccessible : {e}")

        st.divider()

        # 4. Compte Gmail
        st.subheader("📧 Compte Gmail")
        if not Path("token.json").exists():
            st.warning("⚠️ token.json absent — lancez `generate_token.py`.")
        else:
            with st.spinner("Connexion Gmail..."):
                try:
                    from google.oauth2.credentials import Credentials as _GCreds
                    from google.auth.transport.requests import Request as _GRequest
                    from googleapiclient.discovery import build as _gbuild
                    _creds = _GCreds.from_authorized_user_file("token.json")
                    if _creds.expired and _creds.refresh_token:
                        _creds.refresh(_GRequest())
                    _svc     = _gbuild("gmail", "v1", credentials=_creds)
                    _profile = _svc.users().getProfile(userId="me").execute()
                    _email   = _profile.get("emailAddress", "inconnu")
                    _n_msgs  = _profile.get("messagesTotal", "?")
                    st.success(f"Connecté : **{_email}** ({_n_msgs:,} messages)" if isinstance(_n_msgs, int) else f"✅ Connecté : **{_email}**")
                except Exception as e:
                    st.error(f"❌ Gmail inaccessible : {e}")

        st.divider()

        # 5. IMAP (si configuré)
        if os.getenv("MAIL_PROVIDER", "gmail") == "imap":
            st.subheader("📬 Connexion IMAP")
            imap_host = os.getenv("IMAP_HOST", "")
            imap_user = os.getenv("IMAP_USER", "")
            imap_pass = os.getenv("IMAP_PASSWORD", "")
            if not all([imap_host, imap_user, imap_pass]):
                st.error("❌ Variables IMAP incomplètes.")
            else:
                with st.spinner(f"Connexion IMAP à {imap_host}..."):
                    try:
                        import imaplib
                        _port    = int(os.getenv("IMAP_PORT", 993))
                        _use_ssl = os.getenv("IMAP_USE_SSL", "true").lower() != "false"
                        _conn = imaplib.IMAP4_SSL(imap_host, _port) if _use_ssl else imaplib.IMAP4(imap_host, _port)
                        _conn.login(imap_user, imap_pass)
                        _conn.logout()
                        st.success(f"✅ IMAP connecté : **{imap_user}** @ {imap_host}")
                    except Exception as e:
                        st.error(f"❌ IMAP inaccessible : {e}")

        st.divider()

        # 7. Profils
        st.subheader("🗂️ Profils chargés")
        _all_profiles = _get_profiles()
        _defaults = [p for p in _all_profiles if p.get("_is_default")]
        _users    = [p for p in _all_profiles if not p.get("_is_default")]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Profils par défaut", len(_defaults))
        with col2:
            st.metric("Profils personnalisés", len(_users))
        for p in _all_profiles:
            lock  = " 🔒" if p.get("_is_default") else ""
            actif = " ← **actif**" if active_profile and p.get("id") == active_profile.get("id") else ""
            st.caption(f"{p.get('emoji','📁')} {p['nom']}{lock}{actif}")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE — Améliorations à venir
# ═════════════════════════════════════════════════════════════════════════════
elif page == "roadmap":
    st.title("🚧 Améliorations à venir")
    st.caption("Idées et évolutions prévues pour les prochaines versions.")

    st.divider()

    st.subheader("Support multi-utilisateurs")
    st.markdown("""
L'architecture actuelle est pensée pour un usage **mono-utilisateur** (une machine, un compte Google).

Pour permettre à plusieurs utilisateurs d'utiliser l'application indépendamment, il faudrait :

- **Passer l'app Google Cloud en mode Production** — aujourd'hui seuls les emails ajoutés manuellement comme *testeurs* dans la Google Cloud Console peuvent s'authentifier. Un utilisateur inconnu reçoit une erreur `403 access_denied`.
- **Implémenter un OAuth2 web flow côté serveur** — chaque utilisateur aurait sa propre session et son propre `token.json`, géré dynamiquement plutôt que stocké sur le disque.
- **Isoler les configurations par utilisateur** — clé Groq, Google Sheet ID, profils actifs, chacun dans son propre espace.

En attendant, la solution la plus simple pour partager l'app est d'ajouter l'email de chaque utilisateur comme testeur dans la [Google Cloud Console](https://console.cloud.google.com).
    """)

    st.divider()

    st.subheader("Nouveau tri par défaut : Facturation")
    st.markdown("""
Un nouveau profil **Facturation** est prévu pour lire et trier automatiquement les emails contenant des factures.

**Catégories prévues :**
- `Facture reçue` — facture fournisseur à traiter ou à payer
- `Facture envoyée` — confirmation d'émission ou de paiement client
- `Relance paiement` — relance pour impayé, demande de régularisation
- `Avoir / Remboursement` — avoir commercial, note de crédit, remboursement
- `Abonnement / Récurrent` — renouvellement automatique, SaaS, abonnement mensuel
- ...


    """)

    st.divider()

    st.subheader("Ajout de la suppression avec une connexion IMAP")
    st.markdown("""
Actuellement l'application place dans la corbeil Gmail les éléments supprimés depuis le visualisateur, nous travaillons sur une fonctionnalité similaire avec les connexions IMAP


    """)

    st.divider()

    st.subheader("Création d'un google sheet pour les connexions avec compte Google")
    st.markdown("""
Pour les connexions avec un compte Gmail, il sera possible de créer un google sheet pour les réusltats de l'analyse automatiquement. L'export en CSV manuel restera disponiible.


    """)

    st.divider()

    st.subheader("Modifications de nommage et d'organisation du menu")
    st.markdown("""
- onglet API
- Détail du diagnostic
- Partie "Principal" du sidebar, changement dénomination
- ...


    """)

    st.divider()
    st.info("💡 D'autres idées ? N'hésitez pas à contribuer sur le dépôt GitHub ou simplement contacter les créateurs : Kémil Lamouri et Mathias Segura.")